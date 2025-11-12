"""Deduplication module."""

from .deduplicator import Deduplicator
from .title_deduplicator import TitleDeduplicator
from .deal_deduplicator import DealDeduplicator

__all__ = ["Deduplicator", "TitleDeduplicator", "DealDeduplicator"]
