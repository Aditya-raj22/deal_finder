"""
Keyword-based pre-filter for articles before sending to Perplexity.

This module checks if articles contain relevant keywords (TA + stage + deal)
to reduce API costs by only sending relevant articles for extraction.
"""

import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class KeywordFilter:
    """Filter articles by keyword matching (TA + stage + deal keywords)."""

    def __init__(
        self,
        ta_keywords: List[str],
        stage_keywords: List[str],
        deal_keywords: List[str],
        require_deal_keyword: bool = True,
        min_ta_matches: int = 1
    ):
        """
        Initialize keyword filter.

        Args:
            ta_keywords: Therapeutic area keywords
            stage_keywords: Development stage keywords
            deal_keywords: Deal-related keywords
            require_deal_keyword: If True, article MUST have a deal keyword
            min_ta_matches: Minimum number of TA keywords required
        """
        self.ta_keywords = [kw.lower() for kw in ta_keywords]
        self.stage_keywords = [kw.lower() for kw in stage_keywords]
        self.deal_keywords = [kw.lower() for kw in deal_keywords]
        self.require_deal_keyword = require_deal_keyword
        self.min_ta_matches = min_ta_matches

        logger.info(f"KeywordFilter initialized:")
        logger.info(f"  TA keywords: {len(self.ta_keywords)}")
        logger.info(f"  Stage keywords: {len(self.stage_keywords)}")
        logger.info(f"  Deal keywords: {len(self.deal_keywords)}")
        logger.info(f"  Require deal keyword: {require_deal_keyword}")
        logger.info(f"  Min TA matches: {min_ta_matches}")

    def matches(self, text: str) -> Dict[str, any]:
        """
        Check if article text matches filter criteria.

        Args:
            text: Article text content

        Returns:
            Dict with:
                - "passed": bool (True if article passes filter)
                - "ta_keywords_matched": List of TA keywords found
                - "stage_keywords_matched": List of stage keywords found
                - "deal_keywords_matched": List of deal keywords found
                - "reason": str (why it passed/failed)
        """
        text_lower = text.lower()

        # Find matching keywords
        ta_matches = self._find_matches(text_lower, self.ta_keywords)
        stage_matches = self._find_matches(text_lower, self.stage_keywords)
        deal_matches = self._find_matches(text_lower, self.deal_keywords)

        # Check if passes filter
        has_enough_ta = len(ta_matches) >= self.min_ta_matches
        has_stage = len(stage_matches) > 0
        has_deal = len(deal_matches) > 0

        # Determine if passed
        if self.require_deal_keyword:
            passed = has_enough_ta and has_stage and has_deal
            if not passed:
                missing = []
                if not has_enough_ta:
                    missing.append(f"TA (need {self.min_ta_matches}, got {len(ta_matches)})")
                if not has_stage:
                    missing.append("stage")
                if not has_deal:
                    missing.append("deal")
                reason = f"Missing: {', '.join(missing)}"
            else:
                reason = f"Matched: {len(ta_matches)} TA, {len(stage_matches)} stage, {len(deal_matches)} deal keywords"
        else:
            # Relaxed: just need TA + stage (useful for very broad filtering)
            passed = has_enough_ta and has_stage
            if not passed:
                missing = []
                if not has_enough_ta:
                    missing.append(f"TA (need {self.min_ta_matches}, got {len(ta_matches)})")
                if not has_stage:
                    missing.append("stage")
                reason = f"Missing: {', '.join(missing)}"
            else:
                reason = f"Matched: {len(ta_matches)} TA, {len(stage_matches)} stage keywords"

        return {
            "passed": passed,
            "ta_keywords_matched": ta_matches,
            "stage_keywords_matched": stage_matches,
            "deal_keywords_matched": deal_matches,
            "reason": reason
        }

    def _find_matches(self, text: str, keywords: List[str]) -> List[str]:
        """
        Find which keywords appear in text.

        Args:
            text: Lowercase article text
            keywords: List of lowercase keywords

        Returns:
            List of keywords that were found
        """
        matches = []
        for keyword in keywords:
            # Use word boundaries for exact matching
            # This prevents "immune" from matching "immunization" incorrectly
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(keyword)

        return matches

    def filter_articles(self, articles: List[Dict]) -> Dict[str, List]:
        """
        Filter a list of articles.

        Args:
            articles: List of dicts with "url" and "content" keys

        Returns:
            Dict with:
                - "passed": Articles that passed filter
                - "failed": Articles that failed filter
                - "stats": Summary statistics
        """
        passed = []
        failed = []

        for article in articles:
            url = article.get("url", "unknown")
            content = article.get("content", "")

            result = self.matches(content)

            if result["passed"]:
                # Add match info to article
                article["keyword_matches"] = {
                    "ta": result["ta_keywords_matched"],
                    "stage": result["stage_keywords_matched"],
                    "deal": result["deal_keywords_matched"]
                }
                passed.append(article)
                logger.debug(f"PASS: {url} - {result['reason']}")
            else:
                # Store reason for failure
                article["filter_reason"] = result["reason"]
                failed.append(article)
                logger.debug(f"FAIL: {url} - {result['reason']}")

        # Calculate stats
        stats = {
            "total": len(articles),
            "passed": len(passed),
            "failed": len(failed),
            "pass_rate": f"{len(passed)/len(articles)*100:.1f}%" if articles else "0%"
        }

        logger.info(f"Filter results: {stats['passed']}/{stats['total']} passed ({stats['pass_rate']})")

        return {
            "passed": passed,
            "failed": failed,
            "stats": stats
        }


class DateFilter:
    """Filter articles by date range (from sitemap metadata or article text)."""

    def __init__(self, start_date: str, end_date: str):
        """
        Initialize date filter.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        from datetime import datetime

        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        logger.info(f"DateFilter: {start_date} to {end_date}")

    def in_range(self, article_date: str) -> bool:
        """
        Check if article date is in range.

        Args:
            article_date: Article published date (YYYY-MM-DD or datetime string)

        Returns:
            True if in range
        """
        from datetime import datetime

        try:
            # Try parsing as date
            if "T" in article_date:
                # ISO format with time
                date = datetime.fromisoformat(article_date.replace("Z", "+00:00")).date()
            else:
                # Just date
                date = datetime.strptime(article_date, "%Y-%m-%d").date()

            return self.start_date <= date <= self.end_date

        except Exception as e:
            logger.warning(f"Failed to parse date '{article_date}': {e}")
            return False  # Exclude if date is unparseable
