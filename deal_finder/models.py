"""Data models for deal records and evidence."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class DealType(str, Enum):
    """Deal type enumeration (output format)."""

    MA = "M&A"
    PARTNERSHIP = "Partnership"


class DealTypeDetailed(str, Enum):
    """Deal type enumeration (internal classification)."""

    MA = "M&A"
    PARTNERSHIP = "partnership"
    LICENSING = "licensing"
    OPTION_TO_LICENSE = "option-to-license"


class DevelopmentStage(str, Enum):
    """Development stage enumeration."""

    PRECLINICAL = "preclinical"
    PHASE_1 = "phase 1"
    FIRST_IN_HUMAN = "first-in-human"
    UNKNOWN = "unknown"


class Evidence(BaseModel):
    """Evidence for a field extraction."""

    snippet_en: str = Field(description="English snippet containing the evidence")
    snippet_original: Optional[str] = Field(
        default=None, description="Original language snippet if translated"
    )
    selector_or_xpath: Optional[str] = Field(
        default=None, description="CSS selector or XPath to the element"
    )
    raw_phrase: str = Field(description="Exact phrase extracted")


class FieldEvidence(BaseModel):
    """Evidence for all deal fields."""

    date_announced: Optional[Evidence] = None
    target: Optional[Evidence] = None
    acquirer: Optional[Evidence] = None
    upfront_value: Optional[Evidence] = None
    contingent_payment: Optional[Evidence] = None
    total_deal_value: Optional[Evidence] = None
    stage: Optional[Evidence] = None
    therapeutic_area: Optional[Evidence] = None
    asset_focus: Optional[Evidence] = None
    deal_type: Optional[Evidence] = None
    geography: Optional[Evidence] = None


class Deal(BaseModel):
    """Internal deal record with full metadata."""

    # Required fields
    date_announced: date = Field(description="Announcement date in UTC")
    target: str = Field(description="Target or partner company (canonical)")
    acquirer: str = Field(description="Acquirer or partner company (canonical)")
    stage: str = Field(description="Development stage at announcement")  # Changed from DevelopmentStage enum to plain string
    therapeutic_area: str = Field(description="Primary therapeutic area")
    asset_focus: str = Field(description="Asset or focus of the deal")
    deal_type_detailed: DealTypeDetailed = Field(description="Detailed deal type")
    source_url: HttpUrl = Field(description="Primary source URL")
    needs_review: bool = Field(default=False, description="Requires manual review")

    # Optional financial fields
    upfront_value_usd: Optional[Decimal] = Field(
        default=None, description="Upfront value in M USD"
    )
    contingent_payment_usd: Optional[Decimal] = Field(
        default=None, description="Contingent payment in M USD"
    )
    total_deal_value_usd: Optional[Decimal] = Field(
        default=None, description="Total deal value in M USD"
    )
    upfront_pct_total: Optional[Decimal] = Field(
        default=None, description="Upfront as % of total (0.1% precision)"
    )

    # Secondary/Optional fields
    secondary_areas: Optional[str] = Field(
        default=None, description="Secondary therapeutic areas (semicolon-separated)"
    )
    geography: Optional[str] = Field(default=None, description="Target geography (ISO country)")

    # Metadata
    related_urls: list[str] = Field(default_factory=list, description="Related URLs")
    detected_currency: Optional[str] = Field(
        default=None, description="Original currency detected"
    )
    fx_rate: Optional[Decimal] = Field(default=None, description="FX rate to USD")
    fx_source: Optional[str] = Field(default=None, description="FX rate source")
    confidence: Decimal = Field(default=Decimal("1.0"), description="Confidence score 0-1")
    inclusion_reason: str = Field(default="", description="Reason for inclusion")
    exclusion_reason: Optional[str] = Field(default=None, description="Reason for exclusion")
    parser_version: str = Field(default="1.0.0", description="Parser version")
    timestamp_utc: str = Field(description="Processing timestamp UTC")

    # Evidence
    evidence: FieldEvidence = Field(default_factory=FieldEvidence)

    # Deduplication
    canonical_key: Optional[str] = Field(default=None, description="Canonical deduplication key")

    @property
    def deal_type_output(self) -> DealType:
        """Map detailed deal type to output format."""
        if self.deal_type_detailed == DealTypeDetailed.MA:
            return DealType.MA
        else:
            # Licensing, option-to-license, partnership all map to Partnership
            return DealType.PARTNERSHIP

    class Config:
        """Pydantic config."""

        use_enum_values = True
        json_encoders = {Decimal: str}


class ExcelRow(BaseModel):
    """Excel output row matching required schema."""

    date_announced: date
    target: str
    acquirer: str
    upfront_value_m_usd: Optional[Decimal] = None
    contingent_payment_m_usd: Optional[Decimal] = None
    total_deal_value_m_usd: Optional[Decimal] = None
    upfront_as_pct_total: Optional[Decimal] = None
    phase_at_announcement: str
    therapeutic_area: str
    secondary_areas: Optional[str] = None
    asset_focus: str
    deal_type: str  # "M&A" or "Partnership"
    geography: Optional[str] = None
    source_url: str
    needs_review: bool

    @classmethod
    def from_deal(cls, deal: Deal) -> "ExcelRow":
        """Convert Deal to ExcelRow."""
        return cls(
            date_announced=deal.date_announced,
            target=deal.target,
            acquirer=deal.acquirer,
            upfront_value_m_usd=deal.upfront_value_usd,
            contingent_payment_m_usd=deal.contingent_payment_usd,
            total_deal_value_m_usd=deal.total_deal_value_usd,
            upfront_as_pct_total=deal.upfront_pct_total,
            phase_at_announcement=deal.stage if isinstance(deal.stage, str) else deal.stage.value,
            therapeutic_area=deal.therapeutic_area,
            secondary_areas=deal.secondary_areas,
            asset_focus=deal.asset_focus,
            deal_type=deal.deal_type_output if isinstance(deal.deal_type_output, str) else deal.deal_type_output.value,
            geography=deal.geography,
            source_url=str(deal.source_url),
            needs_review=deal.needs_review,
        )
