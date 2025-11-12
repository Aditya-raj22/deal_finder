"""Development stage classifier."""

import re
from typing import Optional, Tuple

from ..models import DevelopmentStage, Evidence
from ..utils.text import extract_snippet, is_ambiguous_stage


class StageClassifier:
    """Classify development stage from text."""

    def __init__(self, allowed_stages: list[str]):
        self.allowed_stages = allowed_stages

        # Stage patterns (order matters - most specific first)
        self.stage_patterns = {
            DevelopmentStage.FIRST_IN_HUMAN: [
                r"\bfirst[- ]in[- ]human\b",
                r"\bFIH\b",
                r"\bfirst[- ]in[- ]man\b",
            ],
            DevelopmentStage.PHASE_1: [
                r"\bphase\s*[1I]\b",
                r"\bphase\s*one\b",
                r"\bstage\s*[1I]\b",
            ],
            DevelopmentStage.PRECLINICAL: [
                r"\bpreclinical\b",
                r"\bpre[- ]clinical\b",
                r"\bdiscovery\s+stage\b",
                r"\bearly[- ]stage\b",
            ],
        }

        # Exclusion patterns (phases beyond early stage)
        self.exclusion_patterns = [
            r"\bphase\s*[1I]\s*[/\-]\s*2\b",
            r"\bphase\s*[1I]\s*[/\-]\s*II\b",
            r"\bphase\s*2\b",
            r"\bphase\s*II\b",
            r"\bphase\s*III\b",
            r"\bphase\s*3\b",
            r"\bphase\s*IV\b",
            r"\bphase\s*4\b",
        ]

    def classify(self, text: str) -> Tuple[Optional[DevelopmentStage], bool, Optional[Evidence]]:
        """
        Classify development stage from text.

        Returns:
            Tuple of (stage, needs_review, evidence)
        """
        text_lower = text.lower()

        # Check for ambiguous stage mentions first (includes phase 1/2, phase 2+)
        if is_ambiguous_stage(text):
            return DevelopmentStage.PRECLINICAL, True, None

        # Check for exclusion patterns (pure phase 2+ without ambiguity)
        for pattern in self.exclusion_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Found phase 2+ mention - reject
                return None, False, None

        # Try to match allowed stages
        for stage, patterns in self.stage_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    matched_phrase = match.group(0)
                    snippet = extract_snippet(text, matched_phrase)

                    evidence = Evidence(
                        snippet_en=snippet, snippet_original=None, raw_phrase=matched_phrase
                    )

                    return stage, False, evidence

        # No stage found - include with default stage for review
        return DevelopmentStage.PRECLINICAL, True, None

    def classify_with_fallback(
        self, text: str, default_stage: Optional[DevelopmentStage] = None
    ) -> Tuple[Optional[DevelopmentStage], bool, Optional[Evidence]]:
        """Classify with fallback to default stage if ambiguous."""
        stage, needs_review, evidence = self.classify(text)

        if stage is None and needs_review and default_stage:
            return default_stage, True, evidence

        return stage, needs_review, evidence
