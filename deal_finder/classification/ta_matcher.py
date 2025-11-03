"""Therapeutic Area matcher."""

import re
from typing import Optional, Tuple

from ..models import Evidence
from ..utils.text import extract_snippet


class TAMatcher:
    """Match therapeutic area from text using vocabulary rules."""

    def __init__(self, vocab: dict):
        self.vocab = vocab
        self.ta_name = vocab["therapeutic_area"]

        # Build expanded includes with synonyms
        self.includes_expanded = set()
        for term in vocab.get("includes", []):
            self.includes_expanded.add(term.lower())
            # Add synonyms
            for canonical, synonyms in vocab.get("synonyms", {}).items():
                if canonical.lower() == term.lower():
                    self.includes_expanded.update(s.lower() for s in synonyms)

        self.excludes = set(term.lower() for term in vocab.get("excludes", []))

        # Compile regex patterns
        self.include_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in vocab.get("regex", {}).get("include_patterns", [])
        ]
        self.exclude_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in vocab.get("regex", {}).get("exclude_patterns", [])
        ]

    def match(
        self, text: str, require_explicit: bool = True
    ) -> Tuple[bool, bool, Optional[Evidence]]:
        """
        Match therapeutic area in text.

        Strategy:
        1. Find all include and exclude term matches
        2. If include terms found and NO exclude terms → match
        3. If include AND exclude terms found → use scoring:
           - More include terms than exclude → match (dual indication)
           - Equal or fewer includes → reject (primarily other TA)
        4. If only exclude terms → reject
        5. If no terms → depend on require_explicit flag

        Returns:
            Tuple of (is_match, needs_review, evidence)
        """
        text_lower = text.lower()

        # Find all include matches (exact terms)
        matched_include_terms = []
        for include_term in self.includes_expanded:
            if include_term in text_lower:
                matched_include_terms.append(include_term)

        # Find all include matches (regex)
        for pattern in self.include_patterns:
            match = pattern.search(text)
            if match:
                matched_include_terms.append(match.group(0))

        # Find all exclude matches (exact terms)
        matched_exclude_terms = []
        for exclude_term in self.excludes:
            if exclude_term in text_lower:
                matched_exclude_terms.append(exclude_term)

        # Find all exclude matches (regex)
        for pattern in self.exclude_patterns:
            match = pattern.search(text)
            if match:
                matched_exclude_terms.append(match.group(0))

        # Decision logic
        include_count = len(matched_include_terms)
        exclude_count = len(matched_exclude_terms)

        if include_count > 0 and exclude_count == 0:
            # Clear match - only include terms found
            best_match = matched_include_terms[0]
            snippet = extract_snippet(text, best_match)
            evidence = Evidence(
                snippet_en=snippet, snippet_original=None, raw_phrase=best_match
            )
            return True, False, evidence

        elif include_count > 0 and exclude_count > 0:
            # Both found - use scoring
            if include_count > exclude_count:
                # More includes than excludes - likely dual indication or primary focus is our TA
                # Include but flag for review
                best_match = matched_include_terms[0]
                snippet = extract_snippet(text, best_match)
                evidence = Evidence(
                    snippet_en=snippet, snippet_original=None, raw_phrase=best_match
                )
                return True, True, evidence  # Match but needs review
            else:
                # Equal or fewer includes - primarily about other TA
                return False, False, None

        elif exclude_count > 0:
            # Only exclude terms found - clear rejection
            return False, False, None

        else:
            # No terms found at all
            if require_explicit:
                return True, True, None  # Include but flag for review
            else:
                return False, False, None

    def extract_secondary_areas(self, text: str) -> list[str]:
        """Extract all matched therapeutic areas (for secondary areas)."""
        # This would require multiple TA vocabs loaded
        # For now, return empty list
        return []
