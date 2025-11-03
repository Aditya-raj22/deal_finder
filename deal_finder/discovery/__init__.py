"""Discovery module."""

from .crawler import DealCrawler
from .sources import SourceRegistry

__all__ = ["DealCrawler", "SourceRegistry"]
