"""Load environment variables from .env.example and run end-to-end test."""

import os
import sys
from pathlib import Path

# Load API key from .env.example
env_file = Path(__file__).parent / ".env.example"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Now import and run the test
from perplexity_end_to_end_test import perplexity_end_to_end

if __name__ == "__main__":
    sys.exit(perplexity_end_to_end())
