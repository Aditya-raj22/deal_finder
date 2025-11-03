"""Geography resolver to determine company headquarters country."""

import re
from typing import Optional


class GeographyResolver:
    """Resolve company geography (HQ country) from text."""

    def __init__(self):
        # Common country patterns
        self.country_patterns = {
            "United States": [
                r"\bU\.?S\.?\b",
                r"\bUSA\b",
                r"\bUnited States\b",
                r"\bCalifornia\b",
                r"\bMassachusetts\b",
                r"\bNew York\b",
                r"\bTexas\b",
                r"\bboston\b",
                r"\bsan francisco\b",
                r"\bsan diego\b",
            ],
            "United Kingdom": [
                r"\bU\.?K\.?\b",
                r"\bUnited Kingdom\b",
                r"\bEngland\b",
                r"\bLondon\b",
                r"\bCambridge\b",
                r"\bOxford\b",
            ],
            "Germany": [r"\bGermany\b", r"\bBerlin\b", r"\bMunich\b", r"\bHeidelberg\b"],
            "Switzerland": [r"\bSwitzerland\b", r"\bSwiss\b", r"\bBasel\b", r"\bZurich\b"],
            "France": [r"\bFrance\b", r"\bParis\b", r"\bFrench\b"],
            "China": [r"\bChina\b", r"\bChinese\b", r"\bBeijing\b", r"\bShanghai\b"],
            "Japan": [r"\bJapan\b", r"\bJapanese\b", r"\bTokyo\b", r"\bOsaka\b"],
            "Canada": [r"\bCanada\b", r"\bCanadian\b", r"\bToronto\b", r"\bMontreal\b"],
            "Israel": [r"\bIsrael\b", r"\bIsraeli\b", r"\bTel Aviv\b"],
            "Denmark": [r"\bDenmark\b", r"\bDanish\b", r"\bCopenhagen\b"],
            "Sweden": [r"\bSweden\b", r"\bSwedish\b", r"\bStockholm\b"],
            "Netherlands": [r"\bNetherlands\b", r"\bDutch\b", r"\bAmsterdam\b"],
            "Belgium": [r"\bBelgium\b", r"\bBelgian\b", r"\bBrussels\b"],
            "Italy": [r"\bItaly\b", r"\bItalian\b", r"\bRome\b", r"\bMilan\b"],
            "Spain": [r"\bSpain\b", r"\bSpanish\b", r"\bMadrid\b", r"\bBarcelona\b"],
            "Australia": [r"\bAustralia\b", r"\bAustralian\b", r"\bSydney\b", r"\bMelbourne\b"],
        }

    def resolve(self, text: str, company_name: Optional[str] = None) -> Optional[str]:
        """
        Resolve geography from text.

        Returns:
            ISO country name or None
        """
        # Try to match country patterns
        for country, patterns in self.country_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return country

        # No match found
        return None

    def resolve_from_url(self, url: str) -> Optional[str]:
        """Resolve geography from URL domain."""
        # Extract TLD
        domain_map = {
            ".com": "United States",  # Default assumption
            ".co.uk": "United Kingdom",
            ".uk": "United Kingdom",
            ".de": "Germany",
            ".ch": "Switzerland",
            ".fr": "France",
            ".cn": "China",
            ".jp": "Japan",
            ".ca": "Canada",
            ".il": "Israel",
            ".dk": "Denmark",
            ".se": "Sweden",
            ".nl": "Netherlands",
            ".be": "Belgium",
            ".it": "Italy",
            ".es": "Spain",
            ".au": "Australia",
        }

        url_lower = url.lower()
        for tld, country in domain_map.items():
            if tld in url_lower:
                return country

        return None
