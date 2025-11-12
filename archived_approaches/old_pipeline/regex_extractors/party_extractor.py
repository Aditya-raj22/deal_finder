"""Party (company) extractor."""

import re
from typing import Optional, Tuple

from ..models import Evidence
from ..utils.text import extract_snippet


class PartyExtractor:
    """Extract company parties from text."""

    def __init__(self):
        # Simplified patterns for identifying companies
        # Each pattern captures: (acquirer, target)
        self.acquirer_patterns = [
            # "Pfizer Inc. announced... acquire Arena Pharmaceuticals"
            r"([A-Z][A-Za-z0-9]+(?:\s+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|SE|AG|plc|PLC)\.?)?)\s+(?:announced|announces)[^.]*?(?:acquire|acquisition of|to acquire)\s+([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|SE|AG|plc|PLC)\.?)",
            # "Pfizer acquires Arena"
            r"([A-Z][A-Za-z0-9]+(?:\s+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|SE|AG|plc|PLC)\.?)?)\s+(?:acquires|will acquire|to acquire)\s+([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|SE|AG|plc|PLC)\.?)",
            # "acquisition of Arena by Pfizer"
            r"(?:acquisition|purchase)\s+of\s+([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|SE|AG|plc|PLC)\.?)\s+by\s+([A-Z][A-Za-z0-9]+(?:\s+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|SE|AG|plc|PLC)\.?)?)",
        ]

        self.partnership_patterns = [
            # "Company and Company announced"
            r"([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?)\s+(?:and|&)\s+([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?)\s+(?:announced|announce)",
            # "partnership between Company and Company"
            r"(?:partnership|collaboration)\s+between\s+([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?)\s+(?:and|&)\s+([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?)",
            # "Company... with Company" (for licensing/collaboration deals)
            r"([A-Z][A-Za-z0-9]+(?:\s+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?)?)[^.]*?\b(?:with|and)\s+([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?),?\s+(?:inking|signing|entering|forming|to develop|for)",
            # "licensing deal for Company's..."
            r"([A-Z][A-Za-z0-9]+(?:\s+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?)?)[^.]*?(?:licensing|option)\s+deal\s+for\s+(?:the\s+)?(?:biotech'?s?|company'?s?|([A-Z][A-Za-z0-9\s]+(?:Inc|Corp|Ltd|Pharmaceuticals|Pharma|Therapeutics|SE|AG|plc|PLC)\.?)'s)",
        ]

    def _clean_company_name(self, name: str) -> str:
        """Clean extracted company name."""
        # Remove leading/trailing whitespace
        name = name.strip()

        # Remove trailing punctuation
        name = re.sub(r"[,.]$", "", name)

        # Collapse multiple spaces
        name = re.sub(r"\s+", " ", name)

        return name

    def extract_acquirer(
        self, text: str
    ) -> Tuple[Optional[str], bool, Optional[Evidence]]:
        """Extract acquirer/buyer company."""
        for i, pattern in enumerate(self.acquirer_patterns):
            match = re.search(pattern, text, re.DOTALL)
            if match and len(match.groups()) >= 2:
                # Third pattern (index 2) has reversed order: (target, acquirer)
                if i == 2:
                    company = self._clean_company_name(match.group(2))
                else:
                    company = self._clean_company_name(match.group(1))

                if len(company) > 2 and not company.startswith(('NEW YORK', 'BOSTON', 'SAN')):
                    snippet = extract_snippet(text, company)
                    evidence = Evidence(
                        snippet_en=snippet, snippet_original=None, raw_phrase=company
                    )
                    return company, False, evidence

        return None, True, None

    def extract_target(
        self, text: str
    ) -> Tuple[Optional[str], bool, Optional[Evidence]]:
        """Extract target company."""
        for i, pattern in enumerate(self.acquirer_patterns):
            match = re.search(pattern, text, re.DOTALL)
            if match and len(match.groups()) >= 2:
                # Third pattern (index 2) has reversed order: (target, acquirer)
                if i == 2:
                    company = self._clean_company_name(match.group(1))
                else:
                    company = self._clean_company_name(match.group(2))

                if len(company) > 2 and not company.startswith(('NEW YORK', 'BOSTON', 'SAN')):
                    snippet = extract_snippet(text, company)
                    evidence = Evidence(
                        snippet_en=snippet, snippet_original=None, raw_phrase=company
                    )
                    return company, False, evidence

        return None, True, None

    def extract_partners(
        self, text: str
    ) -> Tuple[Optional[Tuple[str, str]], bool, Optional[dict[str, Evidence]]]:
        """Extract partnership parties."""
        for pattern in self.partnership_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and len(match.groups()) >= 2:
                partner1 = self._clean_company_name(match.group(1))
                partner2 = self._clean_company_name(match.group(2))

                if len(partner1) > 2 and len(partner2) > 2:
                    snippet1 = extract_snippet(text, partner1)
                    snippet2 = extract_snippet(text, partner2)

                    evidence = {
                        "partner1": Evidence(
                            snippet_en=snippet1, snippet_original=None, raw_phrase=partner1
                        ),
                        "partner2": Evidence(
                            snippet_en=snippet2, snippet_original=None, raw_phrase=partner2
                        ),
                    }

                    return (partner1, partner2), False, evidence

        return None, True, None
