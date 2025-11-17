"""SQLite-based content cache with embedding status tracking.

This cache stores article content and tracks embedding status for resumable processing.
Separates content storage from vector embeddings for better resilience and flexibility.

Architecture:
- SQLite: Source of truth for all fetched articles + status
- ChromaDB: Vector embeddings for semantic search (populated from SQLite)

Benefits:
- Crash-resistant: Both crawl and embed stages auto-resume
- Queryable: Check status, find failed articles, count pending
- Flexible: Re-embed without re-crawling
- Atomic: ACID guarantees from SQLite
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ContentCache:
    """SQLite cache for article content with embedding status tracking.

    Status flow:
        pending -> embedded (success)
        pending -> failed (error during embedding)

    Crawl stage: Inserts articles with status='pending'
    Embed stage: Processes pending articles, updates status to 'embedded'/'failed'
    """

    def __init__(self, db_path: str = "output/content_cache.db"):
        """Initialize content cache.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Access columns by name

        self._create_tables()
        logger.info(f"Initialized content cache at {db_path}")

    def _create_tables(self):
        """Create tables if they don't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                published_date TEXT,
                source TEXT,
                fetched_at TEXT,
                embedding_status TEXT DEFAULT 'pending',
                embedded_at TEXT,
                error_message TEXT,
                lastmod TEXT
            )
        """)

        # Indexes for common queries
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embedding_status
            ON articles(embedding_status)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source
            ON articles(source)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_published_date
            ON articles(published_date)
        """)

        self.conn.commit()

    def upsert_article(
        self,
        url: str,
        title: str,
        content: str,
        published_date: str,
        source: str,
        lastmod: Optional[str] = None
    ) -> bool:
        """Insert or update article (resets embedding status to pending).

        Args:
            url: Article URL (primary key)
            title: Article title
            content: Full article content
            published_date: Publication date (YYYY-MM-DD)
            source: Source name
            lastmod: Last modified date (optional)

        Returns:
            True if successful
        """
        fetched_at = datetime.now(timezone.utc).isoformat()

        try:
            self.conn.execute("""
                INSERT INTO articles
                (url, title, content, published_date, source, fetched_at, lastmod, embedding_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    published_date = excluded.published_date,
                    source = excluded.source,
                    fetched_at = excluded.fetched_at,
                    lastmod = excluded.lastmod,
                    embedding_status = 'pending',
                    embedded_at = NULL,
                    error_message = NULL
            """, (url, title, content, published_date, source, fetched_at, lastmod))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to upsert article {url}: {e}")
            return False

    def upsert_batch(
        self,
        articles: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> int:
        """Batch insert articles (much faster than one-by-one).

        Args:
            articles: List of article dicts with keys: url, title, content, published_date, source
            batch_size: Commit every N articles (default 1000)

        Returns:
            Number of articles successfully inserted
        """
        fetched_at = datetime.now(timezone.utc).isoformat()
        inserted = 0

        for i, article in enumerate(articles):
            try:
                self.conn.execute("""
                    INSERT INTO articles
                    (url, title, content, published_date, source, fetched_at, lastmod, embedding_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                    ON CONFLICT(url) DO UPDATE SET
                        title = excluded.title,
                        content = excluded.content,
                        published_date = excluded.published_date,
                        source = excluded.source,
                        fetched_at = excluded.fetched_at,
                        lastmod = excluded.lastmod,
                        embedding_status = 'pending',
                        embedded_at = NULL,
                        error_message = NULL
                """, (
                    article['url'],
                    article.get('title', ''),
                    article.get('content', ''),
                    article.get('published_date', ''),
                    article.get('source', 'Unknown'),
                    fetched_at,
                    article.get('lastmod', None)
                ))
                inserted += 1

                # Commit in batches for performance
                if (i + 1) % batch_size == 0:
                    self.conn.commit()
                    logger.info(f"Committed batch: {i + 1}/{len(articles)} articles")

            except Exception as e:
                logger.error(f"Failed to insert article {article.get('url', 'unknown')}: {e}")

        # Final commit
        self.conn.commit()
        logger.info(f"Batch insert complete: {inserted}/{len(articles)} articles")
        return inserted

    def get_pending_articles(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get articles that need embedding.

        Args:
            limit: Maximum number of articles to return (None = all)
            offset: Skip first N articles (for pagination)

        Returns:
            List of article dicts with status='pending'
        """
        query = """
            SELECT url, title, content, published_date, source, fetched_at
            FROM articles
            WHERE embedding_status = 'pending'
            ORDER BY fetched_at ASC
        """

        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def mark_embedded(
        self,
        url: str,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Mark article as embedded (or failed).

        Args:
            url: Article URL
            success: True if embedding succeeded, False if failed
            error_message: Error message if failed
        """
        embedded_at = datetime.now(timezone.utc).isoformat()
        status = 'embedded' if success else 'failed'

        self.conn.execute("""
            UPDATE articles
            SET embedding_status = ?,
                embedded_at = ?,
                error_message = ?
            WHERE url = ?
        """, (status, embedded_at, error_message, url))
        self.conn.commit()

    def mark_embedded_batch(self, urls: List[str], success: bool = True):
        """Mark multiple articles as embedded (batch update).

        Args:
            urls: List of article URLs
            success: True if embedding succeeded
        """
        embedded_at = datetime.now(timezone.utc).isoformat()
        status = 'embedded' if success else 'failed'

        placeholders = ','.join('?' * len(urls))
        self.conn.execute(f"""
            UPDATE articles
            SET embedding_status = ?,
                embedded_at = ?
            WHERE url IN ({placeholders})
        """, [status, embedded_at] + urls)
        self.conn.commit()

    def article_exists(self, url: str) -> bool:
        """Check if article exists in cache.

        Args:
            url: Article URL

        Returns:
            True if article exists
        """
        cursor = self.conn.execute(
            "SELECT 1 FROM articles WHERE url = ? LIMIT 1",
            (url,)
        )
        return cursor.fetchone() is not None

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with total, pending, embedded, failed counts
        """
        stats = {}

        # Total articles
        cursor = self.conn.execute("SELECT COUNT(*) FROM articles")
        stats['total_articles'] = cursor.fetchone()[0]

        # By status
        cursor = self.conn.execute("""
            SELECT embedding_status, COUNT(*) as count
            FROM articles
            GROUP BY embedding_status
        """)
        stats['by_status'] = {row[0]: row[1] for row in cursor.fetchall()}

        # By source
        cursor = self.conn.execute("""
            SELECT source, COUNT(*) as count
            FROM articles
            GROUP BY source
            ORDER BY count DESC
        """)
        stats['by_source'] = [
            {"source": row[0], "count": row[1]}
            for row in cursor.fetchall()
        ]

        return stats

    def get_failed_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get articles that failed embedding.

        Args:
            limit: Maximum number to return

        Returns:
            List of failed article dicts with error messages
        """
        cursor = self.conn.execute("""
            SELECT url, title, source, error_message, embedded_at
            FROM articles
            WHERE embedding_status = 'failed'
            ORDER BY embedded_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def reset_failed_to_pending(self):
        """Reset all failed articles back to pending (for retry).

        Returns:
            Number of articles reset
        """
        cursor = self.conn.execute("""
            UPDATE articles
            SET embedding_status = 'pending',
                embedded_at = NULL,
                error_message = NULL
            WHERE embedding_status = 'failed'
        """)
        self.conn.commit()
        return cursor.rowcount

    def close(self):
        """Close database connection."""
        self.conn.close()
