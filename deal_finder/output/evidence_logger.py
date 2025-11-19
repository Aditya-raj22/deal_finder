"""Evidence logger for JSONL output."""

import json
from pathlib import Path
from typing import List

from ..models import Deal


class EvidenceLogger:
    """Log evidence for deals in JSONL format."""

    def __init__(self):
        pass

    def _deal_to_evidence_record(self, deal: Deal) -> dict:
        """Convert Deal to evidence record."""
        # Convert evidence to dict
        evidence_dict = {}
        if deal.evidence.date_announced:
            evidence_dict["date_announced"] = deal.evidence.date_announced.model_dump()
        if deal.evidence.target:
            evidence_dict["target"] = deal.evidence.target.model_dump()
        if deal.evidence.acquirer:
            evidence_dict["acquirer"] = deal.evidence.acquirer.model_dump()
        if deal.evidence.upfront_value:
            evidence_dict["upfront_value"] = deal.evidence.upfront_value.model_dump()
        if deal.evidence.contingent_payment:
            evidence_dict["contingent_payment"] = deal.evidence.contingent_payment.model_dump()
        if deal.evidence.total_deal_value:
            evidence_dict["total_deal_value"] = deal.evidence.total_deal_value.model_dump()
        if deal.evidence.stage:
            evidence_dict["stage"] = deal.evidence.stage.model_dump()
        if deal.evidence.therapeutic_area:
            evidence_dict["therapeutic_area"] = deal.evidence.therapeutic_area.model_dump()
        if deal.evidence.asset_focus:
            evidence_dict["asset_focus"] = deal.evidence.asset_focus.model_dump()
        if deal.evidence.deal_type:
            evidence_dict["deal_type"] = deal.evidence.deal_type.model_dump()
        if deal.evidence.geography:
            evidence_dict["geography"] = deal.evidence.geography.model_dump()

        return {
            "canonical_key": deal.canonical_key,
            "source_url": str(deal.source_url),
            "related_urls": deal.related_urls,
            "evidence": evidence_dict,
            "detected_currency": deal.detected_currency,
            "fx_rate": float(deal.fx_rate) if deal.fx_rate else None,
            "fx_source": deal.fx_source,
            "confidence": float(deal.confidence),
            "inclusion_reason": deal.inclusion_reason,
            "exclusion_reason": deal.exclusion_reason,
            "parser_version": deal.parser_version,
            "timestamp_utc": deal.timestamp_utc,
        }

    def write(self, deals: List[Deal], output_path: str) -> None:
        """Write evidence log in JSONL format."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            for deal in deals:
                record = self._deal_to_evidence_record(deal)
                f.write(json.dumps(record) + "\n")
