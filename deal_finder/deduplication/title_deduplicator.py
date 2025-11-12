"""Title-based article deduplication using embeddings."""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class TitleDeduplicator:
    """Remove duplicate articles using embeddings-based semantic similarity."""

    def __init__(self, similarity_threshold: float = 0.85):
        """Initialize title deduplicator.

        Args:
            similarity_threshold: Cosine similarity threshold for duplicates (default: 0.85)
        """
        self.similarity_threshold = similarity_threshold

    def deduplicate(self, articles: List[Dict]) -> List[Dict]:
        """
        Remove duplicate articles using embeddings-based semantic similarity.

        Strategy:
        1. Generate embeddings for article titles + first 200 chars of content
        2. Compute pairwise cosine similarity
        3. Group similar articles (>threshold similarity)
        4. Keep longest version from each group

        Args:
            articles: List of article dicts with "title" and "content" keys

        Returns:
            Deduplicated list
        """
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity

        if not articles:
            return articles

        logger.info("Loading sentence transformer model for deduplication...")
        model = SentenceTransformer('all-MiniLM-L6-v2')  # Fast, lightweight model

        # Create text to embed: title + first 200 chars of content
        texts = []
        for article in articles:
            title = article.get("title", "")
            content = article.get("content", "")[:200]
            text = f"{title} {content}"
            texts.append(text)

        logger.info(f"Generating embeddings for {len(texts)} articles...")
        embeddings = model.encode(texts, show_progress_bar=True, batch_size=256)

        logger.info("Computing similarity matrix...")
        # Compute pairwise cosine similarity
        similarity_matrix = cosine_similarity(embeddings)

        # Find duplicates (similarity > threshold)
        seen = set()
        duplicates_removed = 0
        final_articles = []

        for i in range(len(articles)):
            if i in seen:
                continue

            # Find all articles similar to this one
            similar_indices = [j for j in range(len(articles))
                              if j != i and similarity_matrix[i][j] > self.similarity_threshold]

            if similar_indices:
                # Found duplicates - keep the longest one
                group = [i] + similar_indices
                longest_idx = max(group, key=lambda idx: len(articles[idx].get("content", "")))

                # Mark others as seen
                for idx in group:
                    if idx != longest_idx:
                        seen.add(idx)
                        duplicates_removed += 1
                        logger.debug(f"Duplicate: '{articles[idx].get('title', '')[:50]}...' (similarity: {similarity_matrix[i][idx]:.2f})")

                # Add longest version if not already added
                if longest_idx not in seen:
                    final_articles.append(articles[longest_idx])
                    seen.add(longest_idx)
            else:
                # No duplicates found
                final_articles.append(articles[i])
                seen.add(i)

        logger.info(f"Embeddings deduplication: {len(articles)} → {len(final_articles)} ({duplicates_removed} removed)")
        return final_articles
