"""
STEP 1: Generate Keywords with ChatGPT-5

This script generates comprehensive keyword lists and saves them to a JSON file.
You can then manually edit the file before running the main pipeline.

Usage:
    python -m deal_finder.cli.generate_keywords --config config/config.yaml

Output:
    config/generated_keywords.json - Edit this file before Step 2!
"""

import json
import logging
import os
import sys
from pathlib import Path

from ..config_loader import load_config
from ..filtering import KeywordGenerator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Generate keywords and save to file for manual editing."""
    import argparse

    parser = argparse.ArgumentParser(description="Step 1: Generate Keywords")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--output",
        default="config/generated_keywords.json",
        help="Output file for generated keywords"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("STEP 1: Generate Keywords with ChatGPT-5")
    logger.info("=" * 80)

    # Load configuration
    config = load_config(args.config)

    # Get TA and stages from config
    therapeutic_area = config.THERAPEUTIC_AREA
    stages = config.EARLY_STAGE_ALLOWED

    logger.info(f"Therapeutic Area: {therapeutic_area}")
    logger.info(f"Stages: {stages}")

    # Check API key
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        # Try loading from .env.example
        env_file = Path.cwd() / ".env.example"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENAI_API_KEY="):
                        openai_key = line.split("=", 1)[1]
                        os.environ["OPENAI_API_KEY"] = openai_key
                        break

    if not openai_key:
        logger.error("❌ OPENAI_API_KEY not set!")
        logger.error("Set it with: export OPENAI_API_KEY='sk-...'")
        return 1

    logger.info("✓ API key found")

    # Initialize keyword generator
    logger.info("\n" + "=" * 80)
    logger.info("Generating TA Keywords (5 temperatures + LLM judge)")
    logger.info("=" * 80)

    keyword_gen = KeywordGenerator(openai_key)

    # Generate TA keywords with multiple temperatures
    logger.info("Generating TA keywords at 5 different temperatures...")
    logger.info("This will take ~30-60 seconds...")

    ta_result = keyword_gen.generate_keywords_for_ta(
        therapeutic_area,
        temperatures=[0.2, 0.3, 0.5, 0.7, 0.8]
    )

    ta_keywords = ta_result["final_keywords"]
    all_candidates = ta_result["all_candidates"]

    logger.info(f"✓ Generated {len(ta_keywords)} final TA keywords")
    logger.info(f"  (from {sum(len(gen['keywords']) for gen in all_candidates)} candidates)")

    # Generate stage keywords
    logger.info("\nGenerating stage keywords...")
    stage_keywords = keyword_gen.generate_stage_keywords(stages)
    logger.info(f"✓ Generated {len(stage_keywords)} stage keywords")

    # Generate deal keywords
    logger.info("\nGenerating deal keywords...")
    deal_keywords = keyword_gen.generate_deal_keywords()
    logger.info(f"✓ Generated {len(deal_keywords)} deal keywords")

    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)

    output_data = {
        "therapeutic_area": therapeutic_area,
        "generated_at": str(Path.cwd()),
        "keywords": {
            "ta_keywords": sorted(ta_keywords),  # Sort alphabetically for easy editing
            "stage_keywords": sorted(stage_keywords),
            "deal_keywords": sorted(deal_keywords)
        },
        "generation_details": {
            "temperatures_used": [0.2, 0.3, 0.5, 0.7, 0.8],
            "total_candidates": sum(len(gen["keywords"]) for gen in all_candidates),
            "final_count": len(ta_keywords)
        },
        "all_candidates": all_candidates  # For transparency
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info("\n" + "=" * 80)
    logger.info("✅ KEYWORD GENERATION COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"\nKeywords saved to: {output_path}")
    logger.info(f"\nSummary:")
    logger.info(f"  • TA keywords: {len(ta_keywords)}")
    logger.info(f"  • Stage keywords: {len(stage_keywords)}")
    logger.info(f"  • Deal keywords: {len(deal_keywords)}")
    logger.info(f"  • Total: {len(ta_keywords) + len(stage_keywords) + len(deal_keywords)}")

    logger.info("\n" + "=" * 80)
    logger.info("📝 NEXT STEP: Edit the keywords file")
    logger.info("=" * 80)
    logger.info(f"\n1. Open: {output_path}")
    logger.info("2. Review and edit the keyword lists:")
    logger.info("   • Add missing keywords")
    logger.info("   • Remove overly generic keywords")
    logger.info("   • Adjust as needed")
    logger.info("\n3. When done, run Step 2:")
    logger.info("   python -m deal_finder.cli.run_pipeline")

    return 0


if __name__ == "__main__":
    sys.exit(main())
