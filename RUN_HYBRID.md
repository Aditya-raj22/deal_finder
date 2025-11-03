# How to Run the Hybrid Pipeline

## Quick Start (5 Minutes)

### 1. Set Environment Variables

```bash
# Required: ChatGPT-5 for keyword generation
export OPENAI_API_KEY="sk-..."

# Required: Perplexity for extraction
export PERPLEXITY_API_KEY="pplx-..."
```

Or keys are already in `.env.example` and will be loaded automatically!

### 2. Run Quick Test

```bash
python test_hybrid.py
```

**What it does**:
- Tests complete pipeline with first 50 articles
- Takes ~5 minutes
- Costs ~$0.50-1.00
- Outputs 1-3 deals (if any in first 50 articles)

### 3. Check Results

Two Excel files will be created in `output/`:

1. **`hybrid_deals_*.xlsx`** - Extracted deals (your main output)
2. **`hybrid_rejected_*.xlsx`** - URLs that passed keywords but rejected by Perplexity

### 4. Run Full Pipeline

```bash
python hybrid_pipeline.py --config config/config.yaml
```

**What it does**:
- Processes ALL ~1,000 articles from FierceBiotech (2021-2025)
- Takes ~40 minutes
- Costs ~$4-5
- Outputs ~10-20 deals

---

## Complete Flow Summary

```
1. Generate Keywords (ChatGPT-5)
   → 5 temps → LLM judge → Final list

2. Crawl Sitemap (FierceBiotech)
   → ~1,000 article URLs

3. Fetch Content (Selenium)
   → Full HTML → Extract text

4. Keyword Filter ⭐
   → Keep only articles with TA + stage + deal keywords
   → Reduces 1,000 → 250 articles (75% cost savings!)

5. Perplexity Extract
   → Only 250 articles sent (not 1,000!)
   → Extract parties, money, stage, date

6. Dual Excel Output
   → Deals (extracted)
   → Rejected (passed keywords but not Perplexity)
```

---

## What You'll Get

### Excel 1: Extracted Deals

Full deal data:
- Parties (acquirer + target)
- Money (upfront, total deal value)
- Stage (preclinical, phase 1)
- Therapeutic area
- Date announced
- Source URL (clickable)
- Evidence snippets

**Expected**: 10-20 deals from 1,000 articles

### Excel 2: Rejected URLs

URLs that passed keyword filter but Perplexity rejected:
- Article URL
- Which keywords matched (TA, stage, deal)
- Why Perplexity rejected it

**Use case**: "Just in case" - manually review if you think Perplexity missed something

---

## Cost Breakdown

| Step | Cost |
|------|------|
| Keyword generation (one-time) | $0.50 |
| Sitemap crawl | $0 |
| Fetch articles | $0 |
| Keyword filter | $0 |
| Perplexity extraction (250 articles) | $3.50 |
| **Total first run** | **$4.00** |
| **Subsequent runs** | **$3.50** |

**vs $14-15 without keyword filter (70% savings!)**

---

## Troubleshooting

### "OPENAI_API_KEY not set"
```bash
export OPENAI_API_KEY="sk-..."
```

### "PERPLEXITY_API_KEY not set"
```bash
export PERPLEXITY_API_KEY="pplx-..."
```

### "No deals found"
- Check `hybrid_rejected_*.xlsx` to see what was filtered out
- May need to adjust TA keywords or filters
- Try running `test_hybrid.py` first to validate

### "Too expensive"
- Keyword filter should reduce to ~250 articles
- If more articles passing → Check keywords aren't too broad
- Cost should be ~$4-5 per full run

---

## Configuration

Edit `config/config.yaml` to change:

```yaml
# Therapeutic area
THERAPEUTIC_AREA: "immunology_inflammation"

# Date range
START_DATE: "2021-01-01"
END_DATE: null  # null = today

# Stages
EARLY_STAGE_ALLOWED:
  - "preclinical"
  - "phase 1"
```

---

## Documentation

- **`HYBRID_ARCHITECTURE.md`** - Complete technical documentation
- **`RUN_HYBRID.md`** - This file (quick start guide)
- **`deal_finder/keyword_generator.py`** - ChatGPT-5 keyword generation
- **`deal_finder/keyword_filter.py`** - Pre-filter logic
- **`hybrid_pipeline.py`** - Main orchestrator

---

## Ready to Run!

```bash
# Quick test first (5 min, $0.50)
python test_hybrid.py

# Then full run (40 min, $4)
python hybrid_pipeline.py --config config/config.yaml
```

🎉 You'll have your deals dataset in < 1 hour for ~$4!
