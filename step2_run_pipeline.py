"""
BACKWARD COMPATIBILITY WRAPPER

This is a wrapper for the refactored CLI module.
Please use: python -m deal_finder.cli.run_pipeline

This wrapper ensures old commands still work.
"""

import sys
from deal_finder.cli.run_pipeline import main

if __name__ == "__main__":
    sys.exit(main())
