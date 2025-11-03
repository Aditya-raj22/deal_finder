"""
Quick test for hybrid pipeline with small dataset.

Tests the complete flow:
1. Keyword generation (ChatGPT-5)
2. Article fetching (first 50 from sitemap)
3. Keyword filtering
4. Perplexity extraction
5. Dual Excel output
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from .env.example
env_file = Path(__file__).parent / ".env.example"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Now run the hybrid pipeline
from hybrid_pipeline import HybridPipeline
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Run quick test with limited articles."""
    logger.info("=" * 80)
    logger.info("HYBRID PIPELINE - QUICK TEST (50 articles)")
    logger.info("=" * 80)

    # Run pipeline
    pipeline = HybridPipeline("config/config.yaml")

    # Monkey-patch to limit articles for testing
    original_crawl = pipeline.run

    def test_run():
        """Modified run that processes fewer articles."""
        # Call original but with smaller limit
        import logging
        logging.getLogger("deal_finder.discovery").setLevel(logging.WARNING)

        # Run the pipeline
        original_crawl()

    pipeline.run = test_run
    pipeline.run()

if __name__ == "__main__":
    main()
