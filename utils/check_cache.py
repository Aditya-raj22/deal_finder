"""Check ChromaDB cache statistics."""

from deal_finder.storage.article_cache_chroma import ChromaArticleCache

def main():
    cache = ChromaArticleCache()
    stats = cache.get_stats()

    print("=" * 60)
    print("CHROMADB CACHE STATISTICS")
    print("=" * 60)
    print(f"\nTotal articles: {stats['total_articles']:,}")
    print(f"Embedding model: {stats['embedding_model']}")
    print(f"Collection: {stats['collection_name']}")

    print(f"\nBy source:")
    for source_info in stats['by_source']:
        print(f"  {source_info['source']:<25} {source_info['count']:>6,} articles")

    print("")

if __name__ == "__main__":
    main()
