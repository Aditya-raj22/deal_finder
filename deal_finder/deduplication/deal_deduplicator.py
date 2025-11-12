"""Deal-based deduplication by acquirer + target + date."""

import logging
from typing import List

logger = logging.getLogger(__name__)


class DealDeduplicator:
    """Remove duplicate deals based on (acquirer + target + date)."""

    def deduplicate(self, deals: List) -> List:
        """
        Remove duplicate deals based on (acquirer + target + date).

        When duplicates are found, keeps the "best" version (most complete data).
        Priority: Deal with highest total_deal_value_usd.

        Args:
            deals: List of Deal objects

        Returns:
            Deduplicated list, keeping the "best" version of each deal
        """
        seen_deals = {}
        unique_deals = []

        for deal in deals:
            # Create unique key
            key = (
                deal.acquirer.lower(),
                deal.target.lower(),
                deal.date_announced.strftime("%Y-%m-%d")
            )

            if key not in seen_deals:
                seen_deals[key] = deal
                unique_deals.append(deal)
            else:
                # Already have this deal - keep the one with more complete data
                existing = seen_deals[key]

                # Compare total deal value (keep the one with value if one is missing)
                if deal.total_deal_value_usd and not existing.total_deal_value_usd:
                    # New one has value, old doesn't → replace
                    unique_deals.remove(existing)
                    unique_deals.append(deal)
                    seen_deals[key] = deal
                elif deal.total_deal_value_usd and existing.total_deal_value_usd:
                    # Both have values - keep the larger one (more complete)
                    if deal.total_deal_value_usd > existing.total_deal_value_usd:
                        unique_deals.remove(existing)
                        unique_deals.append(deal)
                        seen_deals[key] = deal

        duplicates = len(deals) - len(unique_deals)
        if duplicates > 0:
            logger.info(f"Deal deduplication: {len(deals)} → {len(unique_deals)} ({duplicates} duplicates removed)")

        return unique_deals
