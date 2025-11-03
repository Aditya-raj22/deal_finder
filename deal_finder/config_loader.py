"""Configuration loader."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class LanguagePolicy(BaseModel):
    """Language processing policy."""

    DISCOVERY_LANGUAGES: list[str] = Field(default=["*"])
    EXTRACTION_LANGUAGE: str = Field(default="en")
    MT_PROVIDER: str = Field(default="google")
    CACHE_TRANSLATIONS: bool = Field(default=True)


class TABootstrap(BaseModel):
    """TA vocabulary bootstrapper config."""

    ENABLE: bool = Field(default=True)
    LLM_PROVIDER: str = Field(default="anthropic")
    MODEL: str = Field(default="claude-3-5-sonnet-20241022")
    API_KEY_ENV: str = Field(default="ANTHROPIC_API_KEY")


class Config(BaseModel):
    """Application configuration."""

    THERAPEUTIC_AREA: str
    START_DATE: str = Field(default="2021-01-01")
    END_DATE: Optional[str] = None
    EARLY_STAGE_ALLOWED: list[str] = Field(
        default=["preclinical", "phase 1", "phase I", "first-in-human", "FIH"]
    )
    DEAL_TYPES_ALLOWED: list[str] = Field(
        default=["M&A", "partnership", "licensing", "option-to-license"]
    )
    DRY_RUNS_TO_CONVERGE: int = Field(default=5)
    CURRENCY_BASE: str = Field(default="USD")
    FX_PROVIDER: str = Field(default="ECB")
    FX_FALLBACK_PROVIDER: str = Field(default="OpenExchangeRates")
    LANGUAGE_POLICY: LanguagePolicy = Field(default_factory=LanguagePolicy)
    TA_BOOTSTRAP: TABootstrap = Field(default_factory=TABootstrap)
    REQUEST_RATE_LIMIT_PER_DOMAIN_PER_MIN: int = Field(default=15)
    USER_AGENT: str = Field(default="DealsCrawler/1.0 (Research; +https://example.com/bot)")
    TIMEOUT_SECONDS: int = Field(default=20)
    MAX_RETRIES: int = Field(default=3)
    BACKOFF_FACTOR: int = Field(default=2)
    EXISTING_DATASET_PATH: Optional[str] = None
    OUTPUT_DIR: str = Field(default="output")
    EVIDENCE_LOG_FORMAT: str = Field(default="jsonl")
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default="logs/deal_finder.log")

    @property
    def end_date_resolved(self) -> str:
        """Resolve END_DATE to runtime UTC date if None."""
        if self.END_DATE:
            return self.END_DATE
        return datetime.utcnow().date().isoformat()

    @property
    def config_dir(self) -> Path:
        """Return config directory path."""
        return Path(__file__).parent.parent / "config"

    @property
    def ta_vocab_path(self) -> Path:
        """Return path to TA vocab file."""
        return self.config_dir / "ta_vocab" / f"{self.THERAPEUTIC_AREA}.json"

    @property
    def aliases_path(self) -> Path:
        """Return path to aliases file."""
        return self.config_dir / "aliases.json"

    @property
    def prompts_dir(self) -> Path:
        """Return prompts directory path."""
        return self.config_dir / "prompts"


def load_config(config_path: str) -> Config:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
    return Config(**data)


def load_ta_vocab(config: Config) -> dict[str, Any]:
    """Load TA vocabulary."""
    vocab_path = config.ta_vocab_path
    if not vocab_path.exists():
        raise FileNotFoundError(f"TA vocabulary not found: {vocab_path}")

    with open(vocab_path, "r") as f:
        vocab = json.load(f)

    # Validate frozen status
    if vocab.get("generated_by", {}).get("frozen"):
        # Vocab is frozen, cannot be regenerated
        pass

    return vocab


def load_aliases(config: Config) -> dict[str, Any]:
    """Load company aliases."""
    aliases_path = config.aliases_path
    if not aliases_path.exists():
        return {"company_aliases": {}, "legal_suffixes_to_strip": []}

    with open(aliases_path, "r") as f:
        return json.load(f)


def get_api_key(env_var: str) -> str:
    """Get API key from environment."""
    api_key = os.getenv(env_var)
    if not api_key:
        raise ValueError(f"API key not found in environment variable: {env_var}")
    return api_key
