"""Fast embedding script with optimized settings.

Speed improvements:
1. Larger batch sizes (500 instead of 100)
2. Faster model option (all-MiniLM-L6-v2)
3. Better progress tracking
"""

import logging
import argparse
from pathlib import Path

from deal_finder.storage.embedding_service import EmbeddingService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def embed_articles_fast(
    batch_size: int = 500,  # Increased from 100
    max_articles: int = None,
    checkpoint_every: int = 1000,
    embedding_model: str = "all-MiniLM-L6-v2",  # 3x faster than mpnet
    retry_failed: bool = False
):
    """Generate embeddings with optimized settings for speed.

    Speed comparison:
    - all-MiniLM-L6-v2: ~3-4x faster, 384 dim, good quality
    - all-mpnet-base-v2: slower, 768 dim, better quality

    Args:
        batch_size: ChromaDB batch size (default: 500, up from 100)
        max_articles: Maximum articles to process (None = all pending)
        checkpoint_every: Log progress every N articles (default: 1000)
        embedding_model: sentence-transformers model name
        retry_failed: If True, retry previously failed articles
    """
    logger.info("="*80)
    logger.info("FAST EMBED: Optimized Settings")
    logger.info("="*80)
    logger.info(f"Embedding model: {embedding_model}")
    logger.info(f"Batch size: {batch_size} (larger = faster)")
    logger.info(f"Checkpoint every: {checkpoint_every} articles")

    # Initialize embedding service
    service = EmbeddingService(
        content_cache_path="output/content_cache.db",
        chroma_db_path="output/chroma_db",
        embedding_model=embedding_model
    )

    # Show initial progress
    logger.info("\nInitial status:")
    logger.info("-" * 80)
    progress = service.get_progress()
    _print_progress(progress)

    # Retry failed articles if requested
    if retry_failed:
        logger.info("\nRetrying failed articles...")
        logger.info("-" * 80)
        retry_results = service.retry_failed_articles(
            batch_size=batch_size,
            max_retries=max_articles
        )
        logger.info(
            f"Retry complete: {retry_results['succeeded']} succeeded, "
            f"{retry_results['failed']} failed"
        )

    # Process pending articles
    logger.info("\nProcessing pending articles...")
    logger.info("-" * 80)

    results = service.process_pending_articles(
        batch_size=batch_size,
        max_articles=max_articles,
        checkpoint_every=checkpoint_every
    )

    # Final status
    logger.info("\n" + "="*80)
    logger.info("EMBED COMPLETE")
    logger.info("="*80)
    logger.info(f"✓ Processed: {results['processed']} articles")
    logger.info(f"✓ Succeeded: {results['succeeded']} articles")
    logger.info(f"✗ Failed: {results['failed']} articles")

    # Show final progress
    logger.info("\nFinal status:")
    logger.info("-" * 80)
    final_progress = service.get_progress()
    _print_progress(final_progress)

    # Verify sync
    logger.info("\nVerifying sync...")
    logger.info("-" * 80)
    service.verify_sync()

    # Show failed articles if any
    if results['failed'] > 0:
        logger.info("\nFailed articles (last 10):")
        logger.info("-" * 80)
        failed = service.content_cache.get_failed_articles(limit=10)
        for article in failed:
            logger.warning(
                f"  • {article['url'][:80]}\n"
                f"    Source: {article['source']}, Error: {article['error_message']}"
            )
        logger.info(f"\nTo retry failed articles, run: python scripts/embed_fast.py --retry-failed")

    service.close()


def _print_progress(progress: dict):
    """Print progress statistics."""
    content_stats = progress['content_cache']
    sync_status = progress['sync_status']

    logger.info(f"Content Cache (SQLite):")
    logger.info(f"  Total articles: {content_stats['total_articles']}")
    logger.info(f"  Pending: {sync_status['pending']}")
    logger.info(f"  Embedded: {sync_status['embedded']}")
    logger.info(f"  Failed: {sync_status['failed']}")

    logger.info(f"\nChromaDB (Vector Search):")
    logger.info(f"  Total articles: {sync_status['in_chromadb']}")

    logger.info(f"\nBy source:")
    for source_stat in content_stats['by_source'][:10]:  # Top 10 sources
        logger.info(f"  {source_stat['source']}: {source_stat['count']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fast embedding generation with optimized settings"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="ChromaDB batch size (default: 500 for speed)"
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Maximum articles to process (default: all pending)"
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=1000,
        help="Log progress every N articles (default: 1000)"
    )
    parser.add_argument(
        "--embedding-model",
        default="all-MiniLM-L6-v2",
        choices=["all-MiniLM-L6-v2", "all-mpnet-base-v2"],
        help="Embedding model (default: all-MiniLM-L6-v2 for speed)"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry previously failed articles"
    )

    args = parser.parse_args()

    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    embed_articles_fast(
        batch_size=args.batch_size,
        max_articles=args.max_articles,
        checkpoint_every=args.checkpoint_every,
        embedding_model=args.embedding_model,
        retry_failed=args.retry_failed
    )
