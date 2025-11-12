# Archived: Old Pipeline Implementation

This directory contains the original pipeline implementation that has been superseded by the refactored modular architecture.

## Contents

### Main Entry Points (Archived)
- **main.py** - Original CLI entry point using regex-based extraction
- **pipeline.py** - Original pipeline orchestrator with convergence loop
- **hybrid_pipeline.py** - Intermediate hybrid approach (keyword gen + Perplexity)

### Old Discovery
- **crawler.py** - Original crawler implementation
- **api_sources.py** - API-based source configurations
- **free_sources.py** - Free source configurations
- **sources.py** - Source registry

### Regex-Based Extractors (Archived)
**Location**: `regex_extractors/`

These were used in the fallback mode of the old pipeline:
- **asset_extractor.py** - Regex-based asset extraction
- **date_parser.py** - Regex-based date parsing
- **money_parser.py** - Regex-based money/currency extraction
- **party_extractor.py** - Regex-based party (company) extraction

### Regex-Based Classifiers (Archived)
**Location**: `classification/`

Used by the old pipeline for classification:
- **deal_type_classifier.py** - Rule-based deal type classification
- **stage_classifier.py** - Rule-based development stage classification
- **ta_matcher.py** - Therapeutic area matcher

## Why Archived?

The old pipeline used:
1. Regex-based extraction (low accuracy, brittle)
2. Manual convergence loops
3. Sequential processing
4. No LLM pre-filtering (expensive)

The new architecture uses:
1. LLM-based extraction (OpenAI/Perplexity - high accuracy)
2. Keyword pre-filtering (70% cost savings)
3. Parallel processing with checkpointing
4. Modular design with clear separation of concerns

## Migration Path

If you need to reference the old implementation:
- Old main entry: `archived_approaches/old_pipeline/main.py`
- Old pipeline class: `archived_approaches/old_pipeline/pipeline.py`
- Regex extractors: `archived_approaches/old_pipeline/regex_extractors/`

The new implementation is in:
- Entry points: `deal_finder/cli/`
- Filtering: `deal_finder/filtering/`
- Extraction: `deal_finder/extraction/` (openai_extractor.py, perplexity_extractor.py)
- Discovery: `deal_finder/discovery/exhaustive_crawler.py`
