"""Reset ChromaDB to use faster embedding model and re-embed from scratch.

Use this when you want to switch embedding models (e.g., 768-dim to 384-dim).
This will:
1. Delete existing ChromaDB collection
2. Reset all articles to 'pending' status
3. Re-embed with new model
"""

import logging
import argparse
from pathlib import Path

from deal_finder.storage.content_cache import ContentCache
from deal_finder.storage.article_cache_chroma import ChromaArticleCache
from deal_finder.storage.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def reset_and_embed(
    embedding_model: str = "all-MiniLM-L6-v2",
    batch_size: int = 500
):
    """Reset ChromaDB and re-embed with new model.

    Args:
        embedding_model: New embedding model to use
        batch_size: Batch size for embedding
    """
    logger.info("="*80)
    logger.info("RESET & RE-EMBED with Faster Model")
    logger.info("="*80)
    logger.warning(f"This will DELETE all existing embeddings and start fresh!")
    logger.info(f"New model: {embedding_model}")
    logger.info(f"Batch size: {batch_size}")

    # Step 1: Reset content cache statuses
    logger.info("\n1️⃣ Resetting article statuses to 'pending'...")
    content_cache = ContentCache("output/content_cache.db")

    # Reset embedded articles back to pending
    conn = content_cache.conn
    cursor = conn.execute("""
        UPDATE articles
        SET status = 'pending', error_message = NULL
        WHERE status IN ('embedded', 'failed')
    """)
    reset_count = cursor.rowcount
    conn.commit()
    logger.info(f"✓ Reset {reset_count} articles to pending")

    # Step 2: Delete ChromaDB collection
    logger.info("\n2️⃣ Deleting old ChromaDB collection...")
    try:
        chroma_cache = ChromaArticleCache(
            db_path="output/chroma_db",
            embedding_model=embedding_model
        )
        chroma_cache.delete_all()
        logger.info(f"✓ Deleted old collection")
    except Exception as e:
        logger.warning(f"Could not delete collection: {e}")

    # Step 3: Start embedding with new model
    logger.info("\n3️⃣ Starting fresh embedding with new model...")
    logger.info("-" * 80)

    service = EmbeddingService(
        content_cache_path="output/content_cache.db",
        chroma_db_path="output/chroma_db",
        embedding_model=embedding_model
    )

    # Show status
    progress = service.get_progress()
    logger.info(f"Total articles to embed: {progress['sync_status']['pending']}")

    # Process all pending
    results = service.process_pending_articles(
        batch_size=batch_size,
        checkpoint_every=1000
    )

    # Final status
    logger.info("\n" + "="*80)
    logger.info("RESET & RE-EMBED COMPLETE")
    logger.info("="*80)
    logger.info(f"✓ Processed: {results['processed']} articles")
    logger.info(f"✓ Succeeded: {results['succeeded']} articles")
    logger.info(f"✗ Failed: {results['failed']} articles")

    service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reset and re-embed with new model"
    )
    parser.add_argument(
        "--embedding-model",
        default="all-MiniLM-L6-v2",
        choices=["all-MiniLM-L6-v2", "all-mpnet-base-v2"],
        help="Embedding model to use (default: all-MiniLM-L6-v2 for speed)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size (default: 500)"
    )

    args = parser.parse_args()

    logger.warning("⚠️  This will delete all existing embeddings!")
    response = input("Are you sure you want to continue? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        reset_and_embed(
            embedding_model=args.embedding_model,
            batch_size=args.batch_size
        )
    else:
        logger.info("Cancelled.")
