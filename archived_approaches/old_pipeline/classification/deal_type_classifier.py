"""Deal type classifier."""

import re
from typing import Optional, Tuple

from ..models import DealTypeDetailed, Evidence
from ..utils.text import extract_snippet


class DealTypeClassifier:
    """Classify deal type from text."""

    def __init__(self):
        # Deal type patterns (precedence order from spec)
        self.patterns = {
            DealTypeDetailed.MA: [
                r"\bacquir(e|es|ed|ing|ition)\b",
                r"\bmerger\b",
                r"\bmerge[sd]?\b",
                r"\bcombination\b",
                r"\bbuyout\b",
                r"\btakeover\b",
            ],
            DealTypeDetailed.OPTION_TO_LICENSE: [
                r"\boption[- ]to[- ]license\b",
                r"\blicens(e|ing)\s+option\b",
                r"\bopt[- ]in\b",
            ],
            DealTypeDetailed.LICENSING: [
                r"\blicense\b",
                r"\blicensing\b",
                r"\bexclusive\s+license\b",
                r"\bexclusive\s+rights\b",
                r"\bterrit(ory|orial)\s+rights\b",
                r"\basset\s+purchase\b",
                r"\bpurchase\s+of\s+asset\b",
            ],
            DealTypeDetailed.PARTNERSHIP: [
                r"\bpartnership\b",
                r"\bpartner\b",
                r"\bcollaboration\b",
                r"\bcollaborative\b",
                r"\bco[- ]develop(ment)?\b",
                r"\bco[- ]promotion\b",
                r"\bjoint\s+venture\b",
                r"\bJV\b",
                r"\bstrategic\s+alliance\b",
            ],
        }

    def classify(self, text: str) -> Tuple[Optional[DealTypeDetailed], bool, Optional[Evidence]]:
        """
        Classify deal type from text.

        Returns:
            Tuple of (deal_type, needs_review, evidence)
        """
        text_lower = text.lower()

        # Try patterns in precedence order
        for deal_type, patterns in self.patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    matched_phrase = match.group(0)
                    snippet = extract_snippet(text, matched_phrase)

                    evidence = Evidence(
                        snippet_en=snippet, snippet_original=None, raw_phrase=matched_phrase
                    )

                    return deal_type, False, evidence

        # No deal type found - default to partnership for review
        return DealTypeDetailed.PARTNERSHIP, True, None
