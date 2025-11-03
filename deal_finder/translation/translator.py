"""Multi-language translation support."""

import hashlib
import json
from pathlib import Path
from typing import Optional

from deep_translator import GoogleTranslator
from langdetect import detect


class Translator:
    """Translator with caching support."""

    def __init__(
        self,
        target_language: str = "en",
        provider: str = "google",
        cache_enabled: bool = True,
        cache_dir: str = ".cache/translations",
    ):
        self.target_language = target_language
        self.provider = provider
        self.cache_enabled = cache_enabled
        self.cache_dir = Path(cache_dir)

        if cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize translator
        if provider == "google":
            self.translator = GoogleTranslator(target=target_language)
        else:
            raise ValueError(f"Unsupported translation provider: {provider}")

    def detect_language(self, text: str) -> str:
        """Detect language of text."""
        try:
            return detect(text)
        except Exception:
            return "unknown"

    def _get_cache_key(self, text: str, source_lang: str) -> str:
        """Generate cache key for translation."""
        content = f"{source_lang}:{self.target_language}:{text}"
        return hashlib.md5(content.encode()).hexdigest()

    def _load_from_cache(self, cache_key: str) -> Optional[str]:
        """Load translation from cache."""
        if not self.cache_enabled:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            with open(cache_file, "r") as f:
                data = json.load(f)
                return data.get("translation")
        return None

    def _save_to_cache(self, cache_key: str, translation: str) -> None:
        """Save translation to cache."""
        if not self.cache_enabled:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        with open(cache_file, "w") as f:
            json.dump({"translation": translation}, f)

    def translate(self, text: str, source_lang: Optional[str] = None) -> tuple[str, str]:
        """
        Translate text to target language.

        Returns:
            Tuple of (translated_text, detected_language)
        """
        if not text or not text.strip():
            return text, "unknown"

        # Detect language if not provided
        if source_lang is None:
            source_lang = self.detect_language(text)

        # If already in target language, return as-is
        if source_lang == self.target_language:
            return text, source_lang

        # Check cache
        cache_key = self._get_cache_key(text, source_lang)
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached, source_lang

        # Translate
        try:
            if self.provider == "google":
                # Update source language for translator
                self.translator.source = source_lang
                translated = self.translator.translate(text)
            else:
                translated = text  # Fallback

            # Cache result
            self._save_to_cache(cache_key, translated)

            return translated, source_lang

        except Exception as e:
            print(f"Translation error: {e}")
            return text, source_lang  # Return original on error

    def translate_with_original(
        self, text: str, source_lang: Optional[str] = None
    ) -> tuple[str, str, str]:
        """
        Translate text and return both original and translated.

        Returns:
            Tuple of (translated_text, original_text, detected_language)
        """
        translated, lang = self.translate(text, source_lang)
        return translated, text, lang
