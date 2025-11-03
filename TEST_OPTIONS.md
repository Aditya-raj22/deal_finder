# Test Options - Choose Your Testing Strategy

## Option 1: Ultra-Quick Test (Recommended) ⚡

**Time:** < 2 minutes
**Cost:** ~$0.01
**Articles:** 3 known deal articles

```bash
python ultra_quick_test.py
```

### What It Does
1. Uses 3 known deal articles (guaranteed to contain deals)
2. Fetches content from these URLs
3. Extracts using Perplexity
4. Saves to Excel

### When to Use
- **First time testing** - Verify everything works
- **After code changes** - Quick validation
- **Demonstrating to stakeholders** - Fast results

### Expected Output
```
✅ ULTRA-QUICK TEST COMPLETE!

Results:
  • Processed: 3 articles
  • Extracted: 2-3 deals
  • Output: output/ultra_quick_test_abc123.xlsx
```

---

## Option 2: Quick Test 🏃

**Time:** 5-15 minutes
**Cost:** ~$0.03-0.10
**Articles:** First 50 from FiercePharma

```bash
python quick_test.py
```

### What It Does
1. Crawls FiercePharma sitemap (gets all URLs)
2. Takes first 50 articles
3. Fetches content
4. Processes in batches until 1 deal found
5. Saves to Excel and stops

### When to Use
- **Testing real-world discovery** - Uses actual sitemap crawling
- **After discovery changes** - Verify crawling works
- **Testing with unknown articles** - Not pre-selected

### Expected Output
```
🎉 DEAL FOUND!
   Acquirer: Pfizer
   Target: Arena Pharmaceuticals
   Deal Type: M&A

✅ Quick test complete!
Output: output/quick_test_abc123.xlsx
```

---

## Option 3: Single Site Test 🏢

**Time:** 30-60 minutes
**Cost:** ~$3-5
**Articles:** All from one site (e.g., FiercePharma)

```bash
# Edit config to limit to one site, then run:
python -m deal_finder.main --config config/config.yaml
```

### Setup
Create `config/test_config.yaml`:
```yaml
THERAPEUTIC_AREA: "immunology_inflammation"
START_DATE: "2024-01-01"  # Just 2024
END_DATE: null
DRY_RUNS_TO_CONVERGE: 1  # Stop after first cycle
```

### When to Use
- **Testing complete pipeline** - Full end-to-end test
- **Realistic dataset** - Get 5-10 real deals
- **Before production run** - Validate everything

---

## Option 4: Full Production Run 🚀

**Time:** 2-3 hours
**Cost:** ~$13
**Articles:** All 5 sites, complete historical

```bash
python -m deal_finder.main --config config/config.yaml
```

### When to Use
- **Building complete dataset** - Get all deals
- **After successful tests** - Ready for production
- **Initial historical crawl** - One-time setup

---

## Comparison Table

| Test Type | Time | Cost | Articles | Deals | Use Case |
|-----------|------|------|----------|-------|----------|
| **Ultra-Quick** | <2 min | $0.01 | 3 | 2-3 | First test, validation |
| **Quick** | 5-15 min | $0.03-0.10 | 50 | 1+ | Discovery testing |
| **Single Site** | 30-60 min | $3-5 | ~1000 | 5-10 | End-to-end test |
| **Full Production** | 2-3 hours | $13 | ~4000 | 50+ | Complete dataset |

---

## Running the Tests

### Prerequisites
```bash
# Set API key (required for all tests)
export PERPLEXITY_API_KEY="pplx-your-key-here"

# Verify it's set
echo $PERPLEXITY_API_KEY
```

### Ultra-Quick Test (Start Here!)
```bash
# Should complete in < 2 minutes
python ultra_quick_test.py

# Check output
ls -lh output/ultra_quick_test_*.xlsx
open output/ultra_quick_test_*.xlsx  # Mac
# or: xdg-open output/ultra_quick_test_*.xlsx  # Linux
```

### Quick Test
```bash
# Processes up to 50 articles from FiercePharma
python quick_test.py

# Check output
ls -lh output/quick_test_*.xlsx
```

