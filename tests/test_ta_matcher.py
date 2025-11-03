"""Tests for TA matcher."""

import pytest

from deal_finder.classification.ta_matcher import TAMatcher


@pytest.fixture
def vocab():
    return {
        "therapeutic_area": "immunology_inflammation",
        "includes": ["rheumatoid arthritis", "psoriasis", "inflammatory bowel disease"],
        "excludes": ["cancer", "oncology"],
        "synonyms": {"rheumatoid arthritis": ["RA"]},
        "regex": {
            "include_patterns": [r"\\bIL-\\d+\\b"],
            "exclude_patterns": [r"\\bcancer\\b"],
        },
    }


@pytest.fixture
def matcher(vocab):
    return TAMatcher(vocab)


def test_match_exact_term(matcher):
    text = "New therapy for rheumatoid arthritis approved."
    is_match, needs_review, evidence = matcher.match(text)

    assert is_match is True
    assert needs_review is False
    assert evidence is not None


def test_match_synonym(matcher):
    text = "RA treatment shows promise in early trials."
    is_match, needs_review, evidence = matcher.match(text)

    assert is_match is True
    assert needs_review is False


def test_match_regex(matcher):
    text = "IL-6 inhibitor demonstrates efficacy."
    is_match, needs_review, evidence = matcher.match(text)

    assert is_match is True
    assert needs_review is False


def test_exclude_overrides(matcher):
    text = "Cancer treatment for rheumatoid arthritis."
    is_match, needs_review, evidence = matcher.match(text)

    assert is_match is False  # Exclude overrides include
    assert needs_review is False


def test_no_match(matcher):
    text = "Diabetes medication approved."
    is_match, needs_review, evidence = matcher.match(text)

    assert is_match is True  # Include for review
    assert needs_review is True  # Ambiguous
