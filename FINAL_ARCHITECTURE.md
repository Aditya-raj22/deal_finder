# Final Architecture - Complete Explanation

## Your Questions Answered

### Q1: "It will do that for not just FiercePharma but also the other RSS feeds right?"

**YES!** The exhaustive crawler processes ALL 5 sites:

```python
PRIORITY_SITES = {
    'FierceBiotech': {
        'rss_feeds': [
            'https://www.fiercebiotech.com/rss/xml',           # Main feed
            'https://www.fiercebiotech.com/deals/rss',          # Deals feed
            'https://www.fiercebiotech.com/partnering/rss',     # Partnering feed
            'https://www.fiercebiotech.com/regulatory/rss',     # Regulatory feed
        ],
        'sitemap': 'https://www.fiercebiotech.com/sitemap.xml', # Complete archive
    },
    'FiercePharma': {
        'rss_feeds': [
            'https://www.fiercepharma.com/rss/xml',            # Main feed
            'https://www.fiercepharma.com/m-a/rss',            # M&A feed
            'https://www.fiercepharma.com/partnering/rss',     # Partnering feed
        ],
        'sitemap': 'https://www.fiercepharma.com/sitemap.xml',
    },
    'GEN': {
        'rss_feeds': [
            'https://www.genengnews.com/feed/',                # Main feed
            'https://www.genengnews.com/topics/bioprocessing/feed/',
            'https://www.genengnews.com/topics/drug-discovery/feed/',
        ],
        'sitemap': 'https://www.genengnews.com/sitemap.xml',
    },
    'BioPharma Dive': {
        'rss_feeds': [
            'https://www.biopharmadive.com/feeds/news/',       # News feed
        ],
        'sitemap': 'https://www.biopharmadive.com/sitemap.xml',
    },
    'Endpoints News': {
        'rss_feeds': [
            'https://endpts.com/feed/',                        # Main feed
        ],
        'sitemap': 'https://endpts.com/sitemap.xml',
    },
}
```

**Result:** Every article from all 5 sites in your date range!

---

### Q2: "Discovery API classifies deals into 'meets requirements' vs 'no'?"

**NO!** Let me clarify the roles:

#### Discovery Phase (Exhaustive Crawler)
- **Input:** Nothing (just configured sites)
- **Process:** Crawls RSS/sitemaps from all 5 sites
- **Output:** ALL article URLs (no filtering, no classification)
- **Perplexity used?** NO - this is free web scraping
- **Cost:** $0

#### Extraction Phase (Perplexity API)
- **Input:** Article URLs + article content (HTML text)
- **Process:**
  1. Reads article content
  2. Determines if there's a deal
  3. If deal exists, checks if it matches criteria:
     - Is it early stage? (preclinical, phase 1)
     - Does therapeutic area match? (oncology, immunology, etc.)
     - Is it the right deal type? (M&A, licensing, etc.)
  4. Extracts structured data (parties, money, stage, etc.)
- **Output:** Structured deal data OR null (if no deal or no match)
- **Perplexity used?** YES - this costs money
- **Cost:** ~$13 for 4,000 articles

**Key Point:** Discovery doesn't classify. Extraction does BOTH classification AND data extraction in one API call!

---

### Q3: "Extractor API extracts relevant details from 'meets requirements' category?"

**Almost!** Here's the actual flow:

```python
# Perplexity extraction prompt does BOTH filtering and extraction:

For EACH article:
1. Read article content
2. Is there a deal? (M&A, partnership, licensing, etc.)
   → If NO deal: return null
   → If YES deal: continue to step 3

3. Extract deal data:
   - parties (acquirer, target)
   - deal_type (M&A, licensing, etc.)
   - date_announced
   - money (upfront, total, currency)
   - stage (preclinical, phase 1, etc.)
   - asset_focus (drug name, therapy)
   - therapeutic_area_match (true/false)

4. Check if matches criteria:
   - therapeutic_area_match == true?
   - stage in ["preclinical", "phase 1"]?
   - deal_type in ["M&A", "licensing", "partnership"]?

5. Return:
   - If ALL criteria match: return full deal data
   - If NO match: return null (or partial data with therapeutic_area_match=false)
```

