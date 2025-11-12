"""Main CLI entry point."""

import argparse
import logging
import sys
from pathlib import Path

from .config_loader import load_config
from .pipeline import DealPipeline
from .ta_bootstrapper import bootstrap_ta_vocab


def setup_logging(config):
    """Setup logging configuration."""
    log_file = config.LOG_FILE
    log_level = getattr(logging, config.LOG_LEVEL.upper())

    # Create logs directory
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Early-stage biotech deals finder")
    parser.add_argument(
        "--config", type=str, default="config/config.yaml", help="Path to config file"
    )
    parser.add_argument(
        "--overwrite-vocab",
        action="store_true",
        help="Overwrite existing TA vocabulary",
    )

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)

    logger.info("Deal Finder starting")
    logger.info(f"Therapeutic Area: {config.THERAPEUTIC_AREA}")
    logger.info(f"Date range: {config.START_DATE} to {config.end_date_resolved}")

    # Bootstrap TA vocab if needed
    try:
        ta_vocab = bootstrap_ta_vocab(config, overwrite=args.overwrite_vocab)
        logger.info(f"Loaded TA vocabulary: {ta_vocab['therapeutic_area']}")
    except Exception as e:
        logger.error(f"Failed to load/bootstrap TA vocabulary: {e}")
        sys.exit(1)

    # Run pipeline
    try:
        pipeline = DealPipeline(config)
        pipeline.run()
        logger.info("Pipeline completed successfully")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
