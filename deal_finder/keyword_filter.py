"""
Keyword-based pre-filter for articles before sending to Perplexity.

This module checks if articles contain relevant keywords (TA + stage + deal)
to reduce API costs by only sending relevant articles for extraction.
"""

import logging
import re
from typing import List, Dict, Optional
from multiprocessing import Pool, cpu_count

logger = logging.getLogger(__name__)


class KeywordFilter:
    """Filter articles by keyword matching (TA + stage + deal keywords)."""

    def __init__(
        self,
        ta_keywords: List[str],
        stage_keywords: List[str],
        deal_keywords: List[str],
        require_deal_keyword: bool = True,
        min_ta_matches: int = 1,
        min_deal_matches: int = 1,
        require_money_mention: bool = False
    ):
        """
        Initialize keyword filter.

        Args:
            ta_keywords: Therapeutic area keywords
            stage_keywords: Development stage keywords
            deal_keywords: Deal-related keywords
            require_deal_keyword: If True, article MUST have a deal keyword
            min_ta_matches: Minimum number of TA keywords required
            min_deal_matches: Minimum number of deal keywords required
            require_money_mention: If True, article MUST mention dollar amounts
        """
        self.ta_keywords = [kw.lower() for kw in ta_keywords]
        self.stage_keywords = [kw.lower() for kw in stage_keywords]
        self.deal_keywords = [kw.lower() for kw in deal_keywords]
        self.require_deal_keyword = require_deal_keyword
        self.min_ta_matches = min_ta_matches
        self.min_deal_matches = min_deal_matches
        self.require_money_mention = require_money_mention

        # Regex for detecting money mentions (relaxed)
        # Matches: $50M, €100M, "dollar", "euro", "USD", "EUR", etc.
        self.money_pattern = re.compile(
            r'(?:[\$€£¥]\s*\d+(?:\.\d+)?(?:\s*)?(?:million|billion|m|b|mn|bn|mm)?|'
            r'\b(?:dollar|euro|usd|eur|gbp)\b)',
            re.IGNORECASE
        )

        logger.info(f"KeywordFilter initialized:")
        logger.info(f"  TA keywords: {len(self.ta_keywords)}")
        logger.info(f"  Stage keywords: {len(self.stage_keywords)}")
        logger.info(f"  Deal keywords: {len(self.deal_keywords)}")
        logger.info(f"  Require deal keyword: {require_deal_keyword}")
        logger.info(f"  Min TA matches: {min_ta_matches}")
        logger.info(f"  Min deal matches: {min_deal_matches}")
        logger.info(f"  Require money mention: {require_money_mention}")

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

        # Check for money mentions
        money_mentions = self.money_pattern.findall(text)
        has_money = len(money_mentions) > 0

        # Check if passes filter
        has_enough_ta = len(ta_matches) >= self.min_ta_matches
        has_stage = len(stage_matches) > 0
        has_enough_deal = len(deal_matches) >= self.min_deal_matches

        # Determine if passed
        if self.require_deal_keyword:
            # Base requirements
            passed = has_enough_ta and has_stage and has_enough_deal

            # Add money requirement if enabled
            if self.require_money_mention:
                passed = passed and has_money

            if not passed:
                missing = []
                if not has_enough_ta:
                    missing.append(f"TA (need {self.min_ta_matches}, got {len(ta_matches)})")
                if not has_stage:
                    missing.append("stage")
                if not has_enough_deal:
                    missing.append(f"deal (need {self.min_deal_matches}, got {len(deal_matches)})")
                if self.require_money_mention and not has_money:
                    missing.append("money mention")
                reason = f"Missing: {', '.join(missing)}"
            else:
                money_str = f", ${money_mentions[0]}" if has_money else ""
                reason = f"Matched: {len(ta_matches)} TA, {len(stage_matches)} stage, {len(deal_matches)} deal{money_str}"
        else:
            # Relaxed: just need TA + stage + optional money
            passed = has_enough_ta and has_stage

            # Add money requirement if enabled
            if self.require_money_mention:
                passed = passed and has_money

            if not passed:
                missing = []
                if not has_enough_ta:
                    missing.append(f"TA (need {self.min_ta_matches}, got {len(ta_matches)})")
                if not has_stage:
                    missing.append("stage")
                if self.require_money_mention and not has_money:
                    missing.append("money mention")
                reason = f"Missing: {', '.join(missing)}"
            else:
                money_str = f", ${money_mentions[0]}" if has_money else ""
                reason = f"Matched: {len(ta_matches)} TA, {len(stage_matches)} stage{money_str}"

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
        # Use parallel processing for large batches
        if len(articles) >= 5000:
            num_workers = min(cpu_count(), 8)
            chunk_size = max(100, len(articles) // (num_workers * 4))
            logger.info(f"Using {num_workers} workers for parallel filtering...")

            with Pool(num_workers) as pool:
                results = pool.map(self._filter_worker, articles, chunksize=chunk_size)

            passed = [art for art, res in results if res["passed"]]
            failed = [art for art, res in results if not res["passed"]]

            # Add match metadata
            for i, (art, res) in enumerate(results):
                if res["passed"]:
                    passed[i - len([r for r in results[:i] if not r[1]["passed"]])]["keyword_matches"] = {
                        "ta": res["ta_keywords_matched"],
                        "stage": res["stage_keywords_matched"],
                        "deal": res["deal_keywords_matched"]
                    }
                else:
                    failed[i - len([r for r in results[:i] if r[1]["passed"]])]["filter_reason"] = res["reason"]
        else:
            # Serial processing for small batches
            passed = []
            failed = []

            for article in articles:
                url = article.get("url", "unknown")
                content = article.get("content", "")

                result = self.matches(content)

                if result["passed"]:
                    article["keyword_matches"] = {
                        "ta": result["ta_keywords_matched"],
                        "stage": result["stage_keywords_matched"],
                        "deal": result["deal_keywords_matched"]
                    }
                    passed.append(article)
                    logger.debug(f"PASS: {url} - {result['reason']}")
                else:
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

    def _filter_worker(self, article: Dict) -> tuple:
        """Worker function for multiprocessing."""
        content = article.get("content", "")
        result = self.matches(content)
        return (article, result)


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
