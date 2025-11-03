"""Test Perplexity integration end-to-end."""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def test_perplexity_client():
    """Test Perplexity client initialization and search."""
    print("\n=== Testing Perplexity Client ===")

    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        print("❌ PERPLEXITY_API_KEY not set")
        print("   Run: export PERPLEXITY_API_KEY='pplx-...'")
        return False

    print("✓ API key found")

    try:
        from deal_finder.perplexity_client import PerplexityClient
        client = PerplexityClient(api_key)
        print("✓ Client initialized")

        # Test search
        print("\n  Testing search for oncology deals...")
        results = client.search_deals(
            query="oncology acquisition",
            from_date="2024-01-01",
            to_date="2024-12-31",
            max_results=5
        )

        print(f"✓ Search returned {len(results)} results")
        if results:
            print(f"  Sample: {results[0].get('title', 'N/A')[:80]}...")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_perplexity_extraction():
    """Test Perplexity extraction."""
    print("\n=== Testing Perplexity Extraction ===")

    try:
        from deal_finder.extraction.perplexity_extractor import PerplexityExtractor

        extractor = PerplexityExtractor(batch_size=2)
        print("✓ Extractor initialized")

        # Test with mock article
        sample_article = {
            "url": "https://example.com/deal",
            "title": "Pfizer Acquires Arena Pharmaceuticals",
            "content": """
            Pfizer Inc. announced today that it has completed the acquisition of
            Arena Pharmaceuticals for $6.7 billion. The deal includes Arena's
            portfolio of inflammatory disease assets, including etrasimod,
            currently in Phase 3 trials for ulcerative colitis.
            """
        }

        ta_vocab = {
            "therapeutic_area": "immunology",
            "includes": ["inflammatory", "autoimmune", "colitis"],
            "excludes": ["oncology"]
        }

        print("  Testing batch extraction...")
        results = extractor.extract_batch([sample_article], ta_vocab)

        if results and results[0]:
            print("✓ Extraction successful")
            print(f"  Acquirer: {results[0].get('parties', {}).get('acquirer', 'N/A')}")
            print(f"  Target: {results[0].get('parties', {}).get('target', 'N/A')}")
            print(f"  Deal type: {results[0].get('deal_type', 'N/A')}")
        else:
            print("⚠ Extraction returned no results")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_integration():
    """Test full pipeline integration."""
    print("\n=== Testing Pipeline Integration ===")

    try:
        from deal_finder.config_loader import load_config
        from deal_finder.pipeline import DealPipeline

        config_path = Path(__file__).parent / "config" / "config.yaml"
        if not config_path.exists():
            print(f"❌ Config not found: {config_path}")
            return False

        print(f"✓ Loading config from {config_path}")
        config = load_config(str(config_path))

        print("  Initializing pipeline...")
        pipeline = DealPipeline(config)

        if pipeline.use_perplexity_extraction:
            print("✓ Pipeline configured to use Perplexity extraction")
        else:
            print("⚠ Pipeline using fallback (regex) extraction")

        if hasattr(pipeline.crawler, 'use_perplexity') and pipeline.crawler.use_perplexity:
            print("✓ Crawler configured to use Perplexity discovery")
        else:
            print("⚠ Crawler using fallback (RSS) discovery")

        print("\n✓ Pipeline integration successful!")
        print("\nTo run full pipeline:")
        print("  python -m deal_finder.main --config config/config.yaml")

        # Cleanup
        pipeline.selenium_client.close()

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Perplexity Integration Test Suite")
    print("=" * 60)

    results = []

    results.append(("Perplexity Client", test_perplexity_client()))
    results.append(("Perplexity Extraction", test_perplexity_extraction()))
    results.append(("Pipeline Integration", test_pipeline_integration()))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("\n✓ All tests passed!")
        print("\nNext steps:")
        print("1. Set PERPLEXITY_API_KEY environment variable")
        print("2. Run: python -m deal_finder.main --config config/config.yaml")
        return 0
    else:
        print("\n❌ Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
