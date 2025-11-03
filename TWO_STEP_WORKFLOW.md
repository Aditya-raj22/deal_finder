# Two-Step Workflow: Edit Keywords Before Running

## Overview

This workflow separates keyword generation from pipeline execution, allowing you to **manually edit keywords** before processing articles.

```
Step 1: Generate Keywords → Save to JSON → YOU EDIT
                                            ↓
Step 2: Load Keywords → Crawl → Filter → Extract → Excel
```

---

## Step 1: Generate Keywords

### Command
```bash
python step1_generate_keywords.py --config config/config.yaml
```

### What It Does
1. Loads your therapeutic area from config
2. Calls ChatGPT-5 **5 times** with different temperatures (0.2, 0.3, 0.5, 0.7, 0.8)
3. Each call generates 50-100 keywords
4. LLM judge consolidates to final list (80-150 keywords)
5. Also generates stage keywords and deal keywords
6. **Saves to**: `config/generated_keywords.json`

### Output File Structure
```json
{
  "therapeutic_area": "immunology_inflammation",
  "keywords": {
    "ta_keywords": [
      "autoimmune",
      "immune-mediated",
      "rheumatoid arthritis",
      "IL-6",
      "JAK inhibitor",
      ...
    ],
    "stage_keywords": [
      "preclinical",
      "pre-clinical",
      "phase 1",
      "phase I",
      "FIH",
      ...
    ],
    "deal_keywords": [
      "acquisition",
      "partnership",
      "licensing",
      ...
    ]
  },
  "generation_details": {...},
  "all_candidates": [...]
}
```

### Time & Cost
- **Time**: ~30-60 seconds
- **Cost**: ~$0.50 (one-time per TA)

---

## Between Steps: EDIT THE FILE!

### Open the keywords file:
```bash
# Mac
open config/generated_keywords.json

# Linux
nano config/generated_keywords.json

# Or use any text editor
```

### What to Edit

#### 1. Add Missing Keywords
Look at your TA vocab (`config/ta_vocab/immunology_inflammation.json`) and add any keywords that ChatGPT missed:

```json
"ta_keywords": [
  ...existing keywords...,
  "complement inhibitor",        // Add this
  "C5a receptor antagonist",     // Add this
  "fecal microbiota transplant"  // Add this
]
```

#### 2. Remove Overly Generic Keywords
Delete keywords that are too broad:

```json
// Remove these:
"therapy",
"treatment",
"drug",
"medicine",
"healthcare"
```

#### 3. Adjust Stage Keywords
Add variations you know appear in articles:

```json
"stage_keywords": [
  ...existing...,
  "discovery stage",
  "early development",
  "research stage"
]
```

#### 4. Fine-tune Deal Keywords
Add specific phrases:

```json
"deal_keywords": [
  ...existing...,
  "strategic alliance",
  "co-development",
  "asset purchase"
]
```

### Tips for Editing

**Goal**: Cast a wide net (avoid false negatives), but not TOO wide (avoid false positives)

**Good additions**:
- Disease abbreviations (RA, UC, CD)
- Drug mechanism abbreviations (IL-6i, JAKi)
- Specific company drug class terms
- Regional spelling variations (autoimmunisation vs autoimmunization)

**Bad additions**:
- Super generic terms (health, patient, clinical)
- Terms that appear in ALL biotech news (FDA, trial, data)

---

## Step 2: Run Pipeline

### Option A: Test Crawling First (Recommended)

Before running the full pipeline, you can test that all 5 sitemaps are being crawled correctly:

```bash
python test_crawl_only.py --config config/config.yaml
```

**What it does**:
- Crawls all 5 sitemaps
- Reports URLs found per site
- Shows sample URLs
- **Does NOT** fetch content or call APIs (fast and free!)

**Use this to**:
- Verify sitemaps are accessible
- Check expected URL counts before spending money
- Debug crawling issues without API costs

---

### Option B: Run Full Pipeline

