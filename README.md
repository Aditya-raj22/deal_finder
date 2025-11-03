# Deal Finder - Early-Stage Biotech Deals Pipeline

**Automated pipeline for discovering and extracting early-stage biotech/pharma deals using Perplexity AI.**

Compiles a complete, deduplicated dataset of M&A, partnerships, licensing, and option deals from 2021-present across parameterized Therapeutic Areas.

---

## 🚀 Quick Start (5 Minutes)

### 1. Set API Key
```bash
export PERPLEXITY_API_KEY="pplx-your-key-here"
```

### 2. Run Test
```bash
python perplexity_end_to_end_test.py
```

### 3. Check Results
```bash
open output/perplexity_e2e_*.xlsx
```

**Expected**: 2-5 deals in < 2 minutes, saved to Excel.

**For detailed setup and testing options, see [START_HERE.md](START_HERE.md)**

---

## 📖 Documentation

- **[START_HERE.md](START_HERE.md)** - Quick start guide and testing
- **[CURRENT_STATUS.md](CURRENT_STATUS.md)** - Current state, next steps, troubleshooting
- **[TEST_OPTIONS.md](TEST_OPTIONS.md)** - All testing strategies
- **[FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md)** - Complete system design

---

## What This Pipeline Does

A deterministic, test-covered pipeline for compiling a complete, deduplicated dataset of global early-stage life sciences deals (M&A, partnership, licensing, option-to-license) announced on/after 2021-01-01 for parameterized Therapeutic Areas.

## Features

- **Multi-language support**: Discovers and translates press releases in any language
- **Comprehensive classification**: Stage (preclinical, Phase 1, FIH), therapeutic area, and deal type
- **Smart extraction**: Monetary amounts, dates, parties, and asset focus with evidence tracking
- **FX conversion**: Automatic currency conversion using ECB rates with fallbacks
- **Deduplication**: Hash-based deduplication with fuzzy matching within date windows
- **Convergence-based discovery**: Iterates until no new qualifying deals are found
- **Evidence logging**: Complete audit trail with original snippets and sources
- **Deterministic output**: Guaranteed idempotent results for reproducibility
- **False negative prevention**: Includes ambiguous matches flagged for review rather than excluding them

## False Negative Prevention Strategy

The pipeline is designed to **never miss a potential deal** - it's better to have false positives (flagged for manual review) than false negatives (missed deals).

**Ambiguous items are included with `Needs Review = TRUE`:**
- **Stage unclear?** → Defaults to "preclinical" + needs review
- **TA match uncertain?** → Included + needs review
- **Deal type ambiguous?** → Defaults to "Partnership" + needs review
- **Monetary amounts with "up to" or ranges?** → Flagged for review

**Only hard exclusions:**
- Confirmed Phase 2+ (explicitly excluded per spec)
- Confirmed non-TA after applying exclude rules (e.g., cancer when searching I&I)
- Missing required fields (date, URL)

**Result**: You review more deals, but you don't miss any potential matches.

## Installation

### Prerequisites

- Python 3.10+
- API key for LLM provider (Anthropic or OpenAI) if using TA vocab bootstrapping

### Setup

```bash
# Clone or navigate to the repository
cd deal_finder

# Install dependencies
pip install -e ".[dev,llm]"

# Or use make
make install
```

### Environment Variables

For TA vocabulary bootstrapping, set your API key:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
# OR
export OPENAI_API_KEY="your-api-key-here"
```

## Configuration

Edit `config/config.yaml` to customize:

```yaml
THERAPEUTIC_AREA: "immunology_inflammation"  # Required
START_DATE: "2021-01-01"
END_DATE: null  # null = runtime UTC date
DRY_RUNS_TO_CONVERGE: 5
CURRENCY_BASE: "USD"
REQUEST_RATE_LIMIT_PER_DOMAIN_PER_MIN: 15
# ... see config.yaml for full options
```

### Therapeutic Area Vocabulary

TA vocabularies define:
- **includes**: Terms/conditions in the therapeutic area
- **excludes**: Terms from other areas (excludes override includes)
- **synonyms**: Canonical mappings (e.g., "RA" → "rheumatoid arthritis")
- **regex**: Patterns for flexible matching

Pre-configured vocabularies:
- `config/ta_vocab/immunology_inflammation.json`
- `config/ta_vocab/neurology.json`

#### Bootstrapping New TA Vocabularies

To generate a new TA vocabulary using LLM:

1. Set `THERAPEUTIC_AREA` in config
2. Enable bootstrapping: `TA_BOOTSTRAP.ENABLE: true`
3. Run with `--overwrite-vocab` flag:

```bash
python -m deal_finder.main --config config/config.yaml --overwrite-vocab
```

The generated vocabulary will be frozen and saved to `config/ta_vocab/<TA>.json`.

### Company Aliases

Edit `config/aliases.json` to add company name canonicalization rules:

```json
{
  "company_aliases": {
    "pfizer": ["pfizer inc", "pfizer incorporated"],
    "johnson & johnson": ["j&j", "jnj"]
  },
  "legal_suffixes_to_strip": ["inc", "ltd", "llc", ...]
}
```

## Usage

### Basic Run

```bash
python -m deal_finder.main --config config/config.yaml
```

Or use make:

```bash
make run
```

### Command-Line Options

```bash
python -m deal_finder.main --help

Options:
  --config PATH            Path to config file (default: config/config.yaml)
  --overwrite-vocab        Overwrite existing TA vocabulary with LLM-generated one
