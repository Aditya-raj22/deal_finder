"""Text processing utilities."""

import re
import unicodedata
from typing import Optional


def normalize_text(text: str) -> str:
    """Normalize text: lowercase, ASCII-fold, collapse whitespace."""
    # ASCII-fold (remove diacritics)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Lowercase
    text = text.lower()

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def strip_legal_suffixes(company_name: str, suffixes: list[str]) -> str:
    """Strip legal suffixes from company name."""
    name = company_name.strip()
    name_lower = name.lower()

    for suffix in suffixes:
        suffix_lower = suffix.lower()
        # Try with comma
        pattern = rf",?\s+{re.escape(suffix_lower)}\.?$"
        name_lower_new = re.sub(pattern, "", name_lower)
        if name_lower_new != name_lower:
            # Suffix was removed, update original name too
            name = name[: len(name_lower_new)].strip()
            name_lower = name_lower_new

    return name.strip()


def canonicalize_company_name(name: str, aliases: dict[str, list[str]]) -> str:
    """Canonicalize company name using aliases."""
    normalized = normalize_text(name)

    # Check aliases
    for canonical, variants in aliases.items():
        if normalized == canonical.lower():
            return canonical
        for variant in variants:
            if normalized == variant.lower():
                return canonical

    return name.strip()


def extract_snippet(text: str, phrase: str, context_chars: int = 200) -> str:
    """Extract snippet around a phrase."""
    phrase_lower = phrase.lower()
    text_lower = text.lower()

    idx = text_lower.find(phrase_lower)
    if idx == -1:
        return text[:context_chars * 2]  # Return start of text if phrase not found

    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(phrase) + context_chars)

    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


def clean_amount_text(text: str) -> str:
    """Clean monetary amount text for parsing."""
    # Remove common noise words
    noise_words = ["approximately", "about", "around", "up to", "upto", "roughly"]
    text_lower = text.lower()
    for word in noise_words:
        text_lower = re.sub(rf"\b{word}\b", "", text_lower)

    # Remove thousand separators
    text_lower = text_lower.replace(",", "")

    return text_lower.strip()


def is_ambiguous_stage(text: str) -> bool:
    """Check if stage mention is ambiguous (e.g., phase 1/2)."""
    ambiguous_patterns = [
        r"phase\s*[1I]/\s*2",
        r"phase\s*[1I]\s*[/\-]\s*2",
    ]

    text_lower = text.lower()
    for pattern in ambiguous_patterns:
        if re.search(pattern, text_lower):
            return True

    return False


def extract_date_from_text(text: str) -> Optional[str]:
    """Extract date from text using various patterns."""
    # Common date patterns
    patterns = [
        # YYYY-MM-DD
        r"\b(\d{4})-(\d{2})-(\d{2})\b",
        # Month DD, YYYY
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
        # DD Month YYYY
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
        # MM/DD/YYYY
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)

    return None
