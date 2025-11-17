"""Incremental update: Crawl new articles and embed them.

This script combines crawl.py and embed.py for daily/weekly updates.
It only fetches NEW articles (using URL index) and embeds them.

Usage:
    # Daily update
    python update.py

    # Weekly update
    python update.py --start-date 2025-01-09

    # Custom date range
    python update.py --start-date 2025-01-01 --end-date 2025-01-15

Features:
- Incremental: URL index skips already-discovered URLs
- Efficient: Only crawls and embeds new articles
- Resumable: Both stages are independently resumable
"""

import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

from deal_finder.storage.content_cache import ContentCache
from deal_finder.storage.embedding_service import EmbeddingService

# Import crawl and embed functions
import sys
sys.path.insert(0, str(Path(__file__).parent))

from crawl import crawl_and_store
from embed import embed_articles

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def incremental_update(
    start_date: str = None,
    end_date: str = None,
    config_path: str = "config/config.yaml",
    crawl_workers: int = 30,
    embed_batch_size: int = 100,
    embedding_model: str = "all-mpnet-base-v2",
    skip_crawl: bool = False,
    skip_embed: bool = False
):
    """Run incremental update (crawl new + embed new).

    Args:
        start_date: Start date (YYYY-MM-DD, default: yesterday)
        end_date: End date (YYYY-MM-DD, default: today)
        config_path: Path to config file
        crawl_workers: Number of parallel crawl workers
        embed_batch_size: ChromaDB batch size for embedding
        embedding_model: sentence-transformers model name
        skip_crawl: Skip crawl stage (only embed)
        skip_embed: Skip embed stage (only crawl)
    """
    # Default date range: yesterday to today (for daily updates)
    if not start_date:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        start_date = yesterday.isoformat()

    if not end_date:
        end_date = datetime.now(timezone.utc).date().isoformat()

    logger.info("="*80)
    logger.info("INCREMENTAL UPDATE")
    logger.info("="*80)
    logger.info(f"Date range: {start_date} to {end_date}")

    # Show current status
    logger.info("\nCurrent status:")
    logger.info("-" * 80)
    cache = ContentCache()
    stats = cache.get_stats()
    logger.info(f"Content cache: {stats['total_articles']} articles")
    logger.info(f"  Pending: {stats['by_status'].get('pending', 0)}")
    logger.info(f"  Embedded: {stats['by_status'].get('embedded', 0)}")
    logger.info(f"  Failed: {stats['by_status'].get('failed', 0)}")
    cache.close()

    # Stage 1: Crawl new articles
    if not skip_crawl:
        logger.info("\n" + "="*80)
        logger.info("STAGE 1: CRAWL NEW ARTICLES")
        logger.info("="*80)

        try:
            crawl_and_store(
                start_date=start_date,
                end_date=end_date,
                config_path=config_path,
                max_workers=crawl_workers,
                checkpoint_every=1000
            )
        except Exception as e:
            logger.error(f"Crawl failed: {e}")
            if not skip_embed:
                logger.info("Continuing to embed stage despite crawl failure...")
    else:
        logger.info("\nSkipping crawl stage (--skip-crawl)")

    # Stage 2: Embed pending articles
    if not skip_embed:
        logger.info("\n" + "="*80)
        logger.info("STAGE 2: EMBED PENDING ARTICLES")
        logger.info("="*80)

        # Import here to avoid circular dependency
        from deal_finder.storage.embedding_service import EmbeddingService

        service = EmbeddingService(
            embedding_model=embedding_model
        )

        try:
            # Get pending count
            progress = service.get_progress()
            pending_count = progress['sync_status']['pending']

            if pending_count > 0:
                logger.info(f"Embedding {pending_count} pending articles...")

                # Use embed_articles function but don't reinitialize logging
                results = service.process_pending_articles(
                    batch_size=embed_batch_size,
                    checkpoint_every=1000
                )

                logger.info(
                    f"✓ Embedding complete: {results['succeeded']} succeeded, "
                    f"{results['failed']} failed"
                )
            else:
                logger.info("No pending articles to embed")

        except Exception as e:
            logger.error(f"Embedding failed: {e}")

        finally:
            service.close()
    else:
        logger.info("\nSkipping embed stage (--skip-embed)")

    # Final status
    logger.info("\n" + "="*80)
    logger.info("UPDATE COMPLETE")
    logger.info("="*80)

    cache = ContentCache()
    final_stats = cache.get_stats()
    logger.info(f"Content cache: {final_stats['total_articles']} articles")
    logger.info(f"  Pending: {final_stats['by_status'].get('pending', 0)}")
    logger.info(f"  Embedded: {final_stats['by_status'].get('embedded', 0)}")
    logger.info(f"  Failed: {final_stats['by_status'].get('failed', 0)}")
    cache.close()

    # Verify sync
    service = EmbeddingService(embedding_model=embedding_model)
    chroma_count = service.chroma_cache.get_stats()['total_articles']
    logger.info(f"\nChromaDB: {chroma_count} articles")

    embedded_count = final_stats['by_status'].get('embedded', 0)
    if embedded_count == chroma_count:
        logger.info("✓ Sync verified: Content cache and ChromaDB match")
    else:
        logger.warning(
            f"⚠ Sync mismatch: {embedded_count} embedded but {chroma_count} in ChromaDB"
        )

    service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Incremental update: crawl new articles and embed them"
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Start date (YYYY-MM-DD, default: yesterday)"
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date (YYYY-MM-DD, default: today)"
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--crawl-workers",
        type=int,
        default=30,
        help="Number of parallel crawl workers (default: 30)"
    )
    parser.add_argument(
        "--embed-batch-size",
        type=int,
        default=100,
        help="ChromaDB batch size for embedding (default: 100)"
    )
    parser.add_argument(
        "--embedding-model",
        default="all-mpnet-base-v2",
        choices=["all-MiniLM-L6-v2", "all-mpnet-base-v2"],
        help="Embedding model (default: all-mpnet-base-v2)"
    )
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip crawl stage (only embed pending)"
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip embed stage (only crawl)"
    )

    args = parser.parse_args()

    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    incremental_update(
        start_date=args.start_date,
        end_date=args.end_date,
        config_path=args.config,
        crawl_workers=args.crawl_workers,
        embed_batch_size=args.embed_batch_size,
        embedding_model=args.embedding_model,
        skip_crawl=args.skip_crawl,
        skip_embed=args.skip_embed
    )
