"""
Run the deal discovery pipeline with LLM-based filtering and extraction.

This script crawls news sites, filters articles using GPT-3.5-turbo,
and extracts deal information using GPT-4o-mini.

Usage:
    python step2_run_pipeline.py --config config/config.yaml

Requires:
    - OPENAI_API_KEY environment variable
"""

import gzip
import json
import logging
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.config_loader import load_config, load_ta_vocab, load_aliases
from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler
from deal_finder.discovery.url_index import URLIndex
from deal_finder.utils.selenium_client import SeleniumWebClient
from deal_finder.normalization import CompanyCanonicalizer
from deal_finder.models import Deal, FieldEvidence, Evidence
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


    # Load STAT+ authentication cookies if available
    auth_cookies = {}
    stat_cookies_file = Path("config/stat_cookies.json")
    if stat_cookies_file.exists():
        logger.info(f"✓ Loading STAT+ authentication cookies from {stat_cookies_file}")
        with open(stat_cookies_file) as f:
            auth_cookies = json.load(f)
    else:
        logger.info("ℹ️  No STAT+ cookies found. STAT+ articles may be paywalled.")
        logger.info("   To access STAT+ content: run `python extract_stat_cookies.py`")


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
            url_filters=url_filters,
            auth_cookies=auth_cookies
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

    # Load checkpoint if exists (gzip compressed for 80% disk savings)
    checkpoint_file = Path("output/fetch_checkpoint.json.gz")
    fetched_urls = set()
    checkpoint_articles = []

    if checkpoint_file.exists():
        try:
            with gzip.open(checkpoint_file, 'rt', encoding='utf-8') as f:
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
        # Filter and group URLs in single pass (memory-efficient)
        urls_by_source = defaultdict(list)
        filtered_count = 0
        for article_meta in discovered_urls:
            if article_meta["url"] not in fetched_urls:
                source = article_meta.get("source", "Unknown")
                urls_by_source[source].append(article_meta)
                filtered_count += 1

        logger.info(f"Remaining to fetch: {filtered_count} URLs")
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
        from queue import Queue
        import time

        progress_lock = Lock()
        total_processed = [0]
        total_failures = [0]
        all_fetched_articles = checkpoint_articles.copy()  # Start with checkpoint articles
        checkpoint_counter = [0]

        # Create web client pool (limit concurrent browsers to reduce memory)
        max_browsers = min(10, len(worker_groups))
        web_client_pool = Queue()

        logger.info(f"Creating pool of {max_browsers} reusable web clients...")
        for i in range(max_browsers):
            web_client = SeleniumWebClient(headless=True, timeout=5)
            web_client_pool.put(web_client)

        def save_checkpoint():
            """Save checkpoint to disk (gzip compressed)."""
            try:
                with gzip.open(checkpoint_file, 'wt', encoding='utf-8') as f:
                    json.dump({
                        "fetched_urls": list(fetched_urls),
                        "articles": all_fetched_articles,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, f)
                logger.info(f"✓ Checkpoint saved (compressed): {len(fetched_urls)} URLs, {len(all_fetched_articles)} articles")
            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}")

        def fetch_worker(worker_name, article_list):
            """Worker function to fetch articles."""
            worker_logger = logging.getLogger(worker_name)
            web_client = web_client_pool.get()  # Get from pool (reuse browser)

            try:
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

                worker_logger.info(f"{worker_name} finished: {len(worker_articles)} articles, {worker_failures} failures")
                return worker_articles, worker_failures
            finally:
                web_client_pool.put(web_client)  # Return to pool for reuse

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

        # Cleanup web client pool
        logger.info("Cleaning up web client pool...")
        while not web_client_pool.empty():
            client = web_client_pool.get()
            try:
                client.close()
            except Exception as e:
                logger.warning(f"Error closing web client: {e}")

        articles = all_fetched_articles
        logger.info(f"✓ Fetched {len(articles)} articles total ({total_failures[0]} failures)")
        logger.info(f"✓ Checkpoint preserved at: {checkpoint_file}")

    # STEP 3: OpenAI Extraction with Two-Pass Filtering + Deduplication
    logger.info("\n" + "=" * 80)

    # Initialize extractor (needed for parsing even if we skip extraction)
    from deal_finder.extraction.openai_extractor import OpenAIExtractor
    openai_extractor = OpenAIExtractor(api_key=openai_key, batch_size=10)

    if args.skip_extraction:
        logger.info("STEP 3: Loading from extraction checkpoint (--skip-extraction)")
        logger.info("=" * 80)

        extraction_checkpoint_file = Path("output/extraction_checkpoint.json.gz")
        if not extraction_checkpoint_file.exists():
            logger.error("❌ Extraction checkpoint not found! Run without --skip-extraction first.")
            return 1

        with gzip.open(extraction_checkpoint_file, 'rt', encoding='utf-8') as f:
            checkpoint_data = json.load(f)
            extractions = checkpoint_data.get("extractions", [])
            articles = checkpoint_data.get("articles", [])

        logger.info(f"✓ Loaded {len(extractions)} extractions from checkpoint")
    else:
        logger.info("STEP 3: OpenAI Extraction (Two-Pass: nano → dedup → gpt-4.1)")
        logger.info("=" * 80)

        extractions = openai_extractor.extract_batch(articles, ta_vocab)

        # Save extraction checkpoint
        extraction_checkpoint_file = Path("output/extraction_checkpoint.json.gz")
        extraction_checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(extraction_checkpoint_file, 'wt', encoding='utf-8') as f:
            json.dump({
                "extractions": extractions,
                "articles": articles,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, f)
        logger.info(f"✓ Saved extraction checkpoint: {len(extractions)} extractions")

    # STEP 4: Parse results
    logger.info("\n" + "=" * 80)

    if args.skip_parsing:
        logger.info("STEP 4: Loading from parsing checkpoint (--skip-parsing)")
        logger.info("=" * 80)

        parsing_checkpoint_file = Path("output/parsing_checkpoint.json.gz")
        if not parsing_checkpoint_file.exists():
            logger.error("❌ Parsing checkpoint not found! Run without --skip-parsing first.")
            return 1

        with gzip.open(parsing_checkpoint_file, 'rt', encoding='utf-8') as f:
            checkpoint_data = json.load(f)
            # Load extracted deals
            extracted_deals_data = checkpoint_data.get("extracted_deals", [])
            perplexity_rejected = checkpoint_data.get("perplexity_rejected", [])

            # Reconstruct Deal objects
            extracted_deals = []
            for deal_data in extracted_deals_data:
                deal = Deal(
                    date_announced=datetime.fromisoformat(deal_data["date_announced"]).date() if deal_data.get("date_announced") else None,
                    target=deal_data.get("target"),
                    acquirer=deal_data.get("acquirer"),
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
                    confidence=Decimal(str(deal_data["confidence"])) if deal_data.get("confidence") else Decimal("1.0"),
                    evidence=FieldEvidence(
                        date_announced=Evidence(**deal_data["evidence"]["date_announced"]) if deal_data.get("evidence", {}).get("date_announced") else None,
                        target=Evidence(**deal_data["evidence"]["target"]) if deal_data.get("evidence", {}).get("target") else None,
                        acquirer=Evidence(**deal_data["evidence"]["acquirer"]) if deal_data.get("evidence", {}).get("acquirer") else None
                    ) if deal_data.get("evidence") else None,
                    inclusion_reason=deal_data.get("inclusion_reason"),
                    timestamp_utc=deal_data.get("timestamp_utc")
                )
                extracted_deals.append(deal)

        logger.info(f"✓ Loaded {len(extracted_deals)} deals and {len(perplexity_rejected)} rejected from checkpoint")
    else:
        logger.info("STEP 4: Parse Results")
        logger.info("=" * 80)

        company_canonicalizer = CompanyCanonicalizer(aliases)
        extracted_deals = []
        perplexity_rejected = []

        for i, extraction in enumerate(extractions):
            article = articles[i]
            url = article["url"]

            # Skip if no extraction
            if not extraction:
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "perplexity_reason": "No deal found"
                })
                continue

            parsed = openai_extractor.parse_extracted_deal(extraction, therapeutic_area)
            if not parsed:
                continue

            # Skip if missing critical fields
            if not parsed.get("target") or not parsed.get("acquirer"):
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "perplexity_reason": "Missing target or acquirer"
                })
                continue

            # Accept stage as-is without validation (stage is now a plain string, not enum)
            stage = (parsed.get("stage") or "unknown").lower()
            deal_type_raw = (parsed.get("deal_type") or "partnership").lower()

            # Map deal_type to valid enum values
            valid_deal_types = ["m&a", "partnership", "licensing", "option-to-license"]
            if deal_type_raw not in valid_deal_types:
                logger.info(f"Mapping invalid deal_type '{deal_type_raw}' to 'partnership' for {url}")
                deal_type_raw = "partnership"

            deal_type = "M&A" if deal_type_raw == "m&a" else deal_type_raw

            # Create Deal object - let Pydantic handle validation
            try:
                deal = Deal(
                    date_announced=parsed.get("date_announced"),
                    target=company_canonicalizer.canonicalize(parsed["target"]),
                    acquirer=company_canonicalizer.canonicalize(parsed["acquirer"]),
                    stage=stage,
                    therapeutic_area=parsed.get("therapeutic_area") or therapeutic_area,
                    asset_focus=parsed.get("asset_focus") or "Undisclosed",
                    deal_type_detailed=deal_type,
                    source_url=parsed.get("url", url),
                    needs_review=True,  # Flag all for manual review
                    upfront_value_usd=parsed.get("upfront_value_usd"),
                    contingent_payment_usd=parsed.get("contingent_payment_usd"),
                    total_deal_value_usd=parsed.get("total_deal_value_usd"),
                    upfront_pct_total=parsed.get("upfront_pct_total"),
                    geography=parsed.get("geography"),
                    detected_currency=parsed.get("currency") or "USD",
                    fx_rate=Decimal("1.0") if parsed.get("currency") == "USD" else None,
                    fx_source="OpenAI",
                    inclusion_reason=f"OpenAI extraction (conf: {parsed.get('confidence', 'unknown')})",
                    timestamp_utc=datetime.now(timezone.utc).isoformat()
                )
                extracted_deals.append(deal)
            except Exception as e:
                logger.warning(f"Failed to create Deal object for {url}: {e}")
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "perplexity_reason": f"Validation error: {str(e)}"
                })
                continue

        # Save parsing checkpoint
        parsing_checkpoint_file = Path("output/parsing_checkpoint.json.gz")
        parsing_checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert deals to dict for JSON serialization
        extracted_deals_data = []
        for deal in extracted_deals:
            deal_dict = {
                "date_announced": deal.date_announced.isoformat() if deal.date_announced else None,
                "target": deal.target,
                "acquirer": deal.acquirer,
                "stage": str(deal.stage) if deal.stage else None,
                "therapeutic_area": deal.therapeutic_area,
                "asset_focus": deal.asset_focus,
                "deal_type_detailed": str(deal.deal_type_detailed) if deal.deal_type_detailed else None,
                "source_url": str(deal.source_url) if deal.source_url else None,
                "needs_review": deal.needs_review,
                "upfront_value_usd": str(deal.upfront_value_usd) if deal.upfront_value_usd else None,
                "contingent_payment_usd": str(deal.contingent_payment_usd) if deal.contingent_payment_usd else None,
                "total_deal_value_usd": str(deal.total_deal_value_usd) if deal.total_deal_value_usd else None,
                "upfront_pct_total": str(deal.upfront_pct_total) if deal.upfront_pct_total else None,
                "geography": deal.geography,
                "detected_currency": deal.detected_currency,
                "fx_rate": str(deal.fx_rate) if deal.fx_rate else None,
                "fx_source": deal.fx_source,
                "confidence": str(deal.confidence) if deal.confidence else None,
                "evidence": {
                    "date_announced": deal.evidence.date_announced.model_dump() if deal.evidence and deal.evidence.date_announced else None,
                    "target": deal.evidence.target.model_dump() if deal.evidence and deal.evidence.target else None,
                    "acquirer": deal.evidence.acquirer.model_dump() if deal.evidence and deal.evidence.acquirer else None
                } if deal.evidence else None,
                "inclusion_reason": deal.inclusion_reason,
                "timestamp_utc": deal.timestamp_utc
            }
            extracted_deals_data.append(deal_dict)

        with gzip.open(parsing_checkpoint_file, 'wt', encoding='utf-8') as f:
            json.dump({
                "extracted_deals": extracted_deals_data,
                "perplexity_rejected": perplexity_rejected,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, f)
        logger.info(f"✓ Saved parsing checkpoint: {len(extracted_deals)} deals")

    logger.info(f"✓ Extracted {len(extracted_deals)} deals")

    # STEP 5: Deal deduplication
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Deduplicate Deals")
    logger.info("=" * 80)

    extracted_deals = deduplicate_deals(extracted_deals)

    # STEP 6: Save outputs
    logger.info("\n" + "=" * 80)
    logger.info("STEP 6: Save Results")
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
    logger.info(f"  • Deals extracted: {len(extracted_deals)}")
    logger.info(f"  • Rejected: {len(perplexity_rejected)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
