"""Company name canonicalizer."""

from typing import Optional

from ..utils.text import canonicalize_company_name, normalize_text, strip_legal_suffixes


class CompanyCanonicalizer:
    """Canonicalize company names using aliases and normalization."""

    def __init__(self, aliases_dict: dict):
        self.company_aliases = aliases_dict.get("company_aliases", {})
        self.legal_suffixes = aliases_dict.get("legal_suffixes_to_strip", [])

    def canonicalize(self, company_name: str) -> str:
        """Canonicalize company name."""
        if not company_name or not company_name.strip():
            return company_name

        # Strip legal suffixes
        name = strip_legal_suffixes(company_name, self.legal_suffixes)

        # Apply aliases
        name = canonicalize_company_name(name, self.company_aliases)

        # Final normalization
        name = name.strip()

        return name

    def normalize(self, company_name: str) -> str:
        """Normalize company name for comparison (lowercase, ASCII-fold, etc)."""
        return normalize_text(company_name)

    def canonicalize_pair(self, name1: str, name2: str) -> tuple[str, str]:
        """Canonicalize a pair of company names (e.g., acquirer and target)."""
        return self.canonicalize(name1), self.canonicalize(name2)
