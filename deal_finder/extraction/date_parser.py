"""Date parser with timezone handling."""

import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from dateutil import parser as dateutil_parser

from ..models import Evidence
from ..utils.text import extract_snippet


class DateParser:
    """Parse dates from text with timezone handling."""

    def __init__(self):
        # Common date patterns
        self.date_patterns = [
            # YYYY-MM-DD
            r"\b(\d{4})-(\d{2})-(\d{2})\b",
            # Month DD, YYYY (full names)
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
            # Month DD, YYYY (abbreviated names)
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})\b",
            # DD Month YYYY
            r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
            # MM/DD/YYYY
            r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
            # DD.MM.YYYY
            r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b",
        ]

    def parse(self, text: str) -> Tuple[Optional[datetime], bool, Optional[Evidence]]:
        """
        Parse date from text.

        Returns:
            Tuple of (datetime in UTC, needs_review, evidence)
        """
        # Try each pattern
        for pattern in self.date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(0)
                try:
                    # Parse date
                    dt = dateutil_parser.parse(date_str)

                    # Convert to UTC if timezone-aware
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(timezone.utc)
                    else:
                        # Assume UTC if no timezone
                        dt = dt.replace(tzinfo=timezone.utc)

                    # Extract evidence
                    snippet = extract_snippet(text, date_str)
                    evidence = Evidence(
                        snippet_en=snippet, snippet_original=None, raw_phrase=date_str
                    )

                    return dt, False, evidence

                except (ValueError, OverflowError):
                    continue

        # Try dateutil parser as fallback
        try:
            dt = dateutil_parser.parse(text, fuzzy=True)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)

            # Mark as needs review since we used fuzzy parsing
            evidence = Evidence(snippet_en=text[:200], snippet_original=None, raw_phrase=text[:50])

            return dt, True, evidence

        except (ValueError, OverflowError):
            pass

        # No date found - return current date for review
        # Note: In practice this should still fail validation, but we try to extract
        return None, True, None  # Keep as None - date is required field

    def parse_to_date(self, text: str) -> Tuple[Optional[datetime], bool, Optional[Evidence]]:
        """Parse and return date object (YYYY-MM-DD)."""
        dt, needs_review, evidence = self.parse(text)
        if dt:
            # Convert to date (drop time component)
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt, needs_review, evidence