```bash
python step2_run_pipeline.py --config config/config.yaml
```

### What It Does
1. **Loads** your edited keywords from `config/generated_keywords.json`
2. **Crawls** all 5 sitemaps (FierceBiotech, FiercePharma, GEN, BioPharma Dive, Endpoints News)
3. **Fetches** article content (Selenium)
4. **Deduplicates** by title (removes articles with 80%+ similar titles)
5. **Filters** by keywords (TA + stage + deal)
6. **Extracts** with Perplexity (only filtered articles)
7. **Deduplicates** deals (by acquirer + target + date)
8. **Saves** two Excel files:
   - Deals (extracted)
   - Rejected (passed keywords but not Perplexity)

### Expected Results (2021-2025, All 5 Sites)

| Metric | Count |
|--------|-------|
| URLs crawled | ~5,000 |
| Articles fetched | ~4,000 |
| After title deduplication | ~2,500 |
| After keyword filter | ~500-800 |
| Sent to Perplexity | ~500-800 |
| Deals extracted | ~30-50 |
| After deal deduplication | ~25-40 |

### Time & Cost
- **Time**: ~2-3 hours
- **Cost**: ~$10-15 (500-800 articles × $0.06 per 5 articles)

---

## Deduplication Strategy

### 1. Title Deduplication (Before Perplexity)
**Purpose**: Same deal reported by multiple sites

**How it works**:
```python
# Compare titles with fuzzy matching
similarity = SequenceMatcher(None, title1, title2).ratio()
if similarity > 0.8:  # 80% similar
    # It's a duplicate - keep only one
```

**Example**:
- "Pfizer acquires Arena for $6.7B" (FierceBiotech)
- "Pfizer buys Arena Pharma in $6.7B deal" (FiercePharma)
- Similarity: 85% → **Duplicate!** Keep first, remove second

**Savings**: ~40% reduction (5,000 → 3,000 articles)

---

### 2. Deal Deduplication (After Perplexity)
**Purpose**: Same deal extracted multiple times

**How it works**:
```python
# Create unique key: (acquirer + target + date)
key = ("Pfizer", "Arena Pharmaceuticals", "2021-12-13")

# If key already exists, keep the one with more complete data
if existing_deal.total_value < new_deal.total_value:
    replace_with_new_deal()
```

**Example**:
- Deal 1: Pfizer + Arena, no money data
- Deal 2: Pfizer + Arena, $6.7B total value
- Result: **Keep Deal 2** (more complete)

---

## Configuration Options

### Year-based Date Filtering

Instead of exact dates, you can filter by year only:

```yaml
# config/config.yaml

# Option 1: Exact date range (current)
START_DATE: "2024-01-01"
END_DATE: "2024-12-31"

# Option 2: Year-based (simpler)
START_DATE: "2024"
END_DATE: "2024"  # or null for current year
```

**Benefits of year-based**:
- Simpler logic
- Catches year-end edge cases (deal in Dec, article in Jan)
- Perplexity extracts actual announcement date from text

**When to use**:
- For complete datasets (2021-2025)
- When you want Perplexity to find exact dates

---

## Keyword Filter Tuning

### Too Many False Positives (>70% of filtered articles rejected by Perplexity)

**Problem**: Keywords too broad

**Solution**: Increase `min_ta_matches` in `step2_run_pipeline.py`:
```python
keyword_filter = KeywordFilter(
    ...,
    min_ta_matches=2  # Require 2+ TA keywords instead of 1
)
```

---

### Too Many False Negatives (Missing deals in rejected Excel)

**Problem**: Keywords too strict

**Solution 1**: Add more keywords in Step 1 (edit JSON)

**Solution 2**: Relax deal keyword requirement:
```python
keyword_filter = KeywordFilter(
    ...,
    require_deal_keyword=False  # Don't require deal keyword
)
```

---

## Outputs

### Output 1: `hybrid_deals_YYYYMMDD_HHMMSS_[id].xlsx`

