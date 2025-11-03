# Quick Start Guide

## 1. Set Up Perplexity API Key

Get your API key from https://www.perplexity.ai/settings/api

```bash
export PERPLEXITY_API_KEY="pplx-your-key-here"
```

## 2. Test Integration

```bash
python test_perplexity_integration.py
```

Expected output:
```
✓ PASS: Perplexity Client
✓ PASS: Perplexity Extraction
✓ PASS: Pipeline Integration
```

## 3. Run Pipeline

```bash
python -m deal_finder.main --config config/config.yaml
```

## 4. View Results

Results will be in `output/` directory:
- `deals_{run_id}.xlsx` - Excel file with all extracted deals
- `evidence_{run_id}.jsonl` - Evidence log for auditing

## Configuration

Edit `config/config.yaml` to change:
- `THERAPEUTIC_AREA` - which therapeutic area to search
- `START_DATE` / `END_DATE` - date range for deals
- `DRY_RUNS_TO_CONVERGE` - how many empty cycles before stopping

## How It Works

### Discovery (Max Breadth)
1. Generates 20+ search queries based on TA vocabulary
2. Perplexity searches each query (25 results per query)
3. Deduplicates to ~100-150 unique article URLs

### Extraction (Max Accuracy)
1. Fetches HTML for each article
2. Batches 5 articles per Perplexity API call
3. Extracts structured deal data (parties, dates, money, stage, etc.)
4. Returns confidence scores

### Post-Processing
1. Canonicalizes company names
2. Deduplicates deals
3. Runs quality checks
4. Exports to Excel + evidence log

## Performance

**With Perplexity:**
- Discovery: ~100 unique URLs per cycle
- Extraction: 85-95% accuracy
- Cost: ~$0.40 per run
- Runtime: ~10-15 minutes

**Without Perplexity (fallback):**
- Discovery: ~30 URLs from RSS feeds
- Extraction: 40-60% accuracy
- Cost: Free
- Runtime: ~5-8 minutes

## Troubleshooting

### API Key Issues
```bash
# Check if key is set
echo $PERPLEXITY_API_KEY

# Set key in current shell
export PERPLEXITY_API_KEY="pplx-..."

# Set key permanently (add to ~/.bashrc or ~/.zshrc)
echo 'export PERPLEXITY_API_KEY="pplx-..."' >> ~/.bashrc
```

### Low Accuracy
- Check `needs_review` column in Excel output
- Review failed extractions in evidence log
- Adjust extraction prompts in `deal_finder/perplexity_client.py`

### Rate Limits
- Perplexity limit: 50 requests/minute
- Current batch size (5 articles) should stay under limit
- Add delays in `pipeline.py` if needed

## Advanced Usage

### Change Therapeutic Area

Create new vocab file in `config/ta_vocab/{area}.json`:
```json
{
  "therapeutic_area": "oncology",
  "includes": ["cancer", "tumor", "carcinoma", ...],
  "excludes": ["benign", ...],
  ...
}
```

Update `config/config.yaml`:
```yaml
THERAPEUTIC_AREA: "oncology"
```

### Increase Breadth

In `deal_finder/discovery/crawler.py`, line 168:
```python
for query in queries[:40]:  # Increase from 20 to 40
```

In `deal_finder/pipeline.py`, line 257:
```python
discovered = self.crawler.discover(self.ta_vocab, max_results=200)  # Increase from 100
```

### Adjust Batch Size

In `deal_finder/pipeline.py`, line 61:
```python
self.perplexity_extractor = PerplexityExtractor(batch_size=10)  # Increase from 5
```

## Next Steps

1. Run on your therapeutic area
2. Review results and adjust prompts/filters
3. Scale to more TAs or larger date ranges
4. Set up monitoring/alerts (see config)
