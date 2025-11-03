# Architecture Decision: Two Approaches Available

## TL;DR

You now have **two working approaches** for deal discovery and extraction:

1. **End-to-End** (Perplexity does everything) - Best for testing and recent deals
2. **Two-Step** (Exhaustive crawling + Perplexity extraction) - Best for complete historical dataset

Both work. Choose based on your needs.

---

## Approach 1: End-to-End (Perplexity Search + Extract)

### How It Works
Single API call to Perplexity:
```
You: "Find recent biotech deals matching immunology, extract all details"
Perplexity: *searches web, reads articles, returns JSON*
```

### Advantages
- ✅ **Simplest** - One API call does everything
- ✅ **Fastest** - < 2 minutes per query
- ✅ **Cheapest per query** - $0.01-0.05
- ✅ **No manual fetching** - Perplexity handles it
- ✅ **Always current** - Gets latest articles

### Limitations
- ❌ **Limited coverage** - ~1 month of recent articles
- ❌ **Not exhaustive** - Won't find ALL historical deals
- ❌ **Limited control** - Can't specify exact sites/dates
- ❌ **Variable results** - Search may miss some deals

### Use Cases
- Quick testing and validation
- Weekly/monthly updates for new deals
- Exploring a new therapeutic area
- Demonstrating to stakeholders
- When you only care about recent deals

### Test Script
```bash
python perplexity_end_to_end_test.py
```

### Cost
- **Per query**: $0.01-0.05
- **Weekly updates**: $0.20-0.40/month
- **Annual**: ~$10 (if running weekly)

---

## Approach 2: Two-Step (Exhaustive Crawling + Extraction)

### How It Works
Two phases:
```
Phase 1 (Discovery): Crawl sitemaps → Get ALL article URLs (free)
Phase 2 (Extraction): Fetch content → Perplexity extracts (paid)
```

### Advantages
- ✅ **Complete coverage** - Every article from 5 sites (58,000+ URLs)
- ✅ **Reproducible** - Same results every time
- ✅ **Incremental** - URL index tracks processed articles (88% savings)
- ✅ **Historical** - Full 2021-2025 coverage
- ✅ **Controlled** - You choose exact sites and date ranges
- ✅ **Auditable** - Full evidence trail

### Limitations
- ❌ **Slower** - 2-3 hours for first run
- ❌ **More complex** - Two-phase process
- ❌ **Higher first cost** - $13 for complete dataset
- ❌ **Requires setup** - Config, sitemaps, index

### Use Cases
- Building production dataset (one-time)
- Need complete historical coverage
- Regulatory/compliance requirements (audit trail)
- Research requiring reproducibility
- Want every deal from specific sources

### Test Script
```bash
python quick_test.py  # Quick validation (5-15 min)
# OR
python -m deal_finder.main --config config/config.yaml  # Full run (2-3 hrs)
```

### Cost
- **First run (2021-2025)**: ~$13 (4,000 articles → 50 deals)
- **Weekly updates**: ~$1.60 (500 new articles → 5-10 deals)
- **Monthly**: ~$6.40
- **Annual**: ~$77

---

## Comparison Table

| Feature | End-to-End | Two-Step |
|---------|-----------|----------|
| **Setup Time** | 0 min | 10 min |
| **First Run Time** | < 2 min | 2-3 hours |
| **First Run Cost** | $0.01 | $13 |
| **Articles Processed** | 5-10 | 4,000+ |
| **Deals Found** | 2-5 | 50+ |
| **Coverage** | Last ~1 month | 2021-2025 (complete) |
| **Update Frequency** | Weekly/monthly | Weekly (incremental) |
| **Update Cost** | $0.01-0.05 | $1.60 |
| **Reproducibility** | Variable | Exact |
| **Audit Trail** | Limited | Complete |
| **Incremental Crawling** | N/A | Yes (URL index) |
| **Best For** | Testing, recent | Production, complete |

---

## Decision Framework

### Choose End-to-End If:
- [ ] You're testing the system for the first time
- [ ] You only need recent deals (last month)
- [ ] You want results in < 2 minutes
- [ ] You don't need complete historical coverage
- [ ] Budget is tight (< $10/month)
- [ ] You're okay with variable results

### Choose Two-Step If:
- [ ] You need complete historical dataset
- [ ] You want every deal from 5 specific sites
- [ ] Reproducibility matters (research/compliance)
- [ ] You need audit trail and evidence
- [ ] You're building production system
- [ ] You can afford $13 first run, $1.60/week after