```

## Output

The pipeline generates two files in the `OUTPUT_DIR` (default: `output/`):

### 1. Excel File (`deals.xlsx`)

Fixed schema with 15 columns:

| Column | Type | Description |
|--------|------|-------------|
| Date Announced | date | YYYY-MM-DD (UTC) |
| Target / Partner | string | Canonical company name |
| Acquirer / Partner | string | Canonical company name |
| Upfront Value (M USD) | decimal | Blank if unknown |
| Contingent Payment (M USD) | decimal | Blank if unknown |
| Total Deal Value (M USD) | decimal | Blank if unknown |
| Upfront as % of Total Value | decimal | 0.1% precision |
| Phase of Lead Asset at Announcement | enum | {preclinical, phase 1, first-in-human} |
| Therapeutic Area | string | Primary TA |
| Secondary Areas | string | Semicolon-separated |
| Asset / Focus | string | Asset description |
| Deal Type (M&A or Partnership) | enum | {"M&A", "Partnership"} |
| Geography of Target | string | ISO-3166 country name |
| Source URL | URL | Primary source |
| Needs Review | boolean | TRUE/FALSE |

**Note**: Licensing and Option-to-License deals are mapped to "Partnership" in the output.

### 2. Evidence Log (`evidence.jsonl`)

JSONL file with complete evidence for each deal:

```json
{
  "canonical_key": "hash...",
  "source_url": "https://...",
  "related_urls": ["https://..."],
  "evidence": {
    "date_announced": {
      "snippet_en": "...",
      "snippet_original": "...",
      "raw_phrase": "June 15, 2023"
    },
    ...
  },
  "detected_currency": "EUR",
  "fx_rate": 1.0952,
  "fx_source": "ECB",
  "confidence": 0.95,
  "inclusion_reason": "...",
  "parser_version": "1.0.0",
  "timestamp_utc": "2023-08-01T12:00:00Z"
}
```

## Testing

Run all tests:

```bash
make test
# Or
pytest
```

Tests cover:
- **Unit tests**: Stage classifier, TA matcher, money parser, FX converter, canonicalizer, deduplicator
- **Integration tests**: End-to-end pipeline, Excel writer, evidence logger
- **Contract tests**: Excel schema, data types, boolean formatting
- **Determinism tests**: Idempotency, frozen dates, reproducibility

## Architecture

```
deal_finder/
├── classification/      # Stage, TA, and deal type classifiers
├── extraction/          # Money, date, party, and asset extractors
├── normalization/       # FX converter, company canonicalizer, geography resolver
├── deduplication/       # Hash-based deduplicator with fuzzy matching
├── discovery/           # Web crawler and source registry
├── translation/         # Multi-language translator with caching
├── output/              # Excel writer and evidence logger
├── utils/               # Web client (rate limiting, robots.txt) and text utilities
├── config_loader.py     # Configuration management
├── ta_bootstrapper.py   # LLM-based TA vocabulary generator
├── pipeline.py          # Main orchestrator
└── main.py              # CLI entry point
```

## Pipeline Flow

1. **Bootstrap**: Load/generate TA vocabulary
2. **Discovery**: Crawl news sources with TA-specific queries
3. **Translation**: Detect language and translate to English
4. **Classification**: Identify stage, TA, and deal type
5. **Extraction**: Parse dates, parties, amounts, and asset focus
6. **Normalization**: Canonicalize companies, convert currencies, resolve geography
7. **Deduplication**: Generate canonical keys and merge duplicates
8. **Convergence**: Iterate until K consecutive dry runs (no new deals)
9. **Output**: Write Excel and evidence log

## Compliance & Best Practices

- ✅ Respects `robots.txt`
- ✅ Per-domain rate limiting (configurable, default: 15 req/min)
- ✅ Exponential backoff with retries
- ✅ No paywall bypass
- ✅ Does not hallucinate data (all fields have evidence)
- ✅ Deterministic and reproducible
- ✅ Complete audit trail

## Quality Gates

The pipeline will fail if:
- Missing `Source URL`
- Invalid/empty `Date Announced`
- Stage not in allowed set
- TA mismatch after vocab rules
- Excel column order/types mismatch

## Troubleshooting

### No deals found

- Check that TA vocabulary matches your target area
- Verify discovery sources are accessible
- Review logs in `logs/deal_finder.log`
- Try increasing `REQUEST_RATE_LIMIT_PER_DOMAIN_PER_MIN`

### Translation errors

- Ensure internet connectivity
- Check translation cache: `.cache/translations/`
- Try alternative MT provider in config

### FX conversion failures

- Check date is not too far in past/future
- Verify currency code is valid
- Review `fx_source` in evidence log for fallback usage

## Development

### Code Quality

```bash
# Format code
make format

# Lint
make lint
```

### Adding New Sources

Edit `deal_finder/discovery/sources.py`:

```python
sources.append(
    Source(
        name="Your Source",
        base_url="https://example.com",
        source_type="newswire",  # or "trade_press", "IR"
        search_template="https://example.com/search?q={query}&page={page}",
    )
)
```

## License

MIT License - see LICENSE file

## Citation

If you use this pipeline in research, please cite:

```
Deal Finder (2025). Early-Stage Biotech Deals Pipeline.
https://github.com/yourusername/deal_finder
```

## Support

For issues and questions:
- File an issue on GitHub
- Check logs in `logs/deal_finder.log`
- Review evidence log for extraction details

## Acknowledgments

Built with:
- BeautifulSoup4 for HTML parsing
- openpyxl for Excel writing
- deep-translator for multi-language support
- forex-python for FX rates
- pydantic for data validation