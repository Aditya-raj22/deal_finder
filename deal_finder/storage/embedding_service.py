"""Embedding service for processing articles from content cache to ChromaDB.

Handles the embedding generation pipeline:
1. Fetch pending articles from SQLite content cache
2. Generate embeddings using sentence transformers
3. Upsert to ChromaDB for semantic search
4. Update status in content cache

Features:
- Resumable: Only processes articles with status='pending'
- Batch processing: Efficient batching for both embedding and ChromaDB
- Error handling: Tracks failed articles with error messages
- Progress tracking: Logs progress every N articles
"""

import logging
import time
import multiprocessing as mp
from typing import List, Dict, Any, Optional
from pathlib import Path
from functools import partial

from deal_finder.storage.content_cache import ContentCache
from deal_finder.storage.article_cache_chroma import ChromaArticleCache

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for embedding articles and syncing to ChromaDB.

    Two-stage process:
    1. Content Cache (SQLite): Source of truth for article content + status
    2. ChromaDB: Vector embeddings for semantic search
    """

    def __init__(
        self,
        content_cache_path: str = "output/content_cache.db",
        chroma_db_path: str = "output/chroma_db",
        embedding_model: str = "all-mpnet-base-v2"
    ):
        """Initialize embedding service.

        Args:
            content_cache_path: Path to SQLite content cache
            chroma_db_path: Path to ChromaDB storage
            embedding_model: sentence-transformers model name
                - 'all-MiniLM-L6-v2': Fast, good accuracy (384 dim)
                - 'all-mpnet-base-v2': Slower, better accuracy (768 dim) [RECOMMENDED]
        """
        self.content_cache = ContentCache(db_path=content_cache_path)
        self.chroma_cache = ChromaArticleCache(
            db_path=chroma_db_path,
            embedding_model=embedding_model
        )
        self.embedding_model = embedding_model

        logger.info(f"Initialized embedding service with model: {embedding_model}")

    def process_pending_articles(
        self,
        batch_size: int = 100,
        max_articles: Optional[int] = None,
        checkpoint_every: int = 1000
    ) -> Dict[str, int]:
        """Process all pending articles (resumable).

        This is the main method for embedding articles. It:
        1. Fetches articles with status='pending' from content cache
        2. Batches them for efficient embedding
        3. Upserts to ChromaDB
        4. Updates status in content cache

        Args:
            batch_size: ChromaDB batch size (default 100)
            max_articles: Maximum articles to process (None = all pending)
            checkpoint_every: Log progress every N articles

        Returns:
            Dict with counts: {'processed': N, 'succeeded': M, 'failed': K}
        """
        # Get total pending count
        stats = self.content_cache.get_stats()
        pending_count = stats['by_status'].get('pending', 0)

        if pending_count == 0:
            logger.info("No pending articles to process")
            return {'processed': 0, 'succeeded': 0, 'failed': 0}

        # Limit if specified
        total_to_process = min(pending_count, max_articles) if max_articles else pending_count
        logger.info(f"Processing {total_to_process} pending articles (batch_size={batch_size})")

        processed = 0
        succeeded = 0
        failed = 0
        offset = 0
        start_time = time.time()
        last_checkpoint_time = start_time

        while processed < total_to_process:
            # Fetch batch of pending articles
            limit = min(batch_size, total_to_process - processed)
            articles = self.content_cache.get_pending_articles(limit=limit, offset=0)

            if not articles:
                logger.info("No more pending articles")
                break

            # Process batch with timing
            batch_start = time.time()
            batch_results = self._process_batch(articles)
            batch_time = time.time() - batch_start

            succeeded += batch_results['succeeded']
            failed += batch_results['failed']
            processed += len(articles)

            # Calculate metrics
            elapsed = time.time() - start_time
            articles_per_sec = processed / elapsed if elapsed > 0 else 0
            remaining = total_to_process - processed
            eta_seconds = remaining / articles_per_sec if articles_per_sec > 0 else 0

            # Checkpoint logging
            if processed % checkpoint_every == 0 or processed == total_to_process:
                checkpoint_elapsed = time.time() - last_checkpoint_time
                logger.info(
                    f"Progress: {processed}/{total_to_process} articles "
                    f"({100*processed/total_to_process:.1f}%) | "
                    f"{articles_per_sec:.1f} articles/sec | "
                    f"ETA: {_format_time(eta_seconds)} | "
                    f"Last {checkpoint_every}: {_format_time(checkpoint_elapsed)}"
                )
                last_checkpoint_time = time.time()

            # Show per-batch progress for visibility
            logger.info(
                f"  Batch {processed//batch_size}: {len(articles)} articles in {batch_time:.1f}s "
                f"({len(articles)/batch_time:.1f} articles/sec)"
            )

        logger.info(
            f"✓ Embedding complete: {processed} processed, "
            f"{succeeded} succeeded, {failed} failed"
        )

        return {
            'processed': processed,
            'succeeded': succeeded,
            'failed': failed
        }

    def _process_batch(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
        """Process a batch of articles.

        Args:
            articles: List of article dicts from content cache

        Returns:
            Dict with counts: {'succeeded': N, 'failed': M}
        """
        succeeded = 0
        failed = 0

        # Prepare batch for ChromaDB (filter out articles with missing data)
        valid_articles = []
        for article in articles:
            # Validate required fields
            if not article.get('url') or not article.get('content'):
                logger.warning(f"Skipping article with missing data: {article.get('url', 'unknown')}")
                self.content_cache.mark_embedded(
                    article['url'],
                    success=False,
                    error_message="Missing required fields"
                )
                failed += 1
                continue

            valid_articles.append(article)

        # Batch upsert to ChromaDB
        if valid_articles:
            try:
                self.chroma_cache.upsert_batch(valid_articles, batch_size=len(valid_articles))

                # Mark all as successfully embedded
                urls = [a['url'] for a in valid_articles]
                self.content_cache.mark_embedded_batch(urls, success=True)
                succeeded += len(valid_articles)

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")

                # Mark individually to isolate failures
                for article in valid_articles:
                    try:
                        self.chroma_cache.upsert_article(
                            url=article['url'],
                            title=article.get('title', ''),
                            content=article.get('content', ''),
                            published_date=article.get('published_date', ''),
                            source=article.get('source', 'Unknown'),
                            lastmod=article.get('lastmod')
                        )
                        self.content_cache.mark_embedded(article['url'], success=True)
                        succeeded += 1

                    except Exception as e2:
                        logger.error(f"Failed to embed article {article['url']}: {e2}")
                        self.content_cache.mark_embedded(
                            article['url'],
                            success=False,
                            error_message=str(e2)
                        )
                        failed += 1

        return {'succeeded': succeeded, 'failed': failed}

    def retry_failed_articles(
        self,
        batch_size: int = 100,
        max_retries: Optional[int] = None
    ) -> Dict[str, int]:
        """Retry articles that previously failed embedding.

        Args:
            batch_size: ChromaDB batch size
            max_retries: Maximum articles to retry (None = all failed)

        Returns:
            Dict with counts: {'processed': N, 'succeeded': M, 'failed': K}
        """
        logger.info("Resetting failed articles to pending...")
        reset_count = self.content_cache.reset_failed_to_pending()
        logger.info(f"Reset {reset_count} failed articles to pending")

        if reset_count == 0:
            return {'processed': 0, 'succeeded': 0, 'failed': 0}

        # Process the now-pending articles
        return self.process_pending_articles(
            batch_size=batch_size,
            max_articles=max_retries
        )

    def get_progress(self) -> Dict[str, Any]:
        """Get embedding progress statistics.

        Returns:
            Dict with content cache stats and ChromaDB stats
        """
        content_stats = self.content_cache.get_stats()
        chroma_stats = self.chroma_cache.get_stats()

        return {
            'content_cache': content_stats,
            'chroma_cache': chroma_stats,
            'sync_status': {
                'pending': content_stats['by_status'].get('pending', 0),
                'embedded': content_stats['by_status'].get('embedded', 0),
                'failed': content_stats['by_status'].get('failed', 0),
                'in_chromadb': chroma_stats['total_articles']
            }
        }

    def verify_sync(self) -> bool:
        """Verify content cache and ChromaDB are in sync.

        Returns:
            True if embedded count matches ChromaDB count
        """
        content_stats = self.content_cache.get_stats()
        chroma_stats = self.chroma_cache.get_stats()

        embedded_count = content_stats['by_status'].get('embedded', 0)
        chromadb_count = chroma_stats['total_articles']

        if embedded_count == chromadb_count:
            logger.info(f"✓ Sync verified: {embedded_count} articles in both caches")
            return True
        else:
            logger.warning(
                f"⚠ Sync mismatch: {embedded_count} embedded in content cache, "
                f"but {chromadb_count} in ChromaDB"
            )
            return False

    def close(self):
        """Close database connections."""
        self.content_cache.close()
        # ChromaDB client doesn't need explicit close


def _format_time(seconds: float) -> str:
    """Format seconds into human-readable time string.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted string like "2h 15m" or "45s"
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"
