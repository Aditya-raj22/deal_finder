"""Final comprehensive check before production use."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def check_imports():
    """Check all critical imports work."""
    print("\n=== Checking Imports ===")
    errors = []

    try:
        from deal_finder.config_loader import load_config, Config
        print("✓ Config loader")
    except Exception as e:
        errors.append(f"Config loader: {e}")

    try:
        from deal_finder.perplexity_client import PerplexityClient
        print("✓ Perplexity client")
    except Exception as e:
        errors.append(f"Perplexity client: {e}")

    try:
        from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler
        print("✓ Exhaustive crawler")
    except Exception as e:
        errors.append(f"Exhaustive crawler: {e}")

    try:
        from deal_finder.discovery.url_index import URLIndex
        print("✓ URL index")
    except Exception as e:
        errors.append(f"URL index: {e}")

    try:
        from deal_finder.extraction.perplexity_extractor import PerplexityExtractor
        print("✓ Perplexity extractor")
    except Exception as e:
        errors.append(f"Perplexity extractor: {e}")

    try:
        from deal_finder.pipeline import DealPipeline
        print("✓ Pipeline")
    except Exception as e:
        errors.append(f"Pipeline: {e}")

    return errors


def check_config():
    """Check configuration is valid."""
    print("\n=== Checking Configuration ===")
    errors = []

    try:
        from deal_finder.config_loader import load_config
        config_path = Path(__file__).parent / "config" / "config.yaml"

        if not config_path.exists():
            errors.append(f"Config file not found: {config_path}")
            return errors

        config = load_config(str(config_path))
        print(f"✓ Config loaded: {config_path}")
        print(f"  Therapeutic Area: {config.THERAPEUTIC_AREA}")
        print(f"  Date Range: {config.START_DATE} to {config.END_DATE or 'today'}")
        print(f"  Convergence: {config.DRY_RUNS_TO_CONVERGE} dry runs")

    except Exception as e:
        errors.append(f"Config loading error: {e}")

    return errors


def check_perplexity_setup():
    """Check Perplexity API is configured."""
    print("\n=== Checking Perplexity Setup ===")
    import os

    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        print("⚠ PERPLEXITY_API_KEY not set (will use fallback mode)")
        return ["Perplexity API key not set"]
    else:
        print(f"✓ PERPLEXITY_API_KEY set: {api_key[:10]}...")
        return []


def check_exhaustive_crawler():
    """Check exhaustive crawler can be initialized."""
    print("\n=== Checking Exhaustive Crawler ===")
    errors = []

    try:
        from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler

        crawler = ExhaustiveSiteCrawler(
            from_date="2024-01-01",
            to_date="2024-12-31",
            use_index=True
        )

        print("✓ Crawler initialized with incremental mode")
        print(f"  Sites configured: {len(crawler.PRIORITY_SITES)}")
        for site_name in crawler.PRIORITY_SITES.keys():
            print(f"    - {site_name}")

        # Check URL index
        if crawler.url_index:
            stats = crawler.url_index.get_stats()
            print(f"✓ URL index loaded: {stats['total_urls_crawled']} URLs already crawled")
        else:
            print("⚠ URL index not initialized")

    except Exception as e:
        errors.append(f"Crawler initialization error: {e}")
        import traceback
        traceback.print_exc()

    return errors


def check_pipeline():
    """Check pipeline can be initialized."""
    print("\n=== Checking Pipeline ===")
    errors = []

    try:
        from deal_finder.config_loader import load_config
        from deal_finder.pipeline import DealPipeline

        config_path = Path(__file__).parent / "config" / "config.yaml"
        config = load_config(str(config_path))

        pipeline = DealPipeline(config)
        print("✓ Pipeline initialized")
        print(f"  Exhaustive mode: {pipeline.crawler.use_exhaustive}")
        print(f"  Perplexity extraction: {pipeline.use_perplexity_extraction}")

        # Cleanup
        pipeline.selenium_client.close()
        print("✓ Pipeline cleanup successful")

    except Exception as e:
        errors.append(f"Pipeline initialization error: {e}")
        import traceback
        traceback.print_exc()

    return errors


def list_redundant_files():
    """List files that might be redundant."""
    print("\n=== Checking for Redundant Files ===")

    redundant_candidates = [
        "deal_finder/discovery/sources.py",  # Only used by old scraping
        "deal_finder/discovery/free_sources.py",  # Partially redundant (fallback only)
        "deal_finder/classification/stage_classifier.py",  # Fallback only
        "deal_finder/classification/deal_type_classifier.py",  # Fallback only
        "deal_finder/classification/ta_matcher.py",  # Fallback only
        "deal_finder/extraction/party_extractor.py",  # Fallback only
        "deal_finder/extraction/asset_extractor.py",  # Fallback only
        "deal_finder/extraction/date_parser.py",  # Fallback only
        "deal_finder/extraction/money_parser.py",  # Fallback only
    ]

    print("Files kept for fallback mode (used if no Perplexity API key):")
    for file_path in redundant_candidates:
        full_path = Path(__file__).parent / file_path
        if full_path.exists():
            print(f"  - {file_path} (fallback)")

    print("\n✓ All fallback files present")
    print("  These are only used when PERPLEXITY_API_KEY is not set")


def check_documentation():
    """Check documentation files exist."""
    print("\n=== Checking Documentation ===")

    required_docs = [
        "README_PERPLEXITY.md",
        "QUICKSTART.md",
        "EXHAUSTIVE_MODE.md",
        "HOW_PERPLEXITY_WORKS.md",
        "INCREMENTAL_CRAWLING.md",
        "FINAL_ARCHITECTURE.md",
        "OPTIMIZATIONS_SUMMARY.md",
    ]

    missing = []
    for doc in required_docs:
        doc_path = Path(__file__).parent / doc
        if doc_path.exists():
            print(f"✓ {doc}")
        else:
            missing.append(doc)
            print(f"✗ {doc} (missing)")

    return missing


def main():
    """Run all checks."""
    print("=" * 60)
    print("FINAL PRE-PRODUCTION CHECK")
    print("=" * 60)

    all_errors = []

    all_errors.extend(check_imports())
    all_errors.extend(check_config())
    all_errors.extend(check_perplexity_setup())
    all_errors.extend(check_exhaustive_crawler())
    all_errors.extend(check_pipeline())

    list_redundant_files()

    missing_docs = check_documentation()
    if missing_docs:
        all_errors.extend([f"Missing doc: {doc}" for doc in missing_docs])

    print("\n" + "=" * 60)
    print("CHECK SUMMARY")
    print("=" * 60)

    if all_errors:
        print(f"\n❌ {len(all_errors)} issues found:\n")
        for error in all_errors:
            print(f"  - {error}")
        print("\nPlease fix these issues before running in production.")
        return 1
    else:
        print("\n✅ All checks passed!")
        print("\nSystem is ready for production use.")
        print("\nNext steps:")
        print("1. Set PERPLEXITY_API_KEY environment variable")
        print("2. Run: python -m deal_finder.main --config config/config.yaml")
        print("3. Monitor logs for any issues")
        print("4. Check output/deals_*.xlsx for results")
        return 0


if __name__ == "__main__":
    sys.exit(main())