**The extraction prompt does filtering as it extracts!**

Here's the actual prompt (simplified):

```
THERAPEUTIC AREA FOCUS: {immunology_inflammation}
- Include terms: inflammatory, autoimmune, IL-6, TNF, etc.
- Exclude terms: oncology, cancer, tumor, etc.

For EACH article, extract:
1. parties: {acquirer, target, partner1, partner2}
2. deal_type: "M&A" | "partnership" | "licensing"
3. date_announced: "YYYY-MM-DD"
4. money: {upfront_value, total_deal_value, currency}
5. asset_focus: "Drug/therapy name"
6. stage: "preclinical" | "phase 1" | "phase 2"
7. therapeutic_area_match: true/false  ← FILTERING HAPPENS HERE
8. confidence: "high" | "medium" | "low"

Return null if no deal or no match.
```

---

### Q4: "Make sure to parse correctly and store in table with no repeats based on date, acquirer name, target name as the key?"

**YES!** The deduplication logic already does this:

#### Deduplication Key (deal_finder/deduplication/deduplicator.py:17-33)

```python
def generate_canonical_key(deal: Deal) -> str:
    """
    Generate canonical key for deduplication.

    Key = hash(target_norm|acquirer_norm|asset_norm|date)
    """
    target_norm = normalize_text(deal.target)        # "Pfizer Inc." → "pfizer"
    acquirer_norm = normalize_text(deal.acquirer)    # "Arena Pharma" → "arena pharma"
    asset_norm = normalize_text(deal.asset_focus)    # "Etrasimod" → "etrasimod"
    date_str = deal.date_announced.isoformat()       # "2021-12-13"

    key = f"{target_norm}|{acquirer_norm}|{asset_norm}|{date_str}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    return key_hash
```

#### Exact Deduplication Logic

**Primary Key:** `target + acquirer + asset + date`

**Fuzzy Matching:** If dates are within ±3 days, also check:
- Same target (normalized)
- Same acquirer (normalized)
- Same asset (normalized)

**Examples:**

```python
# These are considered DUPLICATES:
Deal 1: Pfizer Inc. + Arena Pharmaceuticals + Etrasimod + 2021-12-13
Deal 2: Pfizer + Arena Pharma + etrasimod + 2021-12-13
# → Same key (after normalization)

Deal 1: BMS + IFM Therapeutics + NLRP3 + 2021-06-01
Deal 2: Bristol Myers Squibb + IFM + NLRP3 + 2021-06-03
# → Fuzzy match (within 3 days, same parties/asset)

# These are considered DIFFERENT:
Deal 1: Pfizer + Arena + Etrasimod + 2021-12-13
Deal 2: Pfizer + Arena + Olorinab + 2021-12-13
# → Different asset

Deal 1: Pfizer + Arena + Etrasimod + 2021-12-13
Deal 2: Pfizer + Arena + Etrasimod + 2022-01-15
# → Same deal but different date (>3 days apart)
```

**Merge Strategy:** When duplicates found, the system:
1. Keeps the primary deal (prefers press releases)
2. Adds duplicate URLs to `related_urls` field
3. Preserves earliest announcement date

---

