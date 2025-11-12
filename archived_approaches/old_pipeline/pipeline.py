"""Main pipeline orchestrator."""

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from bs4 import BeautifulSoup

from .classification import DealTypeClassifier, StageClassifier, TAMatcher
from .config_loader import Config, load_aliases, load_ta_vocab
from .deduplication import Deduplicator
from .discovery import DealCrawler
from .extraction import AssetExtractor, DateParser, MoneyParser, PartyExtractor
from .extraction.perplexity_extractor import PerplexityExtractor
from .models import Deal, DealTypeDetailed, DevelopmentStage, FieldEvidence
from .monitoring import DataQualityChecker, ProductionMonitor
from .normalization import CompanyCanonicalizer, FXConverter, GeographyResolver
from .output import EvidenceLogger, ExcelWriter
from .translation import Translator
from .utils.selenium_client import SeleniumWebClient

logger = logging.getLogger(__name__)


class DealPipeline:
    """Main deal finding pipeline."""

    def __init__(self, config: Config):
        self.config = config
        self.run_id = str(uuid.uuid4())[:8]

        # Load TA vocab and aliases
        self.ta_vocab = load_ta_vocab(config)
        self.aliases = load_aliases(config)

        # Initialize monitoring
        self.quality_checker = DataQualityChecker()
        self.monitor = ProductionMonitor(config.OUTPUT_DIR)
        self.start_time = None

        # Initialize components
        self.selenium_client = SeleniumWebClient(
            headless=True,
            timeout=config.TIMEOUT_SECONDS,
        )

        self.crawler = DealCrawler(config, self.selenium_client)
        self.translator = Translator(
            target_language=config.LANGUAGE_POLICY.EXTRACTION_LANGUAGE,
            provider=config.LANGUAGE_POLICY.MT_PROVIDER,
            cache_enabled=config.LANGUAGE_POLICY.CACHE_TRANSLATIONS,
        )

        # Check if Perplexity is available for extraction
        self.use_perplexity_extraction = bool(os.getenv("PERPLEXITY_API_KEY"))
        if self.use_perplexity_extraction:
            self.perplexity_extractor = PerplexityExtractor(batch_size=5)
            logger.info("Using Perplexity for max accuracy extraction")
        else:
            self.perplexity_extractor = None
            logger.info("Using regex-based extraction (fallback mode)")

        # Classifiers (only used in fallback mode)
        self.stage_classifier = StageClassifier(config.EARLY_STAGE_ALLOWED)
        self.ta_matcher = TAMatcher(self.ta_vocab)
        self.deal_type_classifier = DealTypeClassifier()

        # Extractors (only used in fallback mode)
        self.money_parser = MoneyParser()
        self.date_parser = DateParser()
        self.party_extractor = PartyExtractor()
        self.asset_extractor = AssetExtractor()

        # Normalizers
        self.fx_converter = FXConverter(base_currency=config.CURRENCY_BASE)
        self.company_canonicalizer = CompanyCanonicalizer(self.aliases)
        self.geography_resolver = GeographyResolver()

        # Deduplicator
        self.deduplicator = Deduplicator()

        # Output writers
        self.excel_writer = ExcelWriter()
        self.evidence_logger = EvidenceLogger()

    def process_article(self, url: str, html_content: str) -> Optional[Deal]:
        """Process a single article and extract deal if present."""
        try:
            # Parse HTML
            soup = BeautifulSoup(html_content, "lxml")
            text = soup.get_text(separator=" ", strip=True)

            # Detect language and translate if needed
            text_en, text_original, detected_lang = self.translator.translate_with_original(text)

            # Classify stage (includes ambiguous with needs_review=True)
            stage, stage_needs_review, stage_evidence = self.stage_classifier.classify(text_en)
            if not stage:
                logger.debug(f"No early stage found in {url}")
                return None  # Hard exclusion only for confirmed phase 2+

            # Match TA (includes ambiguous with needs_review=True)
            ta_match, ta_needs_review, ta_evidence = self.ta_matcher.match(text_en)
            if not ta_match:
                logger.debug(f"No TA match in {url}")
                return None  # Hard exclusion only for confirmed non-match

            # Classify deal type (includes ambiguous with needs_review=True)
            deal_type, dt_needs_review, dt_evidence = self.deal_type_classifier.classify(text_en)
            if not deal_type:
                logger.debug(f"No deal type found in {url}")
                return None  # Should not happen with new defaults

            # Extract date
            date_dt, date_needs_review, date_evidence = self.date_parser.parse_to_date(text_en)
            if not date_dt:
                logger.debug(f"No date found in {url}")
                return None

            # Extract parties
            if deal_type == DealTypeDetailed.MA:
                target, target_nr, target_ev = self.party_extractor.extract_target(text_en)
                acquirer, acquirer_nr, acquirer_ev = self.party_extractor.extract_acquirer(text_en)
            else:
                partners, partners_nr, partners_ev = self.party_extractor.extract_partners(text_en)
                if partners:
                    target, acquirer = partners
                    target_ev = partners_ev.get("partner1") if partners_ev else None
                    acquirer_ev = partners_ev.get("partner2") if partners_ev else None
                    target_nr = acquirer_nr = partners_nr
                else:
                    target = acquirer = None
                    target_ev = acquirer_ev = None
                    target_nr = acquirer_nr = True

            if not target or not acquirer:
                logger.debug(f"Could not extract parties from {url}")
                return None

            # Canonicalize company names
            target_canonical = self.company_canonicalizer.canonicalize(target)
            acquirer_canonical = self.company_canonicalizer.canonicalize(acquirer)

            # Extract asset
            asset, asset_nr, asset_ev = self.asset_extractor.extract(text_en)
            if not asset:
                asset = "Undisclosed"
                asset_nr = True

            # Extract money
            (
                upfront,
                contingent,
                total,
                currency,
                money_nr,
                money_ev,
            ) = self.money_parser.parse_upfront_contingent_total(text_en)

            # Convert to USD if needed
            upfront_usd = contingent_usd = total_usd = None
            fx_rate = fx_source = None

            if currency and currency != "USD":
                if upfront:
                    upfront_usd, fx_rate, fx_source = self.fx_converter.convert(
                        upfront, currency, date_dt.date()
                    )
                if contingent:
                    contingent_usd, _, _ = self.fx_converter.convert(
                        contingent, currency, date_dt.date()
                    )
                if total:
                    total_usd, _, _ = self.fx_converter.convert(total, currency, date_dt.date())
            else:
                upfront_usd = upfront
                contingent_usd = contingent
                total_usd = total
                fx_rate = Decimal("1.0") if currency else None
                fx_source = "USD" if currency else None

            # Calculate upfront %
            upfront_pct = None
            if upfront_usd and total_usd and total_usd > 0:
                upfront_pct = round((upfront_usd / total_usd) * Decimal("100"), 1)

            # Resolve geography
            geography = self.geography_resolver.resolve(text_en, target)
            if not geography:
                geography = self.geography_resolver.resolve_from_url(url)

            # Build evidence
            evidence = FieldEvidence(
                date_announced=date_evidence,
                target=target_ev,
                acquirer=acquirer_ev,
                upfront_value=money_ev.get("upfront"),
                contingent_payment=money_ev.get("contingent"),
                total_deal_value=money_ev.get("total"),
                stage=stage_evidence,
                therapeutic_area=ta_evidence,
                asset_focus=asset_ev,
                deal_type=dt_evidence,
            )

            # Determine needs_review
            needs_review = (
                stage_needs_review
                or ta_needs_review
                or dt_needs_review
                or date_needs_review
                or target_nr
                or acquirer_nr
                or asset_nr
                or money_nr
            )

            # Create deal
            deal = Deal(
                date_announced=date_dt.date(),
                target=target_canonical,
                acquirer=acquirer_canonical,
                stage=stage,
                therapeutic_area=self.ta_vocab["therapeutic_area"],
                asset_focus=asset,
                deal_type_detailed=deal_type,
                source_url=url,
                needs_review=needs_review,
                upfront_value_usd=upfront_usd,
                contingent_payment_usd=contingent_usd,
                total_deal_value_usd=total_usd,
                upfront_pct_total=upfront_pct,
                geography=geography,
                detected_currency=currency,
                fx_rate=fx_rate,
                fx_source=fx_source,
                evidence=evidence,
                inclusion_reason="Matched stage, TA, and deal type criteria",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
            )

            return deal

        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return None

    def run_discovery_cycle(self) -> List[Deal]:
        """Run one discovery cycle."""
        logger.info("Starting discovery cycle")

        # Discover URLs (exhaustive crawl returns ALL articles from sites)
        max_articles = 1000 if self.crawler.use_exhaustive else 100
        discovered = self.crawler.discover(self.ta_vocab, max_results=max_articles)

        if self.use_perplexity_extraction:
            return self._process_articles_batch(discovered)
        else:
            return self._process_articles_sequential(discovered)

    def _process_articles_batch(self, discovered: List[dict]) -> List[Deal]:
        """Process articles using batched Perplexity extraction."""
        total_articles = len(discovered)
        logger.info(f"Fetching {total_articles} articles for batch extraction")

        # Fetch all articles first with progress tracking
        articles = []
        fetch_failures = 0
        for i, article_meta in enumerate(discovered, 1):
            url = article_meta["url"]

            # Log progress every 50 articles
            if i % 50 == 0 or i == 1:
                logger.info(f"Progress: {i}/{total_articles} articles fetched ({fetch_failures} failures)")

            html = self.selenium_client.fetch(url)
            if not html:
                fetch_failures += 1
                logger.warning(f"Failed to fetch: {url}")
                continue

            # Parse HTML to text
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(separator=" ", strip=True)

            # Skip articles with very little content
            if len(text) < 500:
                logger.debug(f"Skipping (too short): {url}")
                continue

            articles.append({
                "url": url,
                "title": article_meta.get("title", ""),
                "content": text[:20000]  # Limit to 20k chars per article
            })

        logger.info(f"Successfully fetched {len(articles)}/{total_articles} articles ({fetch_failures} failures)")
        logger.info(f"Starting Perplexity extraction in batches of 5...")

        # Batch extract using Perplexity
        extractions = self.perplexity_extractor.extract_batch(articles, self.ta_vocab)

        # Convert extractions to Deal objects
        deals = []
        for extraction in extractions:
            if not extraction:
                continue

            parsed = self.perplexity_extractor.parse_extracted_deal(
                extraction,
                self.ta_vocab["therapeutic_area"]
            )
            if not parsed:
                continue

            # Canonicalize company names
            target_canonical = self.company_canonicalizer.canonicalize(parsed["target"])
            acquirer_canonical = self.company_canonicalizer.canonicalize(parsed["acquirer"])

            # Create Deal object
            deal = Deal(
                date_announced=parsed["date_announced"],
                target=target_canonical,
                acquirer=acquirer_canonical,
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
                inclusion_reason=f"Perplexity extraction (confidence: {parsed['confidence']})",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
            )

            deals.append(deal)
            logger.info(f"Extracted deal: {deal.target} + {deal.acquirer} ({deal.deal_type_detailed})")

        logger.info(f"Batch extraction complete: {len(deals)} deals from {len(articles)} articles")
        return deals

    def _process_articles_sequential(self, discovered: List[dict]) -> List[Deal]:
        """Process articles sequentially using regex extraction (fallback)."""
        deals = []
        for article_meta in discovered:
            url = article_meta["url"]
            logger.info(f"Processing {url}")

            # Fetch article
            html = self.selenium_client.fetch(url)
            if not html:
                continue

            # Process article
            deal = self.process_article(url, html)
            if deal:
                deals.append(deal)
                logger.info(f"Extracted deal: {deal.target} + {deal.acquirer}")

        return deals

    def run(self) -> None:
        """Run full pipeline with convergence and monitoring."""
        self.start_time = time.time()
        logger.info(f"Starting deal finder pipeline [run_id: {self.run_id}]")

        all_deals = []
        dry_runs = 0
        cycle = 0

        try:
            while dry_runs < self.config.DRY_RUNS_TO_CONVERGE:
                cycle += 1
                logger.info(f"Cycle {cycle}, dry_runs={dry_runs}")

                # Run discovery
                new_deals = self.run_discovery_cycle()

                # Deduplicate against existing deals
                unique_new_deals = []
                for deal in new_deals:
                    if not self.deduplicator.is_duplicate(deal, all_deals):
                        unique_new_deals.append(deal)

                logger.info(f"Found {len(unique_new_deals)} new unique deals")

                if len(unique_new_deals) == 0:
                    dry_runs += 1
                else:
                    dry_runs = 0
                    all_deals.extend(unique_new_deals)

            logger.info(f"Pipeline converged after {cycle} cycles")
            logger.info(f"Total deals found: {len(all_deals)}")

            # Final deduplication
            all_deals = self.deduplicator.deduplicate(all_deals)
            logger.info(f"After final dedup: {len(all_deals)} deals")

            # Data quality checks
            quality_stats = self.quality_checker.check_dataset(all_deals)
            logger.info(f"Quality check: {quality_stats['status']}")

            # Write outputs
            output_excel = f"{self.config.OUTPUT_DIR}/deals_{self.run_id}.xlsx"
            output_evidence = f"{self.config.OUTPUT_DIR}/evidence_{self.run_id}.jsonl"

            self.excel_writer.write(all_deals, output_excel)
            self.evidence_logger.write(all_deals, output_evidence)

            logger.info(f"Wrote Excel: {output_excel}")
            logger.info(f"Wrote evidence log: {output_evidence}")

            # Log metrics
            duration = time.time() - self.start_time
            self.monitor.log_run(
                run_id=self.run_id,
                config=self.config.dict(),
                stats=quality_stats,
                duration_seconds=duration,
                status="SUCCESS",
            )

            # Alert if quality issues
            if hasattr(self.config, 'ENABLE_ALERTS') and self.config.ENABLE_ALERTS:
                self.monitor.alert_if_needed(quality_stats)

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            duration = time.time() - self.start_time if self.start_time else 0
            self.monitor.log_run(
                run_id=self.run_id,
                config=self.config.dict(),
                stats={"status": "ERROR", "message": str(e)},
                duration_seconds=duration,
                status="FAILED",
            )
            raise
        finally:
            # Cleanup Selenium browser
            self.selenium_client.close()
