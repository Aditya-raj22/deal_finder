"""CLI entry points for deal finder pipeline."""

from .generate_keywords import main as generate_keywords_main
from .run_pipeline import main as run_pipeline_main

__all__ = ["generate_keywords_main", "run_pipeline_main"]
