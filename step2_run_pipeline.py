"""
STEP 2: Run Pipeline with Pre-Generated Keywords

This script runs the hybrid pipeline using keywords from config/generated_keywords.json
that you edited in Step 1.

Usage:
    python step2_run_pipeline.py --config config/config.yaml

Requires:
    - config/generated_keywords.json (from Step 1)
    - PERPLEXITY_API_KEY environment variable
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.config_loader import load_config, load_ta_vocab, load_aliases
from deal_finder.keyword_filter import KeywordFilter
from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler
from deal_finder.utils.selenium_client import SeleniumWebClient
from deal_finder.extraction.perplexity_extractor import PerplexityExtractor
from deal_finder.normalization import CompanyCanonicalizer
from deal_finder.models import Deal, FieldEvidence
from deal_finder.output import ExcelWriter
from bs4 import BeautifulSoup
from decimal import Decimal
from difflib import SequenceMatcher

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def deduplicate_by_title(articles: list) -> list:
    """
    Remove duplicate articles using embeddings-based semantic similarity.

    Strategy:
    1. Generate embeddings for article titles + first 200 chars of content
    2. Compute pairwise cosine similarity
    3. Group similar articles (>0.85 similarity)
    4. Keep longest version from each group

    Args:
        articles: List of article dicts with "title" and "content" keys

    Returns:
        Deduplicated list
    """
    from sentence_transformers import SentenceTransformer
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    if not articles:
        return articles

    logger.info("Loading sentence transformer model for deduplication...")
    model = SentenceTransformer('all-MiniLM-L6-v2')  # Fast, lightweight model

    # Create text to embed: title + first 200 chars of content
    texts = []
    for article in articles:
        title = article.get("title", "")
        content = article.get("content", "")[:200]
        text = f"{title} {content}"
        texts.append(text)

    logger.info(f"Generating embeddings for {len(texts)} articles...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=256)

    logger.info("Computing similarity matrix...")
    # Compute pairwise cosine similarity
    similarity_matrix = cosine_similarity(embeddings)

    # Find duplicates (similarity > 0.85)
    SIMILARITY_THRESHOLD = 0.85
    seen = set()
    duplicates_removed = 0
    final_articles = []

    for i in range(len(articles)):
        if i in seen:
            continue

        # Find all articles similar to this one
        similar_indices = [j for j in range(len(articles))
                          if j != i and similarity_matrix[i][j] > SIMILARITY_THRESHOLD]

        if similar_indices:
            # Found duplicates - keep the longest one
            group = [i] + similar_indices
            longest_idx = max(group, key=lambda idx: len(articles[idx].get("content", "")))

            # Mark others as seen
            for idx in group:
                if idx != longest_idx:
                    seen.add(idx)
                    duplicates_removed += 1
                    logger.debug(f"Duplicate: '{articles[idx].get('title', '')[:50]}...' (similarity: {similarity_matrix[i][idx]:.2f})")

            # Add longest version if not already added
            if longest_idx not in seen:
                final_articles.append(articles[longest_idx])
                seen.add(longest_idx)
        else:
            # No duplicates found
            final_articles.append(articles[i])
            seen.add(i)

    logger.info(f"Embeddings deduplication: {len(articles)} → {len(final_articles)} ({duplicates_removed} removed)")
    return final_articles


def deduplicate_deals(deals: list) -> list:
    """
    Remove duplicate deals based on (acquirer + target + date).

    Args:
        deals: List of Deal objects

    Returns:
        Deduplicated list, keeping the "best" version of each deal
    """
    seen_deals = {}
    unique_deals = []

    for deal in deals:
        # Create unique key
        key = (
            deal.acquirer.lower(),
            deal.target.lower(),
            deal.date_announced.strftime("%Y-%m-%d")
        )

        if key not in seen_deals:
            seen_deals[key] = deal
            unique_deals.append(deal)
        else:
            # Already have this deal - keep the one with more complete data
            existing = seen_deals[key]

            # Compare total deal value (keep the one with value if one is missing)
            if deal.total_deal_value_usd and not existing.total_deal_value_usd:
                # New one has value, old doesn't → replace
                unique_deals.remove(existing)
                unique_deals.append(deal)
                seen_deals[key] = deal
            elif deal.total_deal_value_usd and existing.total_deal_value_usd:
                # Both have values - keep the larger one (more complete)
                if deal.total_deal_value_usd > existing.total_deal_value_usd:
                    unique_deals.remove(existing)
                    unique_deals.append(deal)
                    seen_deals[key] = deal

    duplicates = len(deals) - len(unique_deals)
    if duplicates > 0:
        logger.info(f"Deal deduplication: {len(deals)} → {len(unique_deals)} ({duplicates} duplicates removed)")

    return unique_deals


def main():
    """Run Step 2: Pipeline with pre-generated keywords."""
    import argparse

    parser = argparse.ArgumentParser(description="Step 2: Run Pipeline")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--keywords",
        default="config/generated_keywords.json",
        help="Path to generated keywords file (from Step 1)"
    )
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip crawling and load URLs from existing index (for resuming)"
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip fetching and use only checkpoint articles"
    )
    parser.add_argument(
        "--filter-only",
        action="store_true",
        help="Stop after keyword filtering (don't run Perplexity extraction)"
    )
    parser.add_argument(
        "--skip-filter",
        action="store_true",
        help="Skip filtering and use filter checkpoint"
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip OpenAI extraction and use extraction checkpoint"
    )
    parser.add_argument(
        "--skip-parsing",
        action="store_true",
        help="Skip parsing and use parsing checkpoint"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("STEP 2: Run Pipeline with Pre-Generated Keywords")
    logger.info("=" * 80)

    # Load configuration
    config = load_config(args.config)
    ta_vocab = load_ta_vocab(config)
    aliases = load_aliases(config)

    therapeutic_area = ta_vocab["therapeutic_area"]
    start_date = config.START_DATE
    end_date = config.end_date_resolved

    logger.info(f"Therapeutic Area: {therapeutic_area}")
    logger.info(f"Date Range: {start_date} to {end_date}")

    # Load keywords from file
    keywords_file = Path(args.keywords)
    if not keywords_file.exists():
        logger.error(f"❌ Keywords file not found: {keywords_file}")
        logger.error("Run Step 1 first: python step1_generate_keywords.py")
        return 1

    logger.info(f"\nLoading keywords from: {keywords_file}")
    with open(keywords_file) as f:
        keyword_data = json.load(f)

    ta_keywords = keyword_data["keywords"]["ta_keywords"]
    stage_keywords = keyword_data["keywords"]["stage_keywords"]
    deal_keywords = keyword_data["keywords"]["deal_keywords"]

    logger.info(f"✓ Loaded {len(ta_keywords)} TA keywords")
    logger.info(f"✓ Loaded {len(stage_keywords)} stage keywords")
    logger.info(f"✓ Loaded {len(deal_keywords)} deal keywords")

    # Check OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        logger.error("❌ OPENAI_API_KEY not set!")
        return 1

    logger.info("✓ OpenAI API key found")

    # STEP 1: Crawl sitemaps (ALL 7 SITES NOW!)
    logger.info("\n" + "=" * 80)

    if args.skip_crawl:
        logger.info("STEP 1: Load URLs from Index (--skip-crawl)")
        logger.info("=" * 80)
        from deal_finder.discovery.url_index import URLIndex
        url_index = URLIndex()
        discovered_urls = url_index.get_all_urls_with_metadata()
        logger.info(f"✓ Loaded {len(discovered_urls)} article URLs from index")
    else:
        logger.info("STEP 1: Crawl Sitemaps (All 7 Sites)")
        logger.info("=" * 80)

        # Get URL filters from config
        url_filters = config.URL_FILTERS

        crawler = ExhaustiveSiteCrawler(
            from_date=start_date,
            to_date=end_date,
            use_index=True,
            url_filters=url_filters
        )

        discovered_urls = crawler.crawl_all_sites()
        logger.info(f"✓ Discovered {len(discovered_urls)} article URLs from all sites")

    # STEP 2: Fetch content (PARALLEL with checkpointing)
    logger.info("\n" + "=" * 80)

    if args.skip_fetch:
        logger.info("STEP 2: Load Articles from Checkpoint (--skip-fetch)")
    else:
        logger.info("STEP 2: Fetch Article Content (3 Parallel Workers)")
    logger.info("=" * 80)

    # Load checkpoint if exists
    checkpoint_file = Path("output/fetch_checkpoint.json")
    fetched_urls = set()
    checkpoint_articles = []

    if checkpoint_file.exists():
        try:
            with open(checkpoint_file) as f:
                checkpoint_data = json.load(f)
                fetched_urls = set(checkpoint_data.get("fetched_urls", []))
                checkpoint_articles = checkpoint_data.get("articles", [])
            logger.info(f"✓ Loaded checkpoint: {len(fetched_urls)} URLs already fetched, {len(checkpoint_articles)} articles")
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            fetched_urls = set()
            checkpoint_articles = []

    # If skip-fetch, use only checkpoint articles
    if args.skip_fetch:
        articles = checkpoint_articles
        logger.info(f"✓ Using {len(articles)} articles from checkpoint")
    else:
        # Filter out already-fetched URLs
        discovered_urls = [art for art in discovered_urls if art["url"] not in fetched_urls]
        logger.info(f"Remaining to fetch: {len(discovered_urls)} URLs")

        # Group URLs by source
        from collections import defaultdict
        urls_by_source = defaultdict(list)
        for article_meta in discovered_urls:
            source = article_meta.get("source", "Unknown")
            urls_by_source[source].append(article_meta)

        logger.info("URLs by source:")
        for source, urls in urls_by_source.items():
            logger.info(f"  {source}: {len(urls)} URLs")

        # Create source-dedicated worker groups (3 workers per source)
        # Each source gets its own workers to avoid rate limiting
        worker_groups = []

        for source, urls in urls_by_source.items():
            if not urls:
                continue

            # Split this source's URLs into 3 equal chunks
            chunk_size = len(urls) // 3

            for i in range(3):
                start = i * chunk_size
                end = start + chunk_size if i < 2 else len(urls)  # Last worker gets remainder

                worker_name = f"Worker-{source.replace(' ', '')}-{i+1}"
                worker_urls = urls[start:end]

                if worker_urls:  # Only add if has URLs
                    worker_groups.append((worker_name, worker_urls))

        logger.info(f"\nSource-dedicated worker distribution ({len(worker_groups)} workers):")
        for name, urls in worker_groups:
            logger.info(f"  {name}: {len(urls)} URLs")

        # Worker function
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from threading import Lock
        import time

        progress_lock = Lock()
        total_processed = [0]
        total_failures = [0]
        all_fetched_articles = checkpoint_articles.copy()  # Start with checkpoint articles
        checkpoint_counter = [0]

        def save_checkpoint():
            """Save checkpoint to disk."""
            try:
                with open(checkpoint_file, 'w') as f:
                    json.dump({
                        "fetched_urls": list(fetched_urls),
                        "articles": all_fetched_articles,
                        "timestamp": datetime.utcnow().isoformat()
                    }, f)
                logger.info(f"✓ Checkpoint saved: {len(fetched_urls)} URLs, {len(all_fetched_articles)} articles")
            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}")

        def fetch_worker(worker_name, article_list):
            """Worker function to fetch articles."""
            worker_logger = logging.getLogger(worker_name)
            web_client = SeleniumWebClient(headless=True, timeout=5)
            worker_articles = []
            worker_failures = 0

            for i, article_meta in enumerate(article_list, 1):
                url = article_meta["url"]

                try:
                    html = web_client.fetch(url)
                    if not html:
                        worker_failures += 1
                        continue

                    soup = BeautifulSoup(html, "lxml")
                    text = soup.get_text(separator=" ", strip=True)

                    if len(text) < 500:
                        continue

                    article = {
                        "url": url,
                        "title": article_meta.get("title", ""),
                        "published_date": article_meta.get("published_date", ""),
                        "content": text[:20000],
                        "source": article_meta.get("source", "Unknown")
                    }
                    worker_articles.append(article)

                    # Add to shared list and mark as fetched
                    with progress_lock:
                        all_fetched_articles.append(article)
                        fetched_urls.add(url)
                        checkpoint_counter[0] += 1

                        # Save checkpoint every 1000 articles
                        if checkpoint_counter[0] % 1000 == 0:
                            save_checkpoint()

                except Exception as e:
                    worker_failures += 1

                # Update progress every 50 articles
                if i % 50 == 0:
                    with progress_lock:
                        total_processed[0] += 50
                        logger.info(f"Overall Progress: {total_processed[0]}/{len(discovered_urls)} (~{total_failures[0]} failures)")

            web_client.close()
            worker_logger.info(f"{worker_name} finished: {len(worker_articles)} articles, {worker_failures} failures")
            return worker_articles, worker_failures

        # Run parallel workers
        logger.info(f"\nStarting {len(worker_groups)} parallel workers...")

        with ThreadPoolExecutor(max_workers=len(worker_groups)) as executor:
            futures = {
                executor.submit(fetch_worker, name, urls): name
                for name, urls in worker_groups if len(urls) > 0
            }

            for future in as_completed(futures):
                worker_name = futures[future]
                try:
                    worker_articles, worker_failures = future.result()
                    total_failures[0] += worker_failures
                except Exception as e:
                    logger.error(f"{worker_name} crashed: {e}")

        # Final checkpoint save
        save_checkpoint()

        articles = all_fetched_articles
        logger.info(f"✓ Fetched {len(articles)} articles total ({total_failures[0]} failures)")
        logger.info(f"✓ Checkpoint preserved at: {checkpoint_file}")

    # STEP 3: Skip deduplication for now (will do after keyword filter)
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Deduplication (SKIPPED - will do after keyword filter)")
    logger.info("=" * 80)
    logger.info(f"Using all {len(articles)} articles for keyword filtering")

    # STEP 4: Load from checkpoint or run filter
    if args.skip_filter:
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Loading from keyword filter checkpoint (--skip-filter)")
        logger.info("=" * 80)

        keyword_checkpoint_file = Path("output/keyword_checkpoint.json")
        if not keyword_checkpoint_file.exists():
            logger.error("❌ Keyword filter checkpoint not found! Run without --skip-filter first.")
            return 1

        with open(keyword_checkpoint_file) as f:
            checkpoint_data = json.load(f)
            passed_articles = checkpoint_data.get("articles", [])

        logger.info(f"✓ Loaded {len(passed_articles)} articles from keyword filter checkpoint")

    else:
        # STEP 4: Keyword filter
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Keyword Pre-Filter")
        logger.info("=" * 80)

        keyword_filter = KeywordFilter(
            ta_keywords=ta_keywords,
            stage_keywords=stage_keywords,
            deal_keywords=deal_keywords,
            require_deal_keyword=True,
            min_ta_matches=2,
            min_deal_matches=2,
            require_money_mention=True
        )

        filter_results = keyword_filter.filter_articles(articles)
        passed_articles = filter_results["passed"]

        logger.info(f"✓ Keyword Filter: {len(passed_articles)}/{len(articles)} passed")
        logger.info(f"  Cost savings: ${(len(articles) - len(passed_articles)) * 0.06:.2f}")

        # Save checkpoint after keyword filter
        keyword_checkpoint_file = Path("output/keyword_checkpoint.json")
        keyword_checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with open(keyword_checkpoint_file, 'w') as f:
            json.dump({"articles": passed_articles}, f)
        logger.info(f"✓ Saved keyword filter checkpoint: {len(passed_articles)} articles")

        # STEP 4.5: LLM Pre-filter (GPT-4o-mini for early-stage deals)
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4.5: LLM Pre-Filter (Early-Stage Deals)")
        logger.info("=" * 80)

        from deal_finder.llm_prefilter import LLMPreFilter
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            llm_filter = LLMPreFilter(api_key=openai_key, batch_size=20)
            llm_results = llm_filter.filter_articles(passed_articles, therapeutic_area)
            passed_articles = llm_results["passed"]
            logger.info(f"  LLM filter cost: ${llm_results['cost']:.2f}")
        else:
            logger.warning("⚠ OPENAI_API_KEY not set, skipping LLM pre-filter")

        logger.info(f"  Estimated Perplexity cost (before dedup): ${len(passed_articles) * 0.06:.2f}")

        # STEP 4.6: Deduplicate filtered articles with embeddings
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4.5: Deduplicate Filtered Articles (Embeddings)")
        logger.info("=" * 80)

        passed_articles = deduplicate_by_title(passed_articles)
        logger.info(f"  Final Perplexity cost (after dedup): ${len(passed_articles) * 0.06:.2f}")

        # Save checkpoint after filtering
        filter_checkpoint_file = Path("output/filter_checkpoint.json")
        filter_checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with open(filter_checkpoint_file, 'w') as f:
            json.dump({"articles": passed_articles}, f)
        logger.info(f"✓ Saved filter checkpoint: {len(passed_articles)} articles")

    if args.filter_only:
        logger.info("\n" + "=" * 80)
        logger.info("FILTER-ONLY MODE: Stopping before Perplexity extraction")
        logger.info("=" * 80)
        logger.info(f"With current settings (min_ta={keyword_filter.min_ta_matches}, min_deal={keyword_filter.min_deal_matches}):")
        logger.info(f"  {len(passed_articles)} articles would be sent to Perplexity")
        logger.info(f"  Estimated cost: ${len(passed_articles) * 0.06:.2f}")
        return 0

    if not passed_articles:
        logger.warning("⚠ No articles passed filter!")
        return 1

    # STEP 5: OpenAI GPT-4o-mini extraction (replaces Perplexity)
    logger.info("\n" + "=" * 80)

    # Initialize extractor (needed for parsing even if we skip extraction)
    from deal_finder.extraction.openai_extractor import OpenAIExtractor
    openai_extractor = OpenAIExtractor(api_key=openai_key, batch_size=10)

    if args.skip_extraction:
        logger.info("STEP 5: Loading from extraction checkpoint (--skip-extraction)")
        logger.info("=" * 80)

        extraction_checkpoint_file = Path("output/extraction_checkpoint.json")
        if not extraction_checkpoint_file.exists():
            logger.error("❌ Extraction checkpoint not found! Run without --skip-extraction first.")
            return 1

        with open(extraction_checkpoint_file) as f:
            checkpoint_data = json.load(f)
            extractions = checkpoint_data.get("extractions", [])
            passed_articles = checkpoint_data.get("articles", [])

        logger.info(f"✓ Loaded {len(extractions)} extractions from checkpoint")
    else:
        logger.info("STEP 5: OpenAI Extraction (GPT-4o-mini, Two-Pass + Parallel)")
        logger.info("=" * 80)

        extractions = openai_extractor.extract_batch(passed_articles, ta_vocab)

        # Save extraction checkpoint
        extraction_checkpoint_file = Path("output/extraction_checkpoint.json")
        extraction_checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with open(extraction_checkpoint_file, 'w') as f:
            json.dump({
                "extractions": extractions,
                "articles": passed_articles,
                "timestamp": datetime.utcnow().isoformat()
            }, f)
        logger.info(f"✓ Saved extraction checkpoint: {len(extractions)} extractions")

    # STEP 6: Parse results
    logger.info("\n" + "=" * 80)

    if args.skip_parsing:
        logger.info("STEP 6: Loading from parsing checkpoint (--skip-parsing)")
        logger.info("=" * 80)

        parsing_checkpoint_file = Path("output/parsing_checkpoint.json")
        if not parsing_checkpoint_file.exists():
            logger.error("❌ Parsing checkpoint not found! Run without --skip-parsing first.")
            return 1

        with open(parsing_checkpoint_file) as f:
            checkpoint_data = json.load(f)
            # Load extracted deals
            extracted_deals_data = checkpoint_data.get("extracted_deals", [])
            perplexity_rejected = checkpoint_data.get("perplexity_rejected", [])

            # Reconstruct Deal objects
            extracted_deals = []
            for deal_data in extracted_deals_data:
                deal = Deal(
                    date_announced=datetime.fromisoformat(deal_data["date_announced"]).date() if isinstance(deal_data["date_announced"], str) else deal_data["date_announced"],
                    target=deal_data["target"],
                    acquirer=deal_data["acquirer"],
                    stage=deal_data.get("stage"),
                    therapeutic_area=deal_data.get("therapeutic_area"),
                    asset_focus=deal_data.get("asset_focus"),
                    deal_type_detailed=deal_data.get("deal_type_detailed"),
                    source_url=deal_data.get("source_url"),
                    needs_review=deal_data.get("needs_review", False),
                    upfront_value_usd=Decimal(str(deal_data["upfront_value_usd"])) if deal_data.get("upfront_value_usd") else None,
                    contingent_payment_usd=Decimal(str(deal_data["contingent_payment_usd"])) if deal_data.get("contingent_payment_usd") else None,
                    total_deal_value_usd=Decimal(str(deal_data["total_deal_value_usd"])) if deal_data.get("total_deal_value_usd") else None,
                    upfront_pct_total=Decimal(str(deal_data["upfront_pct_total"])) if deal_data.get("upfront_pct_total") else None,
                    geography=deal_data.get("geography"),
                    detected_currency=deal_data.get("detected_currency"),
                    fx_rate=Decimal(str(deal_data["fx_rate"])) if deal_data.get("fx_rate") else None,
                    fx_source=deal_data.get("fx_source"),
                    evidence=FieldEvidence(
                        date_announced=deal_data.get("evidence", {}).get("date_announced", ""),
                        target=deal_data.get("evidence", {}).get("target", ""),
                        acquirer=deal_data.get("evidence", {}).get("acquirer", "")
                    ) if deal_data.get("evidence") else None,
                    inclusion_reason=deal_data.get("inclusion_reason"),
                    timestamp_utc=deal_data.get("timestamp_utc")
                )
                extracted_deals.append(deal)

        logger.info(f"✓ Loaded {len(extracted_deals)} deals and {len(perplexity_rejected)} rejected from checkpoint")
    else:
        logger.info("STEP 6: Parse Results")
        logger.info("=" * 80)

        company_canonicalizer = CompanyCanonicalizer(aliases)
        extracted_deals = []
        perplexity_rejected = []

        for i, extraction in enumerate(extractions):
            article = passed_articles[i]
            url = article["url"]

            if not extraction:
                keyword_matches = article.get("keyword_matches", {})
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "ta_keywords": ", ".join(keyword_matches.get("ta", [])[:10]),  # First 10
                    "stage_keywords": ", ".join(keyword_matches.get("stage", [])),
                    "deal_keywords": ", ".join(keyword_matches.get("deal", [])),
                    "perplexity_reason": "No deal found or did not match criteria"
                })
                continue

            parsed = openai_extractor.parse_extracted_deal(extraction, therapeutic_area)

            if not parsed:
                keyword_matches = article.get("keyword_matches", {})
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "ta_keywords": ", ".join(keyword_matches.get("ta", [])[:10]),
                    "stage_keywords": ", ".join(keyword_matches.get("stage", [])),
                    "deal_keywords": ", ".join(keyword_matches.get("deal", [])),
                    "perplexity_reason": "Parsing failed or filtered out"
                })
                continue

            # Validate parsed has all required fields
            required_fields = ["target", "acquirer", "date_announced"]
            missing_fields = [f for f in required_fields if f not in parsed]
            if missing_fields:
                keyword_matches = article.get("keyword_matches", {})
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "ta_keywords": ", ".join(keyword_matches.get("ta", [])[:10]),
                    "stage_keywords": ", ".join(keyword_matches.get("stage", [])),
                    "deal_keywords": ", ".join(keyword_matches.get("deal", [])),
                    "perplexity_reason": f"Missing required fields: {', '.join(missing_fields)}"
                })
                logger.warning(f"Skipping deal - missing fields: {missing_fields} - {url}")
                continue

            deal = Deal(
                date_announced=parsed["date_announced"],
                target=company_canonicalizer.canonicalize(parsed["target"]),
                acquirer=company_canonicalizer.canonicalize(parsed["acquirer"]),
                stage=parsed.get("stage"),
                therapeutic_area=parsed.get("therapeutic_area"),
                asset_focus=parsed.get("asset_focus"),
                deal_type_detailed=parsed.get("deal_type"),
                source_url=parsed.get("url", url),
                needs_review=parsed.get("needs_review", False),
                upfront_value_usd=parsed.get("upfront_value_usd"),
                contingent_payment_usd=parsed.get("contingent_payment_usd"),
                total_deal_value_usd=parsed.get("total_deal_value_usd"),
                upfront_pct_total=parsed.get("upfront_pct_total"),
                geography=parsed.get("geography"),
                detected_currency=parsed.get("currency"),
                fx_rate=Decimal("1.0") if parsed.get("currency") == "USD" else None,
                fx_source="Perplexity",
                evidence=FieldEvidence(
                    date_announced=parsed.get("evidence", ""),
                    target=parsed.get("evidence", ""),
                    acquirer=parsed.get("evidence", "")
                ),
                inclusion_reason=f"Keyword + Perplexity (conf: {parsed.get('confidence', 'unknown')})",
                timestamp_utc=datetime.utcnow().isoformat()
            )

            extracted_deals.append(deal)

        # Save parsing checkpoint
        parsing_checkpoint_file = Path("output/parsing_checkpoint.json")
        parsing_checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert deals to dict for JSON serialization
        extracted_deals_data = []
        for deal in extracted_deals:
            deal_dict = {
                "date_announced": deal.date_announced.isoformat() if deal.date_announced else None,
                "target": deal.target,
                "acquirer": deal.acquirer,
                "stage": deal.stage,
                "therapeutic_area": deal.therapeutic_area,
                "asset_focus": deal.asset_focus,
                "deal_type_detailed": deal.deal_type_detailed,
                "source_url": deal.source_url,
                "needs_review": deal.needs_review,
                "upfront_value_usd": str(deal.upfront_value_usd) if deal.upfront_value_usd else None,
                "contingent_payment_usd": str(deal.contingent_payment_usd) if deal.contingent_payment_usd else None,
                "total_deal_value_usd": str(deal.total_deal_value_usd) if deal.total_deal_value_usd else None,
                "upfront_pct_total": str(deal.upfront_pct_total) if deal.upfront_pct_total else None,
                "geography": deal.geography,
                "detected_currency": deal.detected_currency,
                "fx_rate": str(deal.fx_rate) if deal.fx_rate else None,
                "fx_source": deal.fx_source,
                "evidence": {
                    "date_announced": deal.evidence.date_announced if deal.evidence else "",
                    "target": deal.evidence.target if deal.evidence else "",
                    "acquirer": deal.evidence.acquirer if deal.evidence else ""
                } if deal.evidence else None,
                "inclusion_reason": deal.inclusion_reason,
                "timestamp_utc": deal.timestamp_utc
            }
            extracted_deals_data.append(deal_dict)

        with open(parsing_checkpoint_file, 'w') as f:
            json.dump({
                "extracted_deals": extracted_deals_data,
                "perplexity_rejected": perplexity_rejected,
                "timestamp": datetime.utcnow().isoformat()
            }, f)
        logger.info(f"✓ Saved parsing checkpoint: {len(extracted_deals)} deals")

    logger.info(f"✓ Extracted {len(extracted_deals)} deals")

    # STEP 7: Deal deduplication
    logger.info("\n" + "=" * 80)
    logger.info("STEP 7: Deduplicate Deals")
    logger.info("=" * 80)

    extracted_deals = deduplicate_deals(extracted_deals)

    # STEP 8: Save outputs
    logger.info("\n" + "=" * 80)
    logger.info("STEP 8: Save Results")
    logger.info("=" * 80)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    run_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Output 1: Deals
    if extracted_deals:
        deals_file = output_dir / f"hybrid_deals_{timestamp}_{run_id}.xlsx"
        ExcelWriter().write(extracted_deals, str(deals_file))
        logger.info(f"✓ Saved {len(extracted_deals)} deals to: {deals_file}")

    # Output 2: Rejected
    if perplexity_rejected:
        import pandas as pd
        rejected_file = output_dir / f"hybrid_rejected_{timestamp}_{run_id}.xlsx"
        pd.DataFrame(perplexity_rejected).to_excel(rejected_file, index=False)
        logger.info(f"✓ Saved {len(perplexity_rejected)} rejected to: {rejected_file}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("✅ PIPELINE COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"\nResults:")
    logger.info(f"  • URLs crawled: {len(discovered_urls)}")
    logger.info(f"  • Articles fetched: {len(articles)}")
    logger.info(f"  • Passed keyword filter: {len(passed_articles)}")
    logger.info(f"  • Deals extracted: {len(extracted_deals)}")
    logger.info(f"  • Rejected by Perplexity: {len(perplexity_rejected)}")
    logger.info(f"\n💰 Cost: ~${len(passed_articles) * 0.06:.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
