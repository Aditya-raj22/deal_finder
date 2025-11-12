"""
BACKWARD COMPATIBILITY WRAPPER

This is a wrapper for the refactored CLI module.
Please use: python -m deal_finder.cli.generate_keywords

This wrapper ensures old commands still work.
"""

import sys
from deal_finder.cli.generate_keywords import main

if __name__ == "__main__":
    sys.exit(main())
