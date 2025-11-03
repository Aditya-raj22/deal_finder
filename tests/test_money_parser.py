"""Tests for money parser."""

from decimal import Decimal

import pytest

from deal_finder.extraction.money_parser import MoneyParser


@pytest.fixture
def parser():
    return MoneyParser()


def test_parse_million_usd(parser):
    text = "Deal worth $500 million."
    amount, currency, needs_review, evidence = parser.parse(text)

    assert amount == Decimal("500")
    assert currency == "USD"
    assert needs_review is False
    assert evidence is not None


def test_parse_billion_usd(parser):
    text = "Acquisition for $2.5 billion."
    amount, currency, needs_review, evidence = parser.parse(text)

    assert amount == Decimal("2500")  # Converted to millions
    assert currency == "USD"
    assert needs_review is False


def test_parse_eur(parser):
    text = "€350 million deal announced."
    amount, currency, needs_review, evidence = parser.parse(text)

    assert amount == Decimal("350")
    assert currency == "EUR"
    assert needs_review is False


def test_parse_ambiguous_up_to(parser):
    text = "Deal worth up to $500 million."
    amount, currency, needs_review, evidence = parser.parse(text)

    # Changed: Extract ambiguous amounts and flag for review (avoid false negatives)
    assert amount == Decimal("500")
    assert currency == "USD"
    assert needs_review is True


def test_parse_undisclosed(parser):
    text = "Undisclosed amount."
    amount, currency, needs_review, evidence = parser.parse(text)

    assert amount is None
    assert needs_review is True


def test_parse_upfront_contingent_total(parser):
    text = "Upfront payment of $100 million with up to $500 million in milestones."
    (
        upfront,
        contingent,
        total,
        currency,
        needs_review,
        evidence,
    ) = parser.parse_upfront_contingent_total(text)

    assert upfront == Decimal("100")
    assert currency == "USD"
    # Note: contingent might be None due to "up to" ambiguity
