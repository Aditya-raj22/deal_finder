"""Money/currency parser."""

import re
from decimal import Decimal
from typing import Optional, Tuple

from ..models import Evidence
from ..utils.text import clean_amount_text, extract_snippet


class MoneyParser:
    """Parse monetary amounts and currencies from text."""

    def __init__(self):
        # Currency symbols and codes
        self.currency_map = {
            "$": "USD",
            "USD": "USD",
            "US$": "USD",
            "€": "EUR",
            "EUR": "EUR",
            "£": "GBP",
            "GBP": "GBP",
            "¥": "JPY",
            "JPY": "JPY",
            "CHF": "CHF",
        }

        # Amount patterns
        self.amount_patterns = [
            # $500 million, $500M, $500 mn
            r"([A-Z$€£¥]+)\s*(\d+(?:\.\d+)?)\s*(million|mn|M)\b",
            # $2.5 billion, $2.5B, $2.5 bn
            r"([A-Z$€£¥]+)\s*(\d+(?:\.\d+)?)\s*(billion|bn|B)\b",
            # 500 million USD, 500M USD
            r"(\d+(?:\.\d+)?)\s*(million|mn|M)\s+([A-Z]{3})\b",
            # 2.5 billion EUR, 2.5B EUR
            r"(\d+(?:\.\d+)?)\s*(billion|bn|B)\s+([A-Z]{3})\b",
        ]

        # Compile patterns
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.amount_patterns
        ]

        # Ambiguity patterns
        self.ambiguous_patterns = [
            r"\bup\s+to\b",
            r"\bupto\b",
            r"\bapproximately\b",
            r"\bundisclosed\b",
            r"\bnot\s+disclosed\b",
            r"\brange\b",
            r"\bbetween\b",
        ]

    def _normalize_currency(self, currency_text: str) -> str:
        """Normalize currency symbol/code to standard code."""
        currency_clean = currency_text.strip().upper()
        return self.currency_map.get(currency_clean, currency_clean)

    def _normalize_multiplier(self, multiplier_text: str) -> Decimal:
        """Convert multiplier text to numeric value."""
        multiplier_lower = multiplier_text.lower()
        if multiplier_lower in ["million", "mn", "m"]:
            return Decimal("1")  # Already in millions
        elif multiplier_lower in ["billion", "bn", "b"]:
            return Decimal("1000")  # Convert to millions
        else:
            return Decimal("1")

    def _is_ambiguous(self, text: str) -> bool:
        """Check if amount mention is ambiguous."""
        text_lower = text.lower()
        for pattern in self.ambiguous_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def parse(
        self, text: str
    ) -> Tuple[Optional[Decimal], Optional[str], bool, Optional[Evidence]]:
        """
        Parse monetary amount from text.

        Returns:
            Tuple of (amount_in_millions, currency, needs_review, evidence)
        """
        # Check for ambiguous mentions - but still try to extract the amount
        is_ambiguous = self._is_ambiguous(text)

        # Try each pattern
        for pattern in self.compiled_patterns:
            match = pattern.search(text)
            if match:
                groups = match.groups()

                # Determine currency and amount based on pattern match
                if len(groups) == 3:
                    if groups[0].replace("$", "").replace("€", "").replace("£", "").isdigit():
                        # Pattern: amount multiplier currency
                        amount_str = groups[0]
                        multiplier_str = groups[1]
                        currency_str = groups[2]
                    else:
                        # Pattern: currency amount multiplier
                        currency_str = groups[0]
                        amount_str = groups[1]
                        multiplier_str = groups[2]

                    try:
                        # Parse amount
                        amount = Decimal(amount_str.replace("$", "").replace("€", "").replace("£", ""))
                        multiplier = self._normalize_multiplier(multiplier_str)
                        amount_millions = amount * multiplier

                        # Normalize currency
                        currency = self._normalize_currency(currency_str)

                        # Extract evidence
                        matched_phrase = match.group(0)
                        snippet = extract_snippet(text, matched_phrase)

                        evidence = Evidence(
                            snippet_en=snippet, snippet_original=None, raw_phrase=matched_phrase
                        )

                        return amount_millions, currency, is_ambiguous, evidence

                    except (ValueError, ArithmeticError):
                        continue

        # No amount found
        return None, None, is_ambiguous, None

    def parse_upfront_contingent_total(
        self, text: str
    ) -> Tuple[
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[str],
        bool,
        dict[str, Optional[Evidence]],
    ]:
        """
        Parse upfront, contingent, and total deal values.

        Returns:
            Tuple of (upfront, contingent, total, currency, needs_review, evidence_dict)
        """
        # Simplified implementation - in practice would use more sophisticated patterns
        # to distinguish upfront vs contingent vs total

        upfront = None
        contingent = None
        total = None
        currency = None
        needs_review = False
        evidence_dict = {
            "upfront": None,
            "contingent": None,
            "total": None,
        }

        # Look for "upfront" mentions
        upfront_match = re.search(
            r"upfront.*?([A-Z$€£¥]+)?\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B|mn|bn)",
            text,
            re.IGNORECASE,
        )
        if upfront_match:
            amount, curr, rev, evid = self.parse(upfront_match.group(0))
            if amount:
                upfront = amount
                currency = curr
                evidence_dict["upfront"] = evid
                needs_review = needs_review or rev

        # Look for "milestone" or "contingent" mentions
        contingent_match = re.search(
            r"(milestone|contingent|potential).*?([A-Z$€£¥]+)?\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B|mn|bn)",
            text,
            re.IGNORECASE,
        )
        if contingent_match:
            amount, curr, rev, evid = self.parse(contingent_match.group(0))
            if amount:
                contingent = amount
                if not currency:
                    currency = curr
                evidence_dict["contingent"] = evid
                needs_review = needs_review or rev

        # Look for "total" mentions
        total_match = re.search(
            r"(total|aggregate).*?([A-Z$€£¥]+)?\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B|mn|bn)",
            text,
            re.IGNORECASE,
        )
        if total_match:
            amount, curr, rev, evid = self.parse(total_match.group(0))
            if amount:
                total = amount
                if not currency:
                    currency = curr
                evidence_dict["total"] = evid
                needs_review = needs_review or rev

        # If no specific mentions, try to parse any amount as total
        if not upfront and not contingent and not total:
            amount, curr, rev, evid = self.parse(text)
            if amount:
                total = amount
                currency = curr
                evidence_dict["total"] = evid
                needs_review = rev

        return upfront, contingent, total, currency, needs_review, evidence_dict
