"""TA vocabulary bootstrapper using LLM."""

import json
import re
from pathlib import Path
from typing import Any

from .config_loader import Config, get_api_key


def validate_vocab(vocab: dict[str, Any]) -> dict[str, Any]:
    """Validate and clean generated vocabulary."""
    errors = []

    # Required fields
    required_fields = [
        "therapeutic_area",
        "includes",
        "excludes",
        "synonyms",
        "regex",
        "generated_by",
    ]
    for field in required_fields:
        if field not in vocab:
            errors.append(f"Missing required field: {field}")

    if errors:
        raise ValueError(f"Vocabulary validation failed: {', '.join(errors)}")

    # Validate includes/excludes
    includes = [term.lower().strip() for term in vocab.get("includes", [])]
    excludes = [term.lower().strip() for term in vocab.get("excludes", [])]

    # Remove duplicates
    includes = list(dict.fromkeys(includes))
    excludes = list(dict.fromkeys(excludes))

    # Check minimum token length (except biomarkers)
    def is_valid_term(term: str) -> bool:
        if len(term) >= 3:
            return True
        # Allow short biomarkers like IL-6, TNF
        if re.match(r"^[A-Z]{2,3}(-\d+)?$", term, re.IGNORECASE):
            return True
        return False

    includes = [t for t in includes if is_valid_term(t)]
    excludes = [t for t in excludes if is_valid_term(t)]

    # Remove overlaps (exclude wins)
    overlap = set(includes) & set(excludes)
    if overlap:
        includes = [t for t in includes if t not in overlap]

    # Validate regex patterns
    regex_includes = vocab.get("regex", {}).get("include_patterns", [])
    regex_excludes = vocab.get("regex", {}).get("exclude_patterns", [])

    for pattern in regex_includes + regex_excludes:
        try:
            re.compile(pattern)
        except re.error as e:
            errors.append(f"Invalid regex pattern '{pattern}': {e}")

    if errors:
        raise ValueError(f"Regex validation failed: {', '.join(errors)}")

    # Clean synonyms
    synonyms = {}
    for canonical, variants in vocab.get("synonyms", {}).items():
        canonical_clean = canonical.lower().strip()
        variants_clean = [v.strip() for v in variants if v.strip()]
        if variants_clean:
            synonyms[canonical_clean] = variants_clean

    return {
        "therapeutic_area": vocab["therapeutic_area"],
        "includes": includes,
        "excludes": excludes,
        "synonyms": synonyms,
        "regex": {"include_patterns": regex_includes, "exclude_patterns": regex_excludes},
        "generated_by": vocab["generated_by"],
    }


def generate_vocab_llm(config: Config) -> dict[str, Any]:
    """Generate vocabulary using LLM."""
    prompt_path = config.prompts_dir / "ta_bootstrapper.txt"
    with open(prompt_path, "r") as f:
        prompt_template = f.read()

    model_version = config.TA_BOOTSTRAP.MODEL.split("-")[-1]
    prompt = prompt_template.format(
        THERAPEUTIC_AREA=config.THERAPEUTIC_AREA,
        MODEL=config.TA_BOOTSTRAP.MODEL,
        VERSION=model_version,
    )

    provider = config.TA_BOOTSTRAP.LLM_PROVIDER.lower()
    api_key = get_api_key(config.TA_BOOTSTRAP.API_KEY_ENV)

    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=config.TA_BOOTSTRAP.MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text

    elif provider == "openai":
        import openai

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=config.TA_BOOTSTRAP.MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2048,
        )
        content = response.choices[0].message.content

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    # Parse JSON from response
    try:
        vocab = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            vocab = json.loads(match.group(1))
        else:
            raise ValueError(f"Failed to parse JSON from LLM response: {content[:500]}")

    return vocab


def bootstrap_ta_vocab(config: Config, overwrite: bool = False) -> dict[str, Any]:
    """Bootstrap TA vocabulary if not exists."""
    vocab_path = config.ta_vocab_path

    # Check if vocab exists and is frozen
    if vocab_path.exists() and not overwrite:
        with open(vocab_path, "r") as f:
            existing_vocab = json.load(f)
        if existing_vocab.get("generated_by", {}).get("frozen"):
            return existing_vocab

    # Generate new vocab
    if not config.TA_BOOTSTRAP.ENABLE and not vocab_path.exists():
        raise FileNotFoundError(
            f"TA vocab not found and bootstrapping is disabled: {vocab_path}"
        )

    vocab = generate_vocab_llm(config)
    vocab = validate_vocab(vocab)

    # Mark as frozen
    vocab["generated_by"]["frozen"] = True

    # Save to file
    vocab_path.parent.mkdir(parents=True, exist_ok=True)
    with open(vocab_path, "w") as f:
        json.dump(vocab, f, indent=2)

    return vocab
