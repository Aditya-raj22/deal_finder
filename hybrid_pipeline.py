"""
Hybrid Pipeline: Keyword Pre-Filter + Perplexity Extraction

This is the main entry point for the cost-optimized pipeline that:
1. Generates TA keywords using ChatGPT-5
2. Crawls sitemaps exhaustively
3. Fetches article content
4. Filters by keywords (TA + stage + deal)
5. Sends filtered articles to Perplexity for extraction
6. Outputs TWO Excel files:
   a) Extracted deals (from Perplexity)
   b) Filtered-out URLs (passed keywords but not Perplexity)
"""

import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.config_loader import load_config, load_ta_vocab, load_aliases
from deal_finder.keyword_generator import KeywordGenerator
from deal_finder.keyword_filter import KeywordFilter, DateFilter
from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler
from deal_finder.utils.selenium_client import SeleniumWebClient
from deal_finder.extraction.perplexity_extractor import PerplexityExtractor
from deal_finder.normalization import CompanyCanonicalizer
from deal_finder.models import Deal, FieldEvidence, DealTypeDetailed, DevelopmentStage
from deal_finder.output import ExcelWriter
from bs4 import BeautifulSoup
from decimal import Decimal

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HybridPipeline:
    """Main hybrid pipeline orchestrator."""

    def __init__(self, config_path: str):
        """
        Initialize hybrid pipeline.

        Args:
            config_path: Path to config.yaml
        """
        logger.info("=" * 80)
        logger.info("HYBRID PIPELINE: Keyword Filter + Perplexity Extraction")
        logger.info("=" * 80)

        # Load configuration
        logger.info("Loading configuration...")
        self.config = load_config(config_path)
        self.ta_vocab = load_ta_vocab(self.config)
        self.aliases = load_aliases(self.config)

        # Extract config values
        self.therapeutic_area = self.ta_vocab["therapeutic_area"]
        self.start_date = self.config.START_DATE
        self.end_date = self.config.end_date_resolved
        self.stages = self.config.EARLY_STAGE_ALLOWED

        logger.info(f"Therapeutic Area: {self.therapeutic_area}")
        logger.info(f"Date Range: {self.start_date} to {self.end_date}")
        logger.info(f"Stages: {self.stages}")

        # Check API keys
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.perplexity_key = os.getenv("PERPLEXITY_API_KEY")

        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY not set!")
        if not self.perplexity_key:
            raise ValueError("PERPLEXITY_API_KEY not set!")

        logger.info("✓ API keys found")

    def run(self):
        """Execute the complete hybrid pipeline."""

        # STEP 1: Generate keywords using ChatGPT-5
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Generate Keywords with ChatGPT-5")
        logger.info("=" * 80)

        keyword_gen = KeywordGenerator(self.openai_key)

        # Generate TA keywords with multiple temperatures
        ta_result = keyword_gen.generate_keywords_for_ta(
            self.therapeutic_area,
            temperatures=[0.2, 0.3, 0.5, 0.7, 0.8]
        )
        ta_keywords = ta_result["final_keywords"]

        # Generate stage and deal keywords
        stage_keywords = keyword_gen.generate_stage_keywords(self.stages)
        deal_keywords = keyword_gen.generate_deal_keywords()

        logger.info(f"✓ Generated {len(ta_keywords)} TA keywords")
        logger.info(f"✓ Generated {len(stage_keywords)} stage keywords")
        logger.info(f"✓ Generated {len(deal_keywords)} deal keywords")

        # STEP 2: Crawl sitemaps
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Crawl Sitemaps (FierceBiotech)")
        logger.info("=" * 80)

        crawler = ExhaustiveSiteCrawler(
            from_date=self.start_date,
            to_date=self.end_date,
            use_index=True  # Incremental crawling enabled
        )

        discovered_urls = crawler.crawl_all()
        logger.info(f"✓ Discovered {len(discovered_urls)} article URLs")

        # STEP 3: Fetch article content
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Fetch Article Content")
        logger.info("=" * 80)

        web_client = SeleniumWebClient(headless=True, timeout=20)
        articles = []
        fetch_failures = 0

        for i, article_meta in enumerate(discovered_urls, 1):
            url = article_meta["url"]

            # Progress logging
            if i % 50 == 0 or i == 1:
                logger.info(f"Progress: {i}/{len(discovered_urls)} articles fetched ({fetch_failures} failures)")

            try:
                html = web_client.fetch(url)
                if not html:
                    fetch_failures += 1
                    continue

                # Extract text from HTML
                soup = BeautifulSoup(html, "lxml")
                text = soup.get_text(separator=" ", strip=True)

                # Skip very short articles
                if len(text) < 500:
                    logger.debug(f"Skipping (too short): {url}")
                    continue

                articles.append({
                    "url": url,
                    "title": article_meta.get("title", ""),
                    "published_date": article_meta.get("published_date", ""),
                    "content": text[:20000]  # Limit to 20k chars
                })

            except Exception as e:
                logger.warning(f"Error fetching {url}: {e}")
                fetch_failures += 1
                continue

        web_client.close()
        logger.info(f"✓ Fetched {len(articles)} articles ({fetch_failures} failures)")

        # STEP 4: Keyword filtering
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Keyword Pre-Filter")
        logger.info("=" * 80)

        keyword_filter = KeywordFilter(
            ta_keywords=ta_keywords,
            stage_keywords=stage_keywords,
            deal_keywords=deal_keywords,
            require_deal_keyword=True,  # Must mention a deal
            min_ta_matches=1  # At least 1 TA keyword
        )

        filter_results = keyword_filter.filter_articles(articles)

        passed_articles = filter_results["passed"]
        failed_articles = filter_results["failed"]
        stats = filter_results["stats"]

        logger.info(f"✓ Filter complete: {stats['passed']}/{stats['total']} passed ({stats['pass_rate']})")
        logger.info(f"  Cost savings: Sending {len(passed_articles)} articles instead of {len(articles)}")
        logger.info(f"  Estimated savings: ${(len(articles) - len(passed_articles)) * 0.06:.2f}")

        # STEP 5: Perplexity extraction
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Perplexity Extraction (Filtered Articles Only)")
        logger.info("=" * 80)

        if not passed_articles:
            logger.warning("No articles passed keyword filter! Nothing to send to Perplexity.")
            return

        perplexity_extractor = PerplexityExtractor(
            api_key=self.perplexity_key,
            batch_size=5
        )

        # Extract deals from filtered articles
        extractions = perplexity_extractor.extract_batch(passed_articles, self.ta_vocab)
        logger.info(f"✓ Extraction complete: {len(extractions)} responses")

        # STEP 6: Parse Perplexity results
        logger.info("\n" + "=" * 80)
        logger.info("STEP 6: Parse Extraction Results")
        logger.info("=" * 80)

        company_canonicalizer = CompanyCanonicalizer(self.aliases)
        extracted_deals = []
        perplexity_rejected = []

        for i, extraction in enumerate(extractions):
            article = passed_articles[i]
            url = article["url"]

            if not extraction:
                # Perplexity returned null (no deal found)
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "ta_keywords": ", ".join(article["keyword_matches"]["ta"]),
                    "stage_keywords": ", ".join(article["keyword_matches"]["stage"]),
                    "deal_keywords": ", ".join(article["keyword_matches"]["deal"]),
                    "perplexity_reason": "No deal found or did not match criteria"
                })
                continue

            # Parse extracted deal
            parsed = perplexity_extractor.parse_extracted_deal(
                extraction,
                self.therapeutic_area
            )

            if not parsed:
                # Parsing failed or filtered out
                perplexity_rejected.append({
                    "url": url,
                    "title": article.get("title", ""),
                    "ta_keywords": ", ".join(article["keyword_matches"]["ta"]),
                    "stage_keywords": ", ".join(article["keyword_matches"]["stage"]),
                    "deal_keywords": ", ".join(article["keyword_matches"]["deal"]),
                    "perplexity_reason": "Extraction failed or filtered by Perplexity"
                })
                continue

            # Create Deal object
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
                    acquirer=parsed["evidence"],
                ),
                inclusion_reason=f"Keyword filter + Perplexity extraction (confidence: {parsed['confidence']})",
                timestamp_utc=datetime.utcnow().isoformat(),
            )

            extracted_deals.append(deal)
            logger.info(f"  ✓ Deal extracted: {parsed['acquirer']} + {parsed['target']}")

        logger.info(f"✓ Parsed {len(extracted_deals)} deals")
        logger.info(f"✓ Perplexity rejected {len(perplexity_rejected)} articles")

        # STEP 7: Save outputs
        logger.info("\n" + "=" * 80)
        logger.info("STEP 7: Save Results to Excel")
        logger.info("=" * 80)

        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)

        run_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Output 1: Extracted deals
        if extracted_deals:
            deals_file = output_dir / f"hybrid_deals_{timestamp}_{run_id}.xlsx"
            excel_writer = ExcelWriter()
            excel_writer.write(extracted_deals, str(deals_file))
            logger.info(f"✓ Saved {len(extracted_deals)} deals to: {deals_file}")
        else:
            logger.warning("⚠ No deals extracted!")

        # Output 2: Perplexity-rejected URLs (passed keywords but not Perplexity)
        if perplexity_rejected:
            import pandas as pd
            rejected_file = output_dir / f"hybrid_rejected_{timestamp}_{run_id}.xlsx"
            df = pd.DataFrame(perplexity_rejected)
            df.to_excel(rejected_file, index=False)
            logger.info(f"✓ Saved {len(perplexity_rejected)} rejected URLs to: {rejected_file}")

        # Final summary
        logger.info("\n" + "=" * 80)
        logger.info("✅ HYBRID PIPELINE COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"\nResults:")
        logger.info(f"  • Total articles crawled: {len(discovered_urls)}")
        logger.info(f"  • Articles fetched: {len(articles)}")
        logger.info(f"  • Passed keyword filter: {len(passed_articles)}")
        logger.info(f"  • Deals extracted: {len(extracted_deals)}")
        logger.info(f"  • Rejected by Perplexity: {len(perplexity_rejected)}")
        logger.info(f"\nOutputs:")
        if extracted_deals:
            logger.info(f"  1. Deals: {deals_file}")
        if perplexity_rejected:
            logger.info(f"  2. Rejected: {rejected_file}")
        logger.info(f"\n💰 Cost estimate: ~${len(passed_articles) * 0.06:.2f}")
        logger.info(f"   (vs ${len(articles) * 0.06:.2f} without keyword filter)")
        logger.info(f"   Savings: ${(len(articles) - len(passed_articles)) * 0.06:.2f}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Hybrid Pipeline: Keyword Filter + Perplexity")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file"
    )

    args = parser.parse_args()

    # Run pipeline
    pipeline = HybridPipeline(args.config)
    pipeline.run()


if __name__ == "__main__":
    main()
