"""Tests for deduplicator."""

from datetime import date, timedelta

import pytest

from deal_finder.deduplication.deduplicator import Deduplicator
from deal_finder.models import Deal, DealTypeDetailed, DevelopmentStage


@pytest.fixture
def deduplicator():
    return Deduplicator()


@pytest.fixture
def sample_deal():
    return Deal(
        date_announced=date(2023, 6, 15),
        target="TargetCo",
        acquirer="AcquirerCo",
        stage=DevelopmentStage.PRECLINICAL,
        therapeutic_area="immunology_inflammation",
        asset_focus="IL-6 inhibitor",
        deal_type_detailed=DealTypeDetailed.MA,
        source_url="https://example.com/deal1",
        timestamp_utc="2023-06-15T00:00:00Z",
    )


def test_generate_canonical_key(deduplicator, sample_deal):
    key = deduplicator.generate_canonical_key(sample_deal)

    assert isinstance(key, str)
    assert len(key) == 64  # SHA256 hex digest


def test_same_deal_same_key(deduplicator, sample_deal):
    key1 = deduplicator.generate_canonical_key(sample_deal)
    key2 = deduplicator.generate_canonical_key(sample_deal)

    assert key1 == key2


def test_different_deals_different_keys(deduplicator, sample_deal):
    deal2 = sample_deal.model_copy(deep=True)
    deal2.asset_focus = "Different asset"

    key1 = deduplicator.generate_canonical_key(sample_deal)
    key2 = deduplicator.generate_canonical_key(deal2)

    assert key1 != key2


def test_is_duplicate_exact(deduplicator, sample_deal):
    sample_deal.canonical_key = deduplicator.generate_canonical_key(sample_deal)

    deal2 = sample_deal.model_copy(deep=True)
    deal2.canonical_key = deduplicator.generate_canonical_key(deal2)

    existing_deals = [sample_deal]

    assert deduplicator.is_duplicate(deal2, existing_deals) is True


def test_is_duplicate_fuzzy_within_window(deduplicator, sample_deal):
    sample_deal.canonical_key = deduplicator.generate_canonical_key(sample_deal)

    # Same deal but 2 days later
    deal2 = sample_deal.model_copy(deep=True)
    deal2.date_announced = sample_deal.date_announced + timedelta(days=2)
    deal2.canonical_key = deduplicator.generate_canonical_key(deal2)

    existing_deals = [sample_deal]

    # Should be considered duplicate due to fuzzy match within date window
    assert deduplicator.is_duplicate(deal2, existing_deals, date_window_days=3) is True


def test_is_not_duplicate_outside_window(deduplicator, sample_deal):
    sample_deal.canonical_key = deduplicator.generate_canonical_key(sample_deal)

    # Same deal but 5 days later
    deal2 = sample_deal.model_copy(deep=True)
    deal2.date_announced = sample_deal.date_announced + timedelta(days=5)
    deal2.canonical_key = deduplicator.generate_canonical_key(deal2)

    existing_deals = [sample_deal]

    # Should not be duplicate - outside date window
    assert deduplicator.is_duplicate(deal2, existing_deals, date_window_days=3) is False


def test_deduplicate_list(deduplicator, sample_deal):
    # Create duplicate deals
    deals = [sample_deal, sample_deal.model_copy(deep=True)]

    unique_deals = deduplicator.deduplicate(deals)

    assert len(unique_deals) == 1


def test_merge_duplicates_prefer_press_release(deduplicator, sample_deal):
    deal1 = sample_deal.model_copy(deep=True)
    deal1.source_url = "https://example.com/some-article"

    deal2 = sample_deal.model_copy(deep=True)
    deal2.source_url = "https://www.prnewswire.com/press-release"

    merged = deduplicator.merge_duplicates(deal1, deal2)

    # Should prefer press release URL
    assert "prnewswire" in str(merged.source_url).lower()