**Columns**:
- date_announced (from Perplexity, not article publish date!)
- target (canonicalized)
- acquirer (canonicalized)
- deal_type_detailed
- stage
- therapeutic_area
- asset_focus
- total_deal_value_usd
- upfront_value_usd
- source_url
- needs_review (TRUE/FALSE)
- evidence

**Expected**: ~25-40 deals from 2021-2025

---

### Output 2: `hybrid_rejected_YYYYMMDD_HHMMSS_[id].xlsx`

**Columns**:
- url
- title
- ta_keywords (which keywords matched)
- stage_keywords
- deal_keywords
- perplexity_reason (why rejected)

**Use case**:
- Backup "just in case"
- Check if Perplexity missed anything
- Debug keyword filter tuning

**Expected**: ~450-750 URLs

---

## FAQ

### Q: Do I need to run Step 1 every time?
**A**: No! Only when:
- Changing therapeutic area
- Want to regenerate keywords with different approach
- First time running

Once you have `config/generated_keywords.json`, you can reuse it for Step 2.

---

### Q: Can I use my own keywords instead of generating?
**A**: Yes! Just create `config/generated_keywords.json` manually with this structure:

```json
{
  "keywords": {
    "ta_keywords": ["your", "keywords", "here"],
    "stage_keywords": ["preclinical", "phase 1"],
    "deal_keywords": ["acquisition", "partnership"]
  }
}
```

---

### Q: Why filter by title before keywords?
**A**:
- Title deduplication is cheap (instant)
- Removes obvious duplicates before expensive keyword matching
- Saves processing time

---

### Q: What if two sites report different deal values?
**A**:
- Deal deduplication keeps the one with larger value
- Assumes more complete data = more accurate
- Can manually review if suspicious

---

### Q: Should I use year-based or exact date filtering?
**A**:
- **Year-based**: Simpler, catches edge cases, lets Perplexity extract exact date
- **Exact dates**: More control, smaller result set
- **Recommendation**: Use year-based for complete datasets

---

## Complete Example

```bash
# 1. Generate keywords (30-60 seconds, $0.50)
python step1_generate_keywords.py

# 2. Edit keywords
open config/generated_keywords.json
# Add/remove keywords as needed

# 3. Run pipeline (2-3 hours, $10-15)
python step2_run_pipeline.py

# 4. Check results
ls -lh output/hybrid_*.xlsx

# 5. Open in Excel
open output/hybrid_deals_*.xlsx
open output/hybrid_rejected_*.xlsx
```

---

## Troubleshooting

### "Keywords file not found"
**Solution**: Run Step 1 first
```bash
python step1_generate_keywords.py
```

### "No articles passed keyword filter"
**Solutions**:
1. Check keywords are in JSON file
2. Try relaxing `require_deal_keyword=False`
3. Lower `min_ta_matches` to 1

### "Too expensive"
**Check**:
- How many articles passed keyword filter?
- Should be ~500-800 for all 5 sites
- If >1,500, keywords are too broad

### "Title deduplication too aggressive"
**Adjust threshold** in `step2_run_pipeline.py`:
```python
if similarity > 0.9:  # Increase from 0.8 to 0.9
```

---

## Cost Summary

| Step | Time | Cost | One-time? |
|------|------|------|-----------|
| **Step 1** (generate keywords) | 1 min | $0.50 | Yes ✅ |
| **Step 2** (pipeline) | 2-3 hrs | $10-15 | No |
| **Total first run** | 2-3 hrs | **$10.50-15.50** | - |
| **Subsequent runs** | 2-3 hrs | **$10-15** | - |

**vs $40-50 without keyword filter (70% savings!)**

---

## Next Steps

1. Run Step 1 to generate keywords
2. Edit the JSON file
3. Run Step 2 to process all articles
4. Review both Excel outputs
5. Tune keywords if needed and re-run Step 2

**Ready to start!** 🚀
