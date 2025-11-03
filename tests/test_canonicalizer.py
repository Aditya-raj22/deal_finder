"""Tests for company canonicalizer."""

import pytest

from deal_finder.normalization.company_canonicalizer import CompanyCanonicalizer


@pytest.fixture
def aliases():
    return {
        "company_aliases": {
            "pfizer": ["pfizer inc", "pfizer incorporated"],
            "johnson & johnson": ["j&j", "jnj"],
        },
        "legal_suffixes_to_strip": ["inc", "incorporated", "ltd", "llc"],
    }


@pytest.fixture
def canonicalizer(aliases):
    return CompanyCanonicalizer(aliases)


def test_strip_legal_suffix(canonicalizer):
    name = "Biotech Company Inc"
    canonical = canonicalizer.canonicalize(name)

    assert "inc" not in canonical.lower()


def test_apply_alias(canonicalizer):
    name = "Pfizer Inc"
    canonical = canonicalizer.canonicalize(name)

    assert canonical.lower() == "pfizer"


def test_apply_alias_variant(canonicalizer):
    name = "J&J"
    canonical = canonicalizer.canonicalize(name)

    assert canonical == "johnson & johnson"


def test_normalize_for_comparison(canonicalizer):
    name1 = "BioTech Company"
    name2 = "biotech company"

    norm1 = canonicalizer.normalize(name1)
    norm2 = canonicalizer.normalize(name2)

    assert norm1 == norm2


def test_canonicalize_pair(canonicalizer):
    name1 = "Pfizer Inc"
    name2 = "J&J"

    canonical1, canonical2 = canonicalizer.canonicalize_pair(name1, name2)

    assert canonical1.lower() == "pfizer"
    assert canonical2 == "johnson & johnson"
