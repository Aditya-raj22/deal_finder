"""Production pipeline with ChromaDB semantic filtering."""

import gzip
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

from deal_finder.config_loader import load_config, load_ta_vocab
from deal_finder.storage.article_cache_chroma import ChromaArticleCache
from deal_finder.extraction.openai_extractor import OpenAIExtractor
from deal_finder.models import Deal
from deal_finder.output import ExcelWriter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def deals_by_stage(deals: list, stage_keywords: list) -> list:
    """Filter deals by stage keywords (case-insensitive).

    Args:
        deals: List of Deal objects
        stage_keywords: List of stage strings to match (e.g., ["phase 1", "phase I"])

    Returns:
        Filtered list of deals matching any of the stage keywords
    """
    stage_keywords_lower = [s.lower() for s in stage_keywords]
    return [
        deal for deal in deals
        if deal.stage and deal.stage.lower() in stage_keywords_lower
    ]


def run_pipeline(config_path="config/config.yaml"):
    """Run pipeline with ChromaDB semantic search."""

    logger.info("="*80)
    logger.info("DEAL FINDER - ChromaDB Semantic Pipeline")
    logger.info("="*80)

    config = load_config(config_path)
    ta_vocab = load_ta_vocab(config)

    logger.info(f"TA: {config.THERAPEUTIC_AREA}")
    logger.info(f"Date range: {config.START_DATE} to {config.end_date_resolved}")

    # Initialize ChromaDB (use same model as embeddings)
    cache = ChromaArticleCache(embedding_model="all-MiniLM-L6-v2")
    stats = cache.get_stats()
    logger.info(f"ChromaDB: {stats['total_articles']} articles")

    # STEP 1: Semantic search (low threshold = no false negatives)
    logger.info("\n" + "="*80)
    logger.info("STEP 1: Semantic TA Filter (ChromaDB)")
    logger.info("="*80)

    # Build rich query emphasizing deals/transactions in the TA
    query = f"{config.THERAPEUTIC_AREA} deals partnerships acquisitions M&A licensing transactions agreements biotech pharma financial"

    # Get sources filter if available
    sources_filter = getattr(config, 'NEWS_SOURCES', None)
    if sources_filter:
        logger.info(f"Filtering by sources: {', '.join(sources_filter)}")

    articles = cache.search_articles_semantic(
        query=query,
        start_date=config.START_DATE,
        end_date=config.end_date_resolved,
        sources=sources_filter,
        top_k=50000,  # No practical limit (most TAs have <10k matches)
        similarity_threshold=0.20  # Low = minimize false negatives
    )

    logger.info(f"✓ Found {len(articles)} articles (threshold=0.20 for max recall)")

    if not articles:
        logger.warning("No articles found!")
        return

    # Convert to pipeline format
    pipeline_articles = [{
        'url': a['url'],
        'title': a['title'],
        'content': a['content_snippet'],
        'published_date': a['published_date'],
        'source': a['source']
    } for a in articles]

    # STEP 2: OpenAI extraction (with quick filter + dedup + full extraction)
    logger.info("\n" + "="*80)
    logger.info("STEP 2: OpenAI Extraction (Quick Filter + Dedup + Full)")
    logger.info("="*80)

    checkpoint = Path("output/extraction_checkpoint.json.gz")

    if checkpoint.exists():
        logger.info("Loading from checkpoint...")
        with gzip.open(checkpoint, 'rt') as f:
            extractions = json.load(f).get("extractions", [])
        logger.info(f"✓ Loaded {len(extractions)} extractions")
    else:
        # Use MPNet model for dedup too (better than MiniLM)
        extractor = OpenAIExtractor()
        # Accept ALL stages - we'll let users filter in the UI
        all_stages = [
            "preclinical", "pre-clinical",
            "phase 1", "phase I", "phase i",
            "phase 2", "phase II", "phase ii",
            "phase 3", "phase III", "phase iii",
            "phase 4", "phase IV", "phase iv",
            "first-in-human", "FIH",
            "clinical", "discovery", "research",
            "undisclosed", "unknown"
        ]
        extractions = extractor.extract_batch(
            pipeline_articles,
            ta_vocab,
            allowed_stages=all_stages
        )

        # Save checkpoint
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(checkpoint, 'wt') as f:
            json.dump({
                "extractions": extractions,
                "articles": pipeline_articles,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, f)
        logger.info(f"✓ Saved {len(extractions)} extractions")

    # STEP 3: Parse to Deal objects (all stages included)
    logger.info("\n" + "="*80)
    logger.info("STEP 3: Parse to Deal Objects")
    logger.info("="*80)

    deals = []
    rejected = []

    for extraction in extractions:
        if not extraction:
            rejected.append({"reason": "null_extraction"})
            continue

        parsed = extractor.parse_extracted_deal(extraction, config.THERAPEUTIC_AREA)
        if not parsed:
            rejected.append({"reason": "parse_failed"})
            continue

        # No stage filtering - include all stages and let users filter in UI

        # Convert to Deal model
        try:
            # Map confidence string to Decimal
            confidence_map = {'high': Decimal('0.9'), 'medium': Decimal('0.7'), 'low': Decimal('0.5')}
            confidence_str = parsed.get('confidence', 'medium')
            confidence_decimal = confidence_map.get(confidence_str, Decimal('0.7'))

            deal = Deal(
                date_announced=datetime.fromisoformat(parsed['date_announced']).date() if parsed.get('date_announced') else None,
                target=parsed.get('target'),
                acquirer=parsed.get('acquirer'),
                stage=parsed.get('stage'),
                therapeutic_area=parsed.get('therapeutic_area'),
                asset_focus=parsed.get('asset_focus'),
                deal_type_detailed=parsed.get('deal_type'),
                source_url=parsed.get('url'),
                upfront_value_usd=Decimal(str(parsed['upfront_value_usd'])) if parsed.get('upfront_value_usd') else None,
                contingent_payment_usd=Decimal(str(parsed['contingent_payment_usd'])) if parsed.get('contingent_payment_usd') else None,
                total_deal_value_usd=Decimal(str(parsed['total_deal_value_usd'])) if parsed.get('total_deal_value_usd') else None,
                geography=parsed.get('geography'),
                confidence=confidence_decimal,
                timestamp_utc=datetime.now(timezone.utc).isoformat()
            )
            deals.append(deal)
        except Exception as e:
            rejected.append({"reason": "model_error", "error": str(e)})

    logger.info(f"✓ {len(deals)} deals extracted, {len(rejected)} rejected")

    # STEP 4: Split deals by stage and save to 3 Excel files
    if deals:
        logger.info("\n" + "="*80)
        logger.info("STEP 4: Split by Stage & Save to Excel")
        logger.info("="*80)

        # Define stage groups
        early_stages = deals_by_stage(deals, ["preclinical", "pre-clinical", "phase 1", "phase I", "phase i", "first-in-human", "FIH", "discovery"])
        mid_stages = deals_by_stage(deals, ["phase 2", "phase II", "phase ii", "phase 3", "phase III", "phase iii"])
        undisclosed_stages = deals_by_stage(deals, ["unknown", "undisclosed", "not specified", "clinical"])

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        ta_clean = config.THERAPEUTIC_AREA.replace(" ", "_")

        # Save 3 separate files
        files_written = []

        if early_stages:
            output_early = output_dir / f"deals_{ta_clean}_EARLY_STAGE_{timestamp}.xlsx"
            ExcelWriter().write(early_stages, str(output_early))
            logger.info(f"✓ Early Stage (Preclinical/Phase 1): {len(early_stages)} deals → {output_early.name}")
            files_written.append(output_early)

        if mid_stages:
            output_mid = output_dir / f"deals_{ta_clean}_MID_STAGE_{timestamp}.xlsx"
            ExcelWriter().write(mid_stages, str(output_mid))
            logger.info(f"✓ Mid Stage (Phase 2/3): {len(mid_stages)} deals → {output_mid.name}")
            files_written.append(output_mid)

        if undisclosed_stages:
            output_unk = output_dir / f"deals_{ta_clean}_UNDISCLOSED_{timestamp}.xlsx"
            ExcelWriter().write(undisclosed_stages, str(output_unk))
            logger.info(f"✓ Undisclosed/Unknown: {len(undisclosed_stages)} deals → {output_unk.name}")
            files_written.append(output_unk)

        logger.info(f"\n✓ Saved {len(files_written)} Excel files ({len(deals)} total deals)")

    # Save parsing checkpoint
    with gzip.open("output/parsing_checkpoint.json.gz", 'wt') as f:
        # Use model_dump to handle Decimal, date, and other non-JSON types
        json.dump({
            "extracted_deals": [d.model_dump(mode='json') for d in deals],
            "extraction_rejected": rejected,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, f)

    logger.info("\n" + "="*80)
    logger.info(f"COMPLETE! {len(deals)} deals found")
    logger.info("="*80)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    run_pipeline(args.config)
