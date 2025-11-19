"""ChromaDB-based semantic search (10-100x faster than SQLite).

Same accuracy as SQLite semantic search, but much faster for large datasets.
Uses HNSW index for approximate nearest neighbor search.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class ChromaArticleCache:
    """Article cache using ChromaDB for fast semantic search.

    Benefits over SQLite:
    - 10-100x faster similarity search (HNSW index)
    - Automatic embedding management
    - Built-in filtering by metadata
    - Scales to millions of articles

    Same accuracy as SQLite semantic search.
    """

    def __init__(
        self,
        db_path: str = "output/chroma_db",
        collection_name: str = "articles",
        embedding_model: str = "all-MiniLM-L6-v2"
    ):
        """Initialize ChromaDB cache.

        Args:
            db_path: Path to ChromaDB persistent storage
            collection_name: Collection name (like a SQL table)
            embedding_model: sentence-transformers model name
                Options:
                - 'all-MiniLM-L6-v2' (default) - Fast, good accuracy (384 dim)
                - 'all-mpnet-base-v2' - Slower, better accuracy (768 dim)
                - 'allenai/specter' - Best for scientific papers (768 dim)
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client (persistent storage)
        logger.info(f"Initializing ChromaDB at {db_path}")
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False
            )
        )

        # Load embedding model
        logger.info(f"Loading embedding model: {embedding_model}")
        self.model = SentenceTransformer(embedding_model)
        self.embedding_function = chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )

        # Get or create collection
        try:
            self.collection = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            logger.info(f"Loaded existing collection: {collection_name}")
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}  # Use cosine similarity
            )
            logger.info(f"Created new collection: {collection_name}")

    def upsert_article(
        self,
        url: str,
        title: str,
        content: str,
        published_date: str,
        source: str,
        lastmod: Optional[str] = None
    ) -> bool:
        """Insert or update article.

        Args:
            url: Article URL (used as ID)
            title: Article title
            content: Article content (first 2500 chars)
            published_date: Publication date (YYYY-MM-DD)
            source: Source name
            lastmod: Last modified date (optional)

        Returns:
            True if successful
        """
        content_snippet = content[:2500] if content else ""
        fetched_at = datetime.now(timezone.utc).isoformat()

        # ChromaDB will automatically compute embedding from document
        self.collection.upsert(
            ids=[url],
            documents=[f"{title} {content_snippet}"],
            metadatas=[{
                "title": title,
                "published_date": published_date,
                "source": source,
                "fetched_at": fetched_at,
                "lastmod": lastmod or "",
                "content_length": len(content_snippet)
            }]
        )

        return True

    def upsert_batch(
        self,
        articles: List[Dict[str, Any]],
        batch_size: int = 100
    ):
        """Batch insert articles (much faster than one-by-one).

        Args:
            articles: List of article dicts with keys: url, title, content, published_date, source
            batch_size: Batch size for ChromaDB insert (default 100)
        """
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]

            ids = []
            documents = []
            metadatas = []

            for article in batch:
                content_snippet = article.get('content', '')[:2500]
                ids.append(article['url'])
                documents.append(f"{article.get('title', '')} {content_snippet}")
                metadatas.append({
                    "title": article.get('title', ''),
                    "published_date": article.get('published_date', ''),
                    "source": article.get('source', 'Unknown'),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "lastmod": article.get('lastmod', ''),
                    "content_length": len(content_snippet)
                })

            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )

            if i % 1000 == 0:
                logger.info(f"Upserted {i}/{len(articles)} articles")

    def search_articles_semantic(
        self,
        query: str,
        start_date: str = "2021-01-01",
        end_date: Optional[str] = None,
        sources: Optional[List[str]] = None,
        top_k: int = 500,
        similarity_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Search articles using semantic similarity.

        Args:
            query: Natural language query
            start_date: Start date filter (YYYY-MM-DD)
            end_date: End date filter (YYYY-MM-DD)
            sources: Filter by sources
            top_k: Maximum results
            similarity_threshold: Minimum similarity (0-1), None = return all top_k

        Returns:
            List of articles with similarity scores
        """
        if not end_date:
            end_date = datetime.now(timezone.utc).date().isoformat()

        # Build metadata filter (ChromaDB where clause)
        # Note: ChromaDB can't do $gte/$lte on string dates, so we only filter by source
        where_filter = None
        if sources:
            where_filter = {"source": {"$in": sources}}

        # Query ChromaDB (get more results since we'll filter dates post-query)
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k * 2,  # Get 2x results to account for date filtering
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )

        # Convert to standard format and filter by date
        articles = []
        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i]
                published_date = metadata.get('published_date', '')

                # Filter by date (string comparison works for YYYY-MM-DD format)
                if published_date < start_date or published_date > end_date:
                    continue

                # ChromaDB returns distance (lower = more similar)
                # Convert to similarity (higher = more similar)
                distance = results['distances'][0][i]
                similarity = 1 - distance  # Cosine distance -> similarity

                # Apply threshold if specified
                if similarity_threshold and similarity < similarity_threshold:
                    continue

                articles.append({
                    'url': results['ids'][0][i],
                    'title': metadata['title'],
                    'content_snippet': results['documents'][0][i].split(' ', 1)[1] if ' ' in results['documents'][0][i] else '',
                    'published_date': published_date,
                    'source': metadata['source'],
                    'similarity': float(similarity),
                    'distance': float(distance)
                })

                # Stop once we have enough results
                if len(articles) >= top_k:
                    break

        return articles

    def article_exists(self, url: str) -> bool:
        """Check if article exists.

        Note: ChromaDB doesn't track lastmod, so we just check existence.
        For incremental updates, use external tracking (e.g., crawl_metadata table).
        """
        try:
            result = self.collection.get(ids=[url])
            return len(result['ids']) > 0
        except:
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_articles = self.collection.count()

        # Get sample of articles to compute stats by source
        sample = self.collection.get(limit=10000, include=["metadatas"])

        sources = {}
        if sample['metadatas']:
            for metadata in sample['metadatas']:
                source = metadata.get('source', 'Unknown')
                if source not in sources:
                    sources[source] = 0
                sources[source] += 1

        by_source = [
            {"source": source, "count": count}
            for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "total_articles": total_articles,
            "by_source": by_source,
            "embedding_model": getattr(self.embedding_function, '_model_name', getattr(self.embedding_function, 'model_name', 'unknown')),
            "collection_name": self.collection.name
        }

    def delete_all(self):
        """Delete all articles (use with caution!)."""
        logger.warning("Deleting all articles from ChromaDB")
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.create_collection(
            name=self.collection.name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}
        )


def migrate_from_sqlite_to_chroma(
    sqlite_db_path: str = "output/article_cache_semantic.db",
    chroma_db_path: str = "output/chroma_db"
):
    """Migrate existing SQLite semantic cache to ChromaDB.

    Args:
        sqlite_db_path: Path to SQLite database
        chroma_db_path: Path to ChromaDB storage
    """
    import sqlite3

    logger.info(f"Migrating from SQLite to ChromaDB...")

    # Read from SQLite
    conn = sqlite3.connect(sqlite_db_path)
    cursor = conn.execute("""
        SELECT url, title, content_snippet, published_date, source, lastmod
        FROM articles
        WHERE embedding IS NOT NULL
    """)

    articles = []
    for row in cursor.fetchall():
        articles.append({
            'url': row[0],
            'title': row[1],
            'content': row[2],
            'published_date': row[3],
            'source': row[4],
            'lastmod': row[5]
        })

    conn.close()
    logger.info(f"Loaded {len(articles)} articles from SQLite")

    # Write to ChromaDB
    cache = ChromaArticleCache(db_path=chroma_db_path)
    cache.upsert_batch(articles, batch_size=100)

    logger.info(f"✓ Migrated {len(articles)} articles to ChromaDB")

    return cache
