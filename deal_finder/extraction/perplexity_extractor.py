"""Perplexity-based deal extractor."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from ..models import DealTypeDetailed, DevelopmentStage, Evidence
from ..perplexity_client import PerplexityClient

logger = logging.getLogger(__name__)


class PerplexityExtractor:
    """Extract deal information using Perplexity API."""

    def __init__(self, api_key: Optional[str] = None, batch_size: int = 5):
        """Initialize Perplexity extractor.

        Args:
            api_key: Perplexity API key
            batch_size: Number of articles to process per API call (3-5 recommended)
        """
        self.client = PerplexityClient(api_key)
        self.batch_size = batch_size

    def extract_batch(
        self,
        articles: List[dict],
        ta_vocab: dict
    ) -> List[Optional[dict]]:
        """Extract deals from a batch of articles.

        Args:
            articles: List of dicts with keys: url, title, content
            ta_vocab: Therapeutic area vocabulary

        Returns:
            List of extracted deal data (same length as articles, None for failed extractions)
        """
        if not articles:
            return []

        # Process in batches to stay within API limits
        all_results = []
        for i in range(0, len(articles), self.batch_size):
            batch = articles[i:i + self.batch_size]
            logger.info(f"Extracting batch {i//self.batch_size + 1}: {len(batch)} articles")

            try:
                batch_results = self.client.extract_deals_batch(batch, ta_vocab)

                # Map results back to articles (handle mismatches)
                results_map = {r.get("url"): r for r in batch_results if r}
                for article in batch:
                    url = article.get("url")
                    result = results_map.get(url)
                    all_results.append(result)

            except Exception as e:
                logger.error(f"Batch extraction failed: {e}")
                # Add None for each article in failed batch
                all_results.extend([None] * len(batch))

        return all_results

    def parse_extracted_deal(
        self,
        extraction: dict,
        ta_name: str
    ) -> Optional[dict]:
        """Parse Perplexity extraction into standardized format.

        Args:
            extraction: Raw extraction dict from Perplexity
            ta_name: Therapeutic area name

        Returns:
            Standardized deal dict or None if extraction invalid
        """
        if not extraction:
            return None

        # Check TA match - RELAXED to prevent false negatives
        # Instead of excluding, we flag TA mismatches for manual review
        ta_match = extraction.get("therapeutic_area_match", False)
        if not ta_match:
            logger.info(f"TA mismatch (including for review): {extraction.get('url')}")
            needs_review = True  # Flag for review but INCLUDE the deal
        else:
            needs_review = False

        # Check confidence - Accept all, but flag low confidence
        confidence = extraction.get("confidence", "unknown")
        if confidence in ["low", "very low", "unknown"]:
            logger.info(f"Low/unknown confidence for {extraction.get('url')}: {confidence}")
            needs_review = True  # Flag for review

        # Parse parties
        parties = extraction.get("parties", {})
        acquirer = parties.get("acquirer") or parties.get("partner1")
        target = parties.get("target") or parties.get("partner2")

        if not acquirer or not target:
            logger.debug(f"Missing parties in {extraction.get('url')}")
            return None

        # Parse deal type
        deal_type_str = extraction.get("deal_type", "unknown").lower()
        deal_type_map = {
            "m&a": DealTypeDetailed.MA,
            "ma": DealTypeDetailed.MA,
            "merger": DealTypeDetailed.MA,
            "acquisition": DealTypeDetailed.MA,
            "partnership": DealTypeDetailed.PARTNERSHIP,
            "collaboration": DealTypeDetailed.PARTNERSHIP,
            "licensing": DealTypeDetailed.LICENSING,
            "license": DealTypeDetailed.LICENSING,
            "option-to-license": DealTypeDetailed.OPTION_TO_LICENSE,
            "option": DealTypeDetailed.OPTION_TO_LICENSE,
        }
        deal_type = deal_type_map.get(deal_type_str, DealTypeDetailed.PARTNERSHIP)

        # Parse date - use article published date as fallback
        date_str = extraction.get("date_announced")
        if not date_str:
            # No date extracted - use article published date if available
            article_pub_date = extraction.get("article_published_date")
            if article_pub_date:
                logger.info(f"No announcement date found, using article date: {article_pub_date}")
                date_str = article_pub_date
                needs_review = True  # Flag for manual review
            else:
                logger.debug(f"Missing date in {extraction.get('url')}")
                return None

        try:
            date_announced = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            logger.debug(f"Invalid date format: {date_str}")
            return None

        # Parse money
        money = extraction.get("money", {})
        upfront = money.get("upfront_value")
        contingent = money.get("contingent_payment")
        total = money.get("total_deal_value")
        currency = money.get("currency", "USD")

        # Convert to Decimal
        upfront_usd = Decimal(str(upfront)) if upfront else None
        contingent_usd = Decimal(str(contingent)) if contingent else None
        total_usd = Decimal(str(total)) if total else None

        # Calculate upfront percentage
        upfront_pct = None
        if upfront_usd and total_usd and total_usd > 0:
            upfront_pct = round((upfront_usd / total_usd) * Decimal("100"), 1)

        # Parse stage - only early stages are in the enum
        stage_str = extraction.get("stage", "unknown").lower()
        stage_map = {
            "preclinical": DevelopmentStage.PRECLINICAL,
            "pre-clinical": DevelopmentStage.PRECLINICAL,
            "phase 1": DevelopmentStage.PHASE_1,
            "phase i": DevelopmentStage.PHASE_1,
            "phase1": DevelopmentStage.PHASE_1,
            "first-in-human": DevelopmentStage.FIRST_IN_HUMAN,
            "fih": DevelopmentStage.FIRST_IN_HUMAN,
        }
        stage = stage_map.get(stage_str)

        # Check if stage is later than early stage (phase 2+, approved)
        late_stage_keywords = ["phase 2", "phase ii", "phase2", "phase 3", "phase iii", "phase3", "approved", "marketed"]
        if stage_str in late_stage_keywords:
            logger.info(f"Late stage deal (not early stage): {stage_str} at {extraction.get('url')}")
            return None  # Filter out late-stage deals

        if not stage:
            # Default to preclinical if uncertain (to avoid false negatives)
            stage = DevelopmentStage.PRECLINICAL
            needs_review = True

        # Parse asset
        asset_focus = extraction.get("asset_focus", "Undisclosed")
        if not asset_focus or asset_focus == "null":
            asset_focus = "Undisclosed"
            needs_review = True

        # Parse geography
        geography = extraction.get("geography")

        # Create evidence
        key_evidence = extraction.get("key_evidence", "")
        evidence = Evidence(
            snippet_en=key_evidence[:500] if key_evidence else "No evidence provided",
            snippet_original=None,
            raw_phrase=key_evidence[:200] if key_evidence else "No evidence"
        )

        return {
            "url": extraction.get("url"),
            "acquirer": acquirer,
            "target": target,
            "deal_type": deal_type,
            "date_announced": date_announced,
            "upfront_value_usd": upfront_usd,
            "contingent_payment_usd": contingent_usd,
            "total_deal_value_usd": total_usd,
            "upfront_pct_total": upfront_pct,
            "currency": currency,
            "stage": stage,
            "asset_focus": asset_focus,
            "therapeutic_area": ta_name,
            "geography": geography,
            "needs_review": needs_review,
            "evidence": evidence,
            "confidence": extraction.get("confidence", "medium")
        }