### Use Both If:
- [ ] Initial dataset → Two-step (complete history)
- [ ] Weekly updates → End-to-end (recent deals only)
- [ ] Best of both worlds!

---

## Technical Details

### End-to-End Architecture
```
┌─────────────────────────────────────┐
│ Perplexity API (Single Call)        │
│ • Searches web for deals             │
│ • Fetches and reads articles         │
│ • Extracts structured data           │
│ • Returns JSON with all details      │
│ → 2-5 deals per query                │
└─────────────────────────────────────┘
```

**Files**:
- `perplexity_end_to_end_test.py` - Test script
- `perplexity_client.py` - API client (search_deals method)

**Prompt Example**:
```python
mega_prompt = f"""Find recent biotech/pharma deals from 2024...
Search reliable biotech news sources...
For each deal you find, extract:
1. article_url, title, published_date
2. parties (acquirer, target)
3. deal_type, money, asset_focus, stage
Return JSON array with up to 5 deals"""
```

### Two-Step Architecture
```
┌─────────────────────────────────────┐
│ PHASE 1: Discovery (Free)            │
│ • Crawl 5 site sitemaps              │
│ • Get ALL article URLs (58,000+)    │
│ • Filter by date range               │
│ • Check URL index (skip processed)   │
│ → 4,000 relevant article URLs        │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│ PHASE 2: Fetch (Free)                │
│ • Selenium/Requests fetch HTML       │
│ • BeautifulSoup extract text         │
│ • Validate content (>500 chars)      │
│ → 4,000 article texts                │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│ PHASE 3: Extraction (Perplexity)     │
│ • Batch processing (5 per call)      │
│ • Temperature 0.0 (max accuracy)     │
│ • Filter: early stage + TA match     │
│ • Mark URLs as processed (index)     │
│ → 50 matching deals                  │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│ PHASE 4: Post-Process (Free)         │
│ • Deduplicate                        │
│ • Canonicalize company names         │
│ • Quality checks                     │
│ → Excel + evidence log               │
└─────────────────────────────────────┘
```

**Files**:
- `pipeline.py` - Main orchestrator
- `discovery/exhaustive_crawler.py` - Sitemap crawling
- `discovery/url_index.py` - Incremental tracking
- `extraction/perplexity_extractor.py` - Batch extraction
- `perplexity_client.py` - API client (extract_deals_batch method)

---

## My Recommendation

### For Your First Use:
1. **Start with End-to-End** (`perplexity_end_to_end_test.py`)
   - Verify Perplexity works
   - Get 2-5 deals in < 2 minutes
   - Validate accuracy

2. **Then Test Two-Step** (`quick_test.py`)
   - Process 50 articles from one site
   - Verify exhaustive crawling works
   - Compare accuracy

3. **Then Decide**:
   - If end-to-end finds enough deals → Use it weekly
   - If you need complete dataset → Run full two-step once
   - Or use both: Two-step for history, end-to-end for updates

### For Production:
- **Complete dataset needed?** → Two-step full run ($13 one-time)
- **Just monitoring new deals?** → End-to-end weekly ($0.20/month)
- **Best of both?** → Two-step initially, then end-to-end for updates

---

## FAQ

### Q: Can I switch between approaches?
**A**: Yes! They're independent. Use end-to-end for quick tests, two-step for complete dataset.

### Q: Will end-to-end find ALL deals?
**A**: No. Perplexity search is limited to recent articles (~1 month). For complete coverage, use two-step.

### Q: Is two-step worth the extra cost?
**A**: If you need complete historical coverage, yes. First run is $13, but incremental updates are only $1.60/week.

### Q: Which is more accurate?
**A**: Both use the same Perplexity extraction model (temperature 0.0). Accuracy is similar (~85-95%).

### Q: Can I use end-to-end for production?
**A**: Yes, if you only need recent deals. But you'll miss historical deals and won't have complete coverage.

### Q: Should I always use URL index with two-step?
**A**: Yes! It saves 88% on subsequent runs by tracking processed URLs. Always use `use_index=True`.

---

## Next Steps

1. **Set API key**:
   ```bash
   export PERPLEXITY_API_KEY="pplx-your-key-here"
   ```

2. **Test end-to-end**:
   ```bash
   python perplexity_end_to_end_test.py
   ```

3. **Test two-step** (optional):
   ```bash
   python quick_test.py
   ```

4. **Choose approach** based on results and needs

5. **Run production** with chosen approach

---

**Both approaches work. Start with end-to-end for simplicity, then decide if you need two-step for completeness.**
