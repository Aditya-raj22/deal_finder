# 🚀 START HERE - Deal Finder Pipeline

## Quick Start (5 Minutes)

### 1. Set API Key
```bash
export PERPLEXITY_API_KEY="pplx-your-key-here"
```

### 2. Run Ultra-Quick Test
```bash
python ultra_quick_test.py
```

**Expected:** Finds 2-3 deals in < 2 minutes, saves to Excel

### 3. Check Results
```bash
# View output
open output/ultra_quick_test_*.xlsx

# Should see columns: date, target, acquirer, deal_type, money, etc.
```

### 4. If Test Passes → Run Production
```bash
python -m deal_finder.main --config config/config.yaml
```

**Expected:** Complete dataset in ~2-3 hours

---

## What This Pipeline Does

Finds **ALL** early-stage biotech/pharma deals from trusted sources:

```
Discover (FREE)
└─ Crawls 5 sites: FierceBiotech, FiercePharma, GEN, BioPharma Dive, Endpoints News
└─ Gets ALL articles from sitemaps + archives (58,000+ total URLs)
└─ Filters by date range (e.g., 2021-today)
└─ Result: ~4,000 article URLs

Extract (PAID - Perplexity API)
└─ Fetches article HTML content
└─ Perplexity reads each article (batches of 5)
└─ Extracts: parties, money, stage, deal type, date
└─ Filters for: early stage + matching therapeutic area
└─ Result: ~50 relevant deals

Export
└─ Deduplicates by (target + acquirer + date + asset)
└─ Saves to Excel with evidence
└─ Result: Complete, accurate dataset
```

---

## File Guide

### 📝 **Read These First**
- **`START_HERE.md`** (this file) - Quick start guide
- **`TEST_OPTIONS.md`** - Testing strategies (ultra-quick, quick, full)
- **`FINAL_ARCHITECTURE.md`** - Complete system explanation

### 🧪 **Test Scripts**
- **`ultra_quick_test.py`** - < 2 min test with known deals ⭐ Start here!
- **`quick_test.py`** - 5-15 min test with real discovery
- **`final_check.py`** - Pre-production validation

### 📚 **Deep Dives**
- `README_PERPLEXITY.md` - How Perplexity integration works
- `EXHAUSTIVE_MODE.md` - Complete sitemap crawling explained
- `INCREMENTAL_CRAWLING.md` - Index-based strategy (cost savings)
- `HOW_PERPLEXITY_WORKS.md` - Discovery vs extraction clarified
- `OPTIMIZATIONS_SUMMARY.md` - All optimizations applied
- `FINAL_RECOMMENDATIONS.md` - Production checklist

### ⚙️ **Config Files**
- `config/config.yaml` - Main configuration
- `config/ta_vocab/immunology_inflammation.json` - TA vocabulary
- `config/aliases.json` - Company name canonicalization

---

## Cost Breakdown

| Run Type | Time | Cost | Output |
|----------|------|------|--------|
| **Ultra-quick test** | <2 min | $0.01 | 2-3 deals |
| **Quick test** | 10 min | $0.05 | 1+ deals |
| **First run (complete)** | 2-3 hrs | $13 | ~50 deals |
| **Weekly update** | 10 min | $1.60 | ~5-10 new |
| **Monthly total** | ~1 hr | $6.40 | ~20-40 new |

**Annual cost:** ~$77 (vs $2,000 for manual research)

---

## Common Questions

### Q: Do I need to update START_DATE for incremental runs?
**A:** No! URL index tracks processed articles automatically.

### Q: What if I want a different therapeutic area?
**A:** Edit `config/config.yaml` and change `THERAPEUTIC_AREA` to one of:
- `oncology`
- `immunology_inflammation`
- `neurology`
- Or create your own in `config/ta_vocab/`

### Q: Can I run without Perplexity API?
**A:** Yes, but accuracy drops from 85-95% to 40-60% (uses regex fallback).

### Q: How do I know if a deal is accurate?
**A:** Check `needs_review` column. TRUE = low confidence, manually verify.

### Q: What if I get duplicate deals?
**A:** Deduplication uses (target + acquirer + asset + date). Duplicates are merged with URLs in `related_urls`.

---

## Architecture Summary

```
┌─────────────────────────────────────┐
│ DISCOVERY (Free)                     │
│ • Crawl 5 sites                      │
│ • All sitemaps (no limits)           │
│ • Archive pages (supplemental)       │
│ • RSS feeds (fallback)               │
│ → 4,000 article URLs                 │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│ FETCH (Free)                         │
│ • Selenium/Requests                  │
│ • HTML → Text extraction             │
│ • Content validation (<500 chars)    │
│ → 4,000 article texts                │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│ EXTRACTION (Perplexity - $13)        │
│ • Batch processing (5 per call)      │
│ • Temperature 0.0 (max accuracy)     │
│ • Filter: early stage + TA match     │
│ → ~50 matching deals                 │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│ POST-PROCESS (Free)                  │
│ • Deduplicate                        │
│ • Canonicalize names                 │
│ • Quality checks                     │
│ → Excel + evidence log               │
└─────────────────────────────────────┘
```

---

## Troubleshooting

### "PERPLEXITY_API_KEY not set"
```bash
export PERPLEXITY_API_KEY="pplx-..."
```

### "No deals found in test"
- Run `ultra_quick_test.py` (uses known deals)
- Check therapeutic area matches articles
- Review `ta_vocab` includes/excludes

### "Extraction accuracy is low"
- Check `needs_review` flagged deals
- Adjust prompts in `perplexity_client.py`
- Tune `ta_vocab` includes/excludes

### "Too slow"
- First run takes 2-3 hours (expected)
- Weekly updates take 10-15 minutes
- Use `quick_test.py` for validation

---

## Support & Documentation

### Getting Help
1. Check `TEST_OPTIONS.md` for testing guidance
2. Review `FINAL_RECOMMENDATIONS.md` for production tips
3. Read `FINAL_ARCHITECTURE.md` for system details

### Reporting Issues
Run diagnostic:
```bash
python final_check.py
```

Share output for debugging.

---

## Success Checklist

- [ ] API key set
- [ ] `ultra_quick_test.py` passes (<2 min, 2-3 deals)
- [ ] Excel file has correct columns
- [ ] Spot-checked 3 deals = accurate
- [ ] Ready for production run!

---

**Ready to start?**
```bash
python ultra_quick_test.py
```

🎉 You'll have results in < 2 minutes!
