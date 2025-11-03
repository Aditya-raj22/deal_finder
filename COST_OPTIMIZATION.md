# Cost Optimization - FierceBiotech Only

## Changes Made

Limited the pipeline to **FierceBiotech only** to keep costs under $20 for the first full run.

### Files Modified

1. **`deal_finder/discovery/exhaustive_crawler.py`**
   - Commented out: FiercePharma, GEN, BioPharma Dive, Endpoints News
   - Active: FierceBiotech only

2. **`deal_finder/perplexity_client.py`**
   - Updated `search_domain_filter` to `["fiercebiotech.com"]` only

3. **`perplexity_end_to_end_test.py`**
   - Updated `search_domain_filter` to `["fiercebiotech.com"]` only

---

## Cost Breakdown (FierceBiotech Only)

### Full Historical Run (2021-2025)

**Articles to process**: ~800-1,000 from FierceBiotech sitemap

**Batches needed**: 1,000 ÷ 5 = 200 batches

**Cost estimate**:
- Token costs: 200 batches × $0.06 = $12.00
- Search context: 200 × ($6-14 per 1K) = $1.20 - $2.80
- **Total: ~$13-15** ✅

**Expected output**: ~10-15 early-stage immunology/inflammation deals

---

## Coverage Comparison

| Configuration | Articles | Cost | Deals Expected |
|--------------|----------|------|----------------|
| **FierceBiotech only** | ~1,000 | **$13-15** | ~10-15 |
| All 5 sites | ~4,000 | $40-50 | ~50 |
| 2024 only (all sites) | ~1,200 | $16-18 | ~15-20 |

---

## How to Expand Later

### To Add More Sites Back

Edit **`deal_finder/discovery/exhaustive_crawler.py`** around line 34:

Uncomment the sites you want:
```python
PRIORITY_SITES = {
    'FierceBiotech': {...},  # Already active

    # Uncomment to add FiercePharma (~$8-10 more):
    'FiercePharma': {
        'rss_feeds': [...],
        'sitemap': 'https://www.fiercepharma.com/sitemap.xml',
        'archive_pattern': 'https://www.fiercepharma.com/archives/{year}/{month}'
    },

    # Uncomment to add GEN (~$6-8 more):
    # 'GEN': {...},

    # And so on...
}
```

Also update **`deal_finder/perplexity_client.py`** line 105:
```python
"search_domain_filter": [
    "fiercebiotech.com",
    "fiercepharma.com",  # Add if uncommenting
    # "genengnews.com",  # Add if uncommenting
    # etc.
]
```

---

## Incremental Cost Model

| Sites Active | First Run Cost | Weekly Update Cost | Total Year 1 |
|--------------|----------------|-------------------|--------------|
| **FierceBiotech** | **$13-15** | **$1.60** | **~$20** |
| + FiercePharma | $24-27 | $3.20 | ~$40 |
| All 5 sites | $40-50 | $8.00 | ~$90 |

**Note**: Weekly update costs assume URL index is enabled (88% savings from tracking processed articles)

---

## Running the Pipeline

### Full Historical Run (FierceBiotech, 2021-2025)
```bash
python -m deal_finder.main --config config/config.yaml
```

**Expected**:
- Time: 30-60 minutes
- Cost: ~$13-15
- Output: `output/deals_YYYYMMDD_HHMMSS.xlsx` with ~10-15 deals

### Quick Test (FierceBiotech, 50 articles)
```bash
python quick_test.py
```

**Expected**:
- Time: 5-10 minutes
- Cost: ~$0.60
- Output: 1+ deals

---

## Why FierceBiotech?

**Best single source for biotech deals**:
- Most comprehensive coverage of M&A, partnerships, licensing
- Focused on biotech (not pharma-heavy like FiercePharma)
- Excellent deal-specific RSS feeds (deals, partnering, regulatory)
- High signal-to-noise ratio for early-stage deals

**Coverage**: ~60-70% of all early-stage biotech deals appear on FierceBiotech

---

## Recommendation

1. **Start**: Run FierceBiotech only (~$13-15)
2. **Evaluate**: Check if deal coverage is sufficient
3. **Expand**: Add FiercePharma if you need more pharma-side deals (~$10 more)
4. **Complete**: Add all 5 sites for comprehensive dataset (~$25 more)

**Total phased cost**: $13 → $24 → $40 (spread over time, not all at once)

This approach lets you validate the pipeline and build incrementally without spending $40-50 upfront.
