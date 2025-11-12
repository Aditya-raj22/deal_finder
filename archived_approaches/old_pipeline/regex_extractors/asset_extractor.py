"""Asset/focus extractor."""

import re
from typing import Optional, Tuple

from ..models import Evidence
from ..utils.text import extract_snippet


class AssetExtractor:
    """Extract asset or focus of deal from text."""

    def __init__(self):
        # Patterns to identify asset focus
        self.asset_patterns = [
            r"(?:asset|program|candidate|therapy|treatment|drug):\s*([A-Za-z0-9\s\-]+)",
            r"(?:targeting|focused on|for)\s+([A-Za-z0-9\s\-]{3,50})",
            r"([A-Z]{2,}-\d+)",  # Drug codes like ABC-123
            r"([A-Z][a-z]+mab|[A-Z][a-z]+ximab|[A-Z][a-z]+zumab)",  # Antibody names
        ]

    def extract(self, text: str) -> Tuple[Optional[str], bool, Optional[Evidence]]:
        """
        Extract asset/focus from text.

        Returns:
            Tuple of (asset_focus, needs_review, evidence)
        """
        # Try each pattern
        for pattern in self.asset_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                asset = match.group(1 if len(match.groups()) > 0 else 0).strip()

                # Basic validation
                if 2 < len(asset) < 100:
                    snippet = extract_snippet(text, asset)
                    evidence = Evidence(
                        snippet_en=snippet, snippet_original=None, raw_phrase=asset
                    )
                    return asset, False, evidence

        # Fallback: use a generic description if no specific asset found
        # In practice, this should mark as needs_review
        return "Undisclosed", True, None