### Single Site Test
```bash
# Create test config
cat > config/test_config.yaml << EOF
THERAPEUTIC_AREA: "immunology_inflammation"
START_DATE: "2024-01-01"
END_DATE: null
DRY_RUNS_TO_CONVERGE: 1
EOF

# Run pipeline with test config
python -m deal_finder.main --config config/test_config.yaml

# Check output
ls -lh output/deals_*.xlsx
```

---

## What to Check in Results

### In Excel File

1. **Columns Present:**
   - `date_announced` - Deal announcement date
   - `target` - Company being acquired/licensed from
   - `acquirer` - Company acquiring/licensing
   - `deal_type_detailed` - M&A, Partnership, Licensing, etc.
   - `stage` - Preclinical, Phase 1, etc.
   - `therapeutic_area` - Should match your config
   - `total_deal_value_usd` - Total value in USD
   - `source_url` - Link to original article
   - `needs_review` - TRUE if low confidence

2. **Data Quality:**
   - Parties are company names (not "NEW YORK" or city names)
   - Dates are reasonable (not far future or ancient past)
   - Money values make sense (>$1M typically)
   - Stage matches your criteria (preclinical, phase 1)

3. **Spot Check:**
   - Open 2-3 `source_url` links
   - Verify the deal is real
   - Check if parties/money are correct

### In Logs

Look for:
```
✓ Crawler initialized
✓ Fetched X articles
✓ Extraction complete
✓ Found X deals
✓ Saved to: output/...
```

Watch for warnings:
```
⚠ Failed to fetch: [URL]
⚠ Extraction filtered out (expected for non-deals)
```

---

## Troubleshooting

### "PERPLEXITY_API_KEY not set"
```bash
export PERPLEXITY_API_KEY="pplx-..."
python ultra_quick_test.py  # Try again
```

### "No deals found"
This is OK for quick_test.py (first 50 articles might not have deals)
Try ultra_quick_test.py which uses known deal articles.

### "Failed to fetch articles"
- Check internet connection
- Some sites may block automated requests
- Selenium may need Chrome/ChromeDriver installed

### "Extraction returns all nulls"
- Articles don't contain deals (expected)
- Or articles don't match therapeutic area filter
- Check ta_vocab includes/excludes in config

### "Excel file is empty"
- Extraction filtered out all deals
- Check `needs_review` field - may need to adjust filters
- Try ultra_quick_test.py with known articles

---

## Recommended Testing Sequence

### Day 1: Initial Validation
1. Run `ultra_quick_test.py` (2 min)
2. Open Excel, verify 2-3 deals
3. Click source URLs, verify deals are real

### Day 2: Discovery Testing
1. Run `quick_test.py` (10 min)
2. Verify sitemap crawling works
3. Check 1 deal extracted correctly

### Day 3: End-to-End Testing
1. Run single site test (1 hour)
2. Get 5-10 deals from one site
3. Spot check 3 deals for accuracy
4. Verify deduplication works

### Day 4: Production Run
1. Run full pipeline (2-3 hours)
2. Get complete dataset (50+ deals)
3. Review needs_review flags
4. Set up weekly cron job

---

## Success Criteria

### ✅ Tests Pass If:
- Ultra-quick test finds 2-3 deals in <2 minutes
- Quick test finds ≥1 deal in <15 minutes
- Excel file has correct columns
- Spot-checked deals are accurate (parties, money, date)
- No Python errors or crashes

### ⚠ Review Needed If:
- >50% of deals have `needs_review=TRUE`
- Many duplicate deals in output
- Money values are wrong (off by 10x, etc.)
- Dates are obviously wrong
- Company names are cities/locations

### ❌ Tests Fail If:
- Python import errors
- "API key not set" errors
- No deals found in ultra_quick_test.py
- Excel file not created
- All extractions return null

---

## Next Steps After Testing

Once tests pass:
1. ✅ Set up production config with your date range
2. ✅ Run full pipeline for complete dataset
3. ✅ Set up weekly cron job for updates
4. ✅ Monitor logs for issues
5. ✅ Review flagged deals monthly

Happy testing! 🚀
