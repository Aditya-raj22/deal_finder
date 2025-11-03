"""Deal deduplicator."""

import hashlib
from datetime import date, timedelta
from typing import List

from ..models import Deal
from ..utils.text import normalize_text


class Deduplicator:
    """Deduplicate deals using canonical key."""

    def __init__(self):
        self.seen_keys = {}

    def generate_canonical_key(self, deal: Deal) -> str:
        """
        Generate canonical key for deduplication.

        Key = hash(norm_targets|norm_acquirers|asset_focus_norm|announcement_utc_date)
        """
        # Normalize components
        target_norm = normalize_text(deal.target)
        acquirer_norm = normalize_text(deal.acquirer)
        asset_norm = normalize_text(deal.asset_focus)
        date_str = deal.date_announced.isoformat()

        # Combine and hash
        key_components = f"{target_norm}|{acquirer_norm}|{asset_norm}|{date_str}"
        key_hash = hashlib.sha256(key_components.encode()).hexdigest()

        return key_hash

    def is_duplicate(
        self, deal: Deal, existing_deals: List[Deal], date_window_days: int = 3
    ) -> bool:
        """
        Check if deal is a duplicate of existing deals.

        Considers:
        - Same canonical key
        - Within ±date_window_days of an existing deal with same parties/asset
        """
        deal_key = self.generate_canonical_key(deal)

        # Exact key match
        for existing in existing_deals:
            if existing.canonical_key == deal_key:
                return True

        # Fuzzy match: same parties/asset within date window
        for existing in existing_deals:
            # Check if within date window
            date_diff = abs((deal.date_announced - existing.date_announced).days)
            if date_diff <= date_window_days:
                # Check if parties and asset match (normalized)
                if (
                    normalize_text(deal.target) == normalize_text(existing.target)
                    and normalize_text(deal.acquirer) == normalize_text(existing.acquirer)
                    and normalize_text(deal.asset_focus) == normalize_text(existing.asset_focus)
                ):
                    return True

        return False

    def merge_duplicates(self, deal1: Deal, deal2: Deal) -> Deal:
        """
        Merge two duplicate deals, keeping primary source and merging URLs.

        Prioritizes press releases over other sources.
        """
        # Determine which is primary (prefer press release URLs)
        primary_keywords = ["prnewswire", "businesswire", "globenewswire", "newsroom", "press"]

        deal1_url_lower = str(deal1.source_url).lower()
        deal2_url_lower = str(deal2.source_url).lower()

        deal1_is_press = any(kw in deal1_url_lower for kw in primary_keywords)
        deal2_is_press = any(kw in deal2_url_lower for kw in primary_keywords)

        if deal1_is_press and not deal2_is_press:
            primary = deal1
            secondary = deal2
        elif deal2_is_press and not deal1_is_press:
            primary = deal2
            secondary = deal1
        else:
            # Both or neither are press releases, keep earlier date
            if deal1.date_announced <= deal2.date_announced:
                primary = deal1
                secondary = deal2
            else:
                primary = deal2
                secondary = deal1

        # Merge related URLs
        merged_urls = list(set(primary.related_urls + [str(secondary.source_url)]))

        # Create merged deal
        merged = primary.model_copy(deep=True)
        merged.related_urls = merged_urls

        return merged

    def deduplicate(self, deals: List[Deal]) -> List[Deal]:
        """
        Deduplicate list of deals.

        Returns:
            List of unique deals with merged duplicates
        """
        unique_deals = []
        seen_keys = set()

        for deal in deals:
            # Generate canonical key
            deal.canonical_key = self.generate_canonical_key(deal)

            # Check if duplicate
            if not self.is_duplicate(deal, unique_deals):
                unique_deals.append(deal)
                seen_keys.add(deal.canonical_key)
            else:
                # Find matching deal and merge
                for i, existing in enumerate(unique_deals):
                    if (
                        existing.canonical_key == deal.canonical_key
                        or self._is_fuzzy_match(deal, existing)
                    ):
                        # Merge and replace
                        merged = self.merge_duplicates(existing, deal)
                        unique_deals[i] = merged
                        break

        return unique_deals

    def _is_fuzzy_match(
        self, deal1: Deal, deal2: Deal, date_window_days: int = 3
    ) -> bool:
        """Check if two deals are fuzzy matches."""
        date_diff = abs((deal1.date_announced - deal2.date_announced).days)
        if date_diff > date_window_days:
            return False

        return (
            normalize_text(deal1.target) == normalize_text(deal2.target)
            and normalize_text(deal1.acquirer) == normalize_text(deal2.acquirer)
            and normalize_text(deal1.asset_focus) == normalize_text(deal2.asset_focus)
        )
