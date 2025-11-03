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
    Remove duplicate articles based on title similarity.

    Args:
        articles: List of article dicts with "title" key

    Returns:
        Deduplicated list
    """
    unique_articles = []
    seen_titles = []
    duplicates_removed = 0

    for article in articles:
        title = article.get("title", "").lower()

        # Check if similar title already seen
        is_duplicate = False
        for seen_title in seen_titles:
            similarity = SequenceMatcher(None, title, seen_title).ratio()
            if similarity > 0.8:  # 80% similar = duplicate
                is_duplicate = True
                duplicates_removed += 1
                logger.debug(f"Duplicate found: '{title}' similar to '{seen_title}'")
                break

        if not is_duplicate:
            unique_articles.append(article)
            seen_titles.append(title)

    logger.info(f"Title deduplication: {len(articles)} → {len(unique_articles)} ({duplicates_removed} removed)")
    return unique_articles


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

    # Check Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        # Try loading from .env.example
        env_file = Path(__file__).parent / ".env.example"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("PERPLEXITY_API_KEY="):
                        perplexity_key = line.split("=", 1)[1]
                        os.environ["PERPLEXITY_API_KEY"] = perplexity_key
                        break

    if not perplexity_key:
        logger.error("❌ PERPLEXITY_API_KEY not set!")
        return 1

    logger.info("✓ API key found")

    # STEP 1: Crawl sitemaps (ALL 7 SITES NOW!)
    logger.info("\n" + "=" * 80)
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

    # STEP 2: Fetch content
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Fetch Article Content")
    logger.info("=" * 80)

    web_client = SeleniumWebClient(headless=True, timeout=20)
    articles = []
    fetch_failures = 0

    for i, article_meta in enumerate(discovered_urls, 1):
        url = article_meta["url"]

        if i % 50 == 0 or i == 1:
            logger.info(f"Progress: {i}/{len(discovered_urls)} ({fetch_failures} failures)")

        try:
            html = web_client.fetch(url)
            if not html:
                fetch_failures += 1
                continue

            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(separator=" ", strip=True)

            if len(text) < 500:
                continue

            articles.append({
                "url": url,
                "title": article_meta.get("title", ""),
                "published_date": article_meta.get("published_date", ""),
                "content": text[:20000]
            })

        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            fetch_failures += 1

    web_client.close()
    logger.info(f"✓ Fetched {len(articles)} articles ({fetch_failures} failures)")

    # STEP 3: Title-based deduplication (BEFORE keyword filter)
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Deduplicate by Title")
    logger.info("=" * 80)

    articles = deduplicate_by_title(articles)

    # STEP 4: Keyword filter
    logger.info("\n" + "=" * 80)
    logger.info("STEP 4: Keyword Pre-Filter")
    logger.info("=" * 80)

    keyword_filter = KeywordFilter(
        ta_keywords=ta_keywords,
        stage_keywords=stage_keywords,
        deal_keywords=deal_keywords,
        require_deal_keyword=True,
        min_ta_matches=1
    )

    filter_results = keyword_filter.filter_articles(articles)
    passed_articles = filter_results["passed"]

    logger.info(f"✓ Filter: {len(passed_articles)}/{len(articles)} passed")
    logger.info(f"  Cost savings: ${(len(articles) - len(passed_articles)) * 0.06:.2f}")

    if not passed_articles:
        logger.warning("⚠ No articles passed filter!")
        return 1

    # STEP 5: Perplexity extraction
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Perplexity Extraction")
    logger.info("=" * 80)

    perplexity_extractor = PerplexityExtractor(api_key=perplexity_key, batch_size=5)
    extractions = perplexity_extractor.extract_batch(passed_articles, ta_vocab)

    # STEP 6: Parse results
    logger.info("\n" + "=" * 80)
    logger.info("STEP 6: Parse Results")
    logger.info("=" * 80)

    company_canonicalizer = CompanyCanonicalizer(aliases)
    extracted_deals = []
    perplexity_rejected = []

    for i, extraction in enumerate(extractions):
        article = passed_articles[i]
        url = article["url"]

        if not extraction:
            perplexity_rejected.append({
                "url": url,
                "title": article.get("title", ""),
                "ta_keywords": ", ".join(article["keyword_matches"]["ta"][:10]),  # First 10
                "stage_keywords": ", ".join(article["keyword_matches"]["stage"]),
                "deal_keywords": ", ".join(article["keyword_matches"]["deal"]),
                "perplexity_reason": "No deal found or did not match criteria"
            })
            continue

        parsed = perplexity_extractor.parse_extracted_deal(extraction, therapeutic_area)

        if not parsed:
            perplexity_rejected.append({
                "url": url,
                "title": article.get("title", ""),
                "ta_keywords": ", ".join(article["keyword_matches"]["ta"][:10]),
                "stage_keywords": ", ".join(article["keyword_matches"]["stage"]),
                "deal_keywords": ", ".join(article["keyword_matches"]["deal"]),
                "perplexity_reason": "Parsing failed or filtered out"
            })
            continue

        deal = Deal(
            date_announced=parsed["date_announced"],
            target=company_canonicalizer.canonicalize(parsed["target"]),
            acquirer=company_canonicalizer.canonicalize(parsed["acquirer"]),
            stage=parsed["stage"],
            therapeutic_area=parsed["therapeutic_area"],
            asset_focus=parsed["asset_focus"],
            deal_type_detailed=parsed["deal_type"],
            source_url=parsed["url"],
            needs_review=parsed["needs_review"],
            upfront_value_usd=parsed["upfront_value_usd"],
            contingent_payment_usd=parsed["contingent_payment_usd"],
            total_deal_value_usd=parsed["total_deal_value_usd"],
            upfront_pct_total=parsed["upfront_pct_total"],
            geography=parsed["geography"],
            detected_currency=parsed["currency"],
            fx_rate=Decimal("1.0") if parsed["currency"] == "USD" else None,
            fx_source="Perplexity",
            evidence=FieldEvidence(
                date_announced=parsed["evidence"],
                target=parsed["evidence"],
                acquirer=parsed["evidence"]
            ),
            inclusion_reason=f"Keyword + Perplexity (conf: {parsed['confidence']})",
            timestamp_utc=datetime.utcnow().isoformat()
        )

        extracted_deals.append(deal)

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
