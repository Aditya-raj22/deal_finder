"""End-to-end test using ONLY Perplexity - no manual scraping."""

import json
import logging
import os
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def perplexity_end_to_end():
    """Use Perplexity for BOTH discovery AND extraction - true end-to-end."""
    from deal_finder.config_loader import load_config, load_ta_vocab, load_aliases
    from deal_finder.normalization import CompanyCanonicalizer
    from deal_finder.models import Deal, DealTypeDetailed, DevelopmentStage, FieldEvidence
    from deal_finder.output import ExcelWriter
    import requests

    logger.info("=" * 70)
    logger.info("PERPLEXITY END-TO-END TEST")
    logger.info("Let Perplexity do ALL the work (no manual scraping!)")
    logger.info("=" * 70)

    # Check API key
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.error("\n❌ PERPLEXITY_API_KEY not set!")
        return 1

    logger.info("\n✓ API key found")

    # Load config
    logger.info("\n1. Loading configuration...")
    config_path = Path(__file__).parent / "config" / "config.yaml"
    config = load_config(str(config_path))
    ta_vocab = load_ta_vocab(config)
    aliases = load_aliases(config)

    ta_name = ta_vocab.get("therapeutic_area", "biotech")
    ta_includes = ta_vocab.get("includes", [])
    ta_excludes = ta_vocab.get("excludes", [])

    logger.info(f"   Therapeutic Area: {ta_name}")
    logger.info(f"   Key terms: {', '.join(ta_includes[:5])}...")

    # Single Perplexity prompt that does EVERYTHING
    logger.info("\n2. Asking Perplexity to find AND extract deals...")
    logger.info("   (One API call does discovery + extraction!)")

    mega_prompt = f"""Find recent biotech/pharma deals from 2024 that match this therapeutic area: {ta_name}

THERAPEUTIC AREA CRITERIA:
- Include terms: {', '.join(ta_includes[:20])}
- Exclude terms: {', '.join(ta_excludes[:10])}
- Must be early stage: preclinical, phase 1, or phase I

DEAL TYPES TO FIND:
- M&A (mergers & acquisitions)
- Partnerships and collaborations
- Licensing deals
- Option agreements

Search reliable biotech news sources like FierceBiotech, FiercePharma, GEN, BioPharma Dive, Endpoints News.

For each deal you find, extract:
1. **article_url**: Direct link to article
2. **title**: Article headline
3. **published_date**: When announced (YYYY-MM-DD)
4. **parties**:
   - acquirer: Company acquiring/licensing
   - target: Company being acquired/partner
5. **deal_type**: "M&A", "partnership", "licensing", or "option"
6. **money**:
   - upfront_value: Upfront payment
   - total_deal_value: Total value
   - currency: "USD", "EUR", etc.
7. **asset_focus**: Drug/therapy name
8. **stage**: "preclinical", "phase 1", "phase I"
9. **therapeutic_area_match**: true if matches {ta_name}, false otherwise
10. **key_evidence**: Brief quote from article

Return JSON array with up to 5 deals:
[
  {{
    "article_url": "https://...",
    "title": "...",
    "published_date": "2024-01-15",
    "parties": {{"acquirer": "...", "target": "..."}},
    "deal_type": "M&A",
    "money": {{"upfront_value": 100000000, "total_deal_value": 500000000, "currency": "USD"}},
    "asset_focus": "...",
    "stage": "preclinical",
    "therapeutic_area_match": true,
    "key_evidence": "..."
  }}
]

IMPORTANT: Only include deals that match the therapeutic area. Return empty array if no matches."""

    # Call Perplexity
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    })

    logger.info("   Calling Perplexity API...")
    logger.info("   (This may take 30-60 seconds)")

    try:
        response = session.post(
            "https://api.perplexity.ai/chat/completions",
            json={
                "model": "sonar-pro",  # Best model for deep search + extraction
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a biotech deal research assistant. Search the web for recent deals and return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": mega_prompt
                    }
                ],
                "temperature": 0.0,  # Maximum determinism for accuracy
                "max_tokens": 8000,  # More tokens for comprehensive extraction
                "search_domain_filter": [
                    "fiercebiotech.com"
                ],  # Limited to FierceBiotech only (cost optimization)
                "search_recency_filter": "month"  # Recent deals only for test
            },
            timeout=180  # Longer timeout for sonar-pro deep search
        )
        if response.status_code != 200:
            logger.error(f"   API Error: {response.status_code}")
            logger.error(f"   Response: {response.text}")
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        logger.info("   ✓ Got response from Perplexity")

        # Parse JSON
        try:
            deals_data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract from markdown
            import re
            match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
            if match:
                deals_data = json.loads(match.group(1))
            else:
                logger.error(f"Failed to parse JSON: {content[:500]}")
                return 1

        if not deals_data:
            logger.warning("\n⚠ Perplexity found no matching deals")
            logger.info("Try adjusting therapeutic area includes/excludes")
            return 1

        logger.info(f"\n✅ Perplexity found {len(deals_data)} deals!")

        # Convert to Deal objects
        logger.info("\n3. Converting to Deal objects...")
        deals = []
        company_canonicalizer = CompanyCanonicalizer(aliases)

        deal_type_map = {
            "m&a": DealTypeDetailed.MA,
            "ma": DealTypeDetailed.MA,
            "merger": DealTypeDetailed.MA,
            "acquisition": DealTypeDetailed.MA,
            "partnership": DealTypeDetailed.PARTNERSHIP,
            "collaboration": DealTypeDetailed.PARTNERSHIP,
            "licensing": DealTypeDetailed.LICENSING,
            "option": DealTypeDetailed.OPTION_TO_LICENSE,
        }

        stage_map = {
            "preclinical": DevelopmentStage.PRECLINICAL,
            "phase 1": DevelopmentStage.PHASE_1,
            "phase i": DevelopmentStage.PHASE_1,
        }

        for i, deal_data in enumerate(deals_data, 1):
            logger.info(f"\n   Deal {i}:")
            logger.info(f"   Title: {deal_data.get('title', 'N/A')}")

            parties = deal_data.get("parties", {})
            acquirer = parties.get("acquirer")
            target = parties.get("target")

            if not acquirer or not target:
                logger.warning(f"   ✗ Skipping (missing parties)")
                continue

            logger.info(f"   Acquirer: {acquirer}")
            logger.info(f"   Target: {target}")

            # Parse date
            date_str = deal_data.get("published_date")
            try:
                date_announced = datetime.strptime(date_str, "%Y-%m-%d").date()
            except:
                logger.warning(f"   ✗ Skipping (invalid date: {date_str})")
                continue

            # Parse deal type
            deal_type_str = deal_data.get("deal_type", "").lower()
            deal_type = deal_type_map.get(deal_type_str, DealTypeDetailed.PARTNERSHIP)

            # Parse stage
            stage_str = deal_data.get("stage", "").lower()
            stage = stage_map.get(stage_str, DevelopmentStage.PRECLINICAL)

            # Parse money
            money = deal_data.get("money", {})
            upfront_usd = Decimal(str(money.get("upfront_value", 0))) if money.get("upfront_value") else None
            total_usd = Decimal(str(money.get("total_deal_value", 0))) if money.get("total_deal_value") else None
            currency = money.get("currency", "USD")

            logger.info(f"   Type: {deal_type}")
            logger.info(f"   Stage: {stage}")
            if total_usd:
                logger.info(f"   Value: ${total_usd:,.0f} {currency}")

            # Create Deal
            deal = Deal(
                date_announced=date_announced,
                target=company_canonicalizer.canonicalize(target),
                acquirer=company_canonicalizer.canonicalize(acquirer),
                stage=stage,
                therapeutic_area=ta_name,
                asset_focus=deal_data.get("asset_focus", "Undisclosed"),
                deal_type_detailed=deal_type,
                source_url=deal_data.get("article_url", ""),
                needs_review=not deal_data.get("therapeutic_area_match", False),
                upfront_value_usd=upfront_usd,
                total_deal_value_usd=total_usd,
                detected_currency=currency,
                fx_rate=Decimal("1.0"),
                fx_source="Perplexity",
                evidence=FieldEvidence(),
                inclusion_reason="Perplexity end-to-end search",
                timestamp_utc=datetime.utcnow().isoformat(),
            )

            deals.append(deal)

        if not deals:
            logger.warning("\n⚠ No valid deals after parsing")
            return 1

        # Save to Excel
        logger.info(f"\n4. Saving {len(deals)} deals to Excel...")
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"perplexity_e2e_{uuid.uuid4().hex[:8]}.xlsx"

        excel_writer = ExcelWriter()
        excel_writer.write(deals, str(output_file))

        logger.info(f"   ✓ Saved to: {output_file}")

        logger.info("\n" + "=" * 70)
        logger.info("✅ PERPLEXITY END-TO-END TEST COMPLETE!")
        logger.info("=" * 70)
        logger.info(f"\nResults:")
        logger.info(f"  • Perplexity searched the web")
        logger.info(f"  • Found and extracted {len(deals)} matching deals")
        logger.info(f"  • Saved to: {output_file}")
        logger.info(f"\nNo manual scraping required! 🎉")

        return 0

    except Exception as e:
        logger.error(f"\n❌ API call failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(perplexity_end_to_end())
