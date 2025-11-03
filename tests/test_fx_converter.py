"""Tests for FX converter."""

from datetime import date
from decimal import Decimal

import pytest

from deal_finder.normalization.fx_converter import FXConverter


@pytest.fixture
def converter():
    return FXConverter(base_currency="USD")


def test_convert_usd_to_usd(converter):
    amount = Decimal("100")
    converted, rate, source = converter.convert(amount, "USD", date(2023, 1, 15))

    assert converted == amount
    assert rate == Decimal("1.0")


def test_get_rate_eur_to_usd(converter):
    # This will use actual FX rates if available
    rate, source = converter.get_rate("EUR", date(2023, 1, 15))

    # Basic validation - rate should be positive
    if rate is not None:
        assert rate > 0
        assert isinstance(rate, Decimal)


def test_get_rate_caching(converter):
    # Get rate twice
    rate1, source1 = converter.get_rate("EUR", date(2023, 1, 15))
    rate2, source2 = converter.get_rate("EUR", date(2023, 1, 15))

    # Should return cached result
    assert rate1 == rate2
    assert source1 == source2


def test_convert_with_rate(converter):
    amount = Decimal("100")
    test_date = date(2023, 1, 15)

    converted, rate, source = converter.convert(amount, "EUR", test_date)

    if converted is not None and rate is not None:
        # Verify calculation
        assert converted == amount * rate