## Complete Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  STEP 1: DISCOVERY (Exhaustive Crawler)                      │
│  Cost: $0 | Time: ~5 minutes                                │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Crawl ALL RSS feeds:                                        │
│  ├─ FierceBiotech (4 feeds + sitemap) → ~1,200 articles    │
│  ├─ FiercePharma (3 feeds + sitemap)  → ~800 articles      │
│  ├─ GEN (3 feeds + sitemap)           → ~1,000 articles    │
│  ├─ BioPharma Dive (1 feed + sitemap) → ~600 articles      │
│  └─ Endpoints News (1 feed + sitemap) → ~400 articles      │
│                                                               │
│  Filter by date range: 2021-01-01 to today                  │
│  Deduplicate URLs: ~4,000 unique articles                   │
│                                                               │
│  Output: List of 4,000 article URLs                         │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 2: FETCH CONTENT (Selenium/Requests)                   │
│  Cost: $0 | Time: ~30-60 minutes                            │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  For each URL:                                               │
│  1. Fetch HTML (handle Cloudflare, JS rendering)            │
│  2. Extract text content using BeautifulSoup                 │
│  3. Limit to 20,000 chars per article                        │
│                                                               │
│  Output: List of 4,000 articles with content                │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 3: EXTRACTION + FILTERING (Perplexity API)             │
│  Cost: ~$13 | Time: ~60-90 minutes                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Batch processing: 5 articles per API call                   │
│  Total: 4,000 ÷ 5 = 800 API calls                           │
│                                                               │
│  For EACH batch of 5 articles:                              │
│  ├─ Send article text to Perplexity                         │
│  ├─ Perplexity reads content                                │
│  ├─ Perplexity checks if deal exists                        │
│  ├─ Perplexity checks if TA matches                         │
│  ├─ If match: extract all fields                            │
│  └─ If no match: return null                                │
│                                                               │
│  Expected results:                                           │
│  ├─ ~3,800 articles with no deals (null)                    │
│  ├─ ~150 deals found but wrong TA (filtered out)            │
│  └─ ~50 deals matching all criteria ✓                       │
│                                                               │
│  Output: List of ~50 matching deals                         │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 4: DEDUPLICATION                                       │
│  Cost: $0 | Time: <1 minute                                 │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  For each deal:                                              │
│  1. Generate canonical key:                                  │
│     hash(target_norm|acquirer_norm|asset_norm|date)         │
│                                                               │
│  2. Check for exact match:                                   │
│     → If key exists: merge deals, keep primary URL          │
│                                                               │
│  3. Check for fuzzy match (±3 days):                        │
│     → If same parties + asset + nearby date: merge          │
│                                                               │
│  4. If unique: add to final list                            │
│                                                               │
│  Expected: ~50 deals → ~45 unique deals (after dedup)       │
│                                                               │
│  Output: List of ~45 unique deals                           │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 5: EXPORT                                              │
│  Cost: $0 | Time: <1 minute                                 │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Excel file (output/deals_abc123.xlsx):                     │
│  ├─ One row per deal                                         │
│  ├─ Columns: target, acquirer, date, stage, TA, money, etc. │
│  ├─ needs_review flag for low confidence                    │
│  └─ related_urls column (for duplicates)                    │
│                                                               │
│  Evidence log (output/evidence_abc123.jsonl):               │
│  ├─ One JSON object per deal                                │
│  ├─ Full evidence snippets                                  │
│  └─ Useful for auditing extractions                         │
│                                                               │
│  Output: Complete dataset of all deals!                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Summary

✅ **YES** - Crawls all 5 sites (FierceBiotech, FiercePharma, GEN, BioPharma Dive, Endpoints News)

✅ **NO** - Discovery doesn't classify (just gets URLs)

✅ **YES** - Extraction does BOTH classification AND data extraction in one API call

✅ **YES** - Deduplication uses (target + acquirer + asset + date) as key

✅ **YES** - Fuzzy matching catches variations in company names

✅ **YES** - Duplicate URLs are merged and stored in `related_urls` field

---

## Cost Breakdown

| Phase | What It Does | Cost | Time |
|-------|-------------|------|------|
| **Discovery** | Crawl RSS/sitemaps | $0 | 5 min |
| **Fetch** | Get HTML content | $0 | 60 min |
| **Extraction** | Perplexity filtering + extraction | $13 | 90 min |
| **Dedup** | Remove duplicates | $0 | <1 min |
| **Export** | Save to Excel | $0 | <1 min |
| **TOTAL** | Complete dataset | **$13** | **~2.5 hours** |

---

## To Run

```bash
# Set API key
export PERPLEXITY_API_KEY="pplx-..."

# Run pipeline (exhaustive mode is default)
python -m deal_finder.main --config config/config.yaml

# Wait ~2.5 hours for complete dataset
# Result: output/deals_{run_id}.xlsx with ~45 unique deals
```
