# Incremental Crawling Strategy

## Overview

The pipeline now uses **index-based incremental crawling** to avoid reprocessing articles you've already seen.

## How It Works

### Initial Run (Complete Historical Crawl)

```
Step 1: Crawl ALL sitemaps/archives from all 5 sites
├─ FierceBiotech sitemap → 15,000 URLs (entire history)
├─ FiercePharma sitemap → 12,000 URLs
├─ GEN sitemap → 18,000 URLs
├─ BioPharma Dive sitemap → 8,000 URLs
└─ Endpoints News sitemap → 5,000 URLs
Total: 58,000 URLs (all time)

Step 2: Filter by date range (2021-01-01 to today)
Result: 4,000 URLs in your date range

Step 3: Fetch content + Perplexity extraction
Result: ~50 deals found

Step 4: Save URL index
output/url_index.json: 4,000 URLs marked as "crawled"
```

### Incremental Runs (Only New Articles)

```
Step 1: Load existing URL index
output/url_index.json: 4,000 URLs already crawled

Step 2: Crawl ALL sitemaps/archives again
Result: 58,500 URLs (500 new articles since last run)

Step 3: Filter for NEW URLs only
4,000 already crawled → skip
500 new URLs → process these

Step 4: Fetch + extract only new articles
Result: ~5-10 new deals

Step 5: Update URL index
output/url_index.json: now 4,500 URLs marked as "crawled"
```

## Key Benefits

### 1. No Wasted API Calls
**Before (quarterly approach):**
- Run 1 (Q1 2024): Process 4,000 articles → $13
- Run 2 (Q2 2024): Process 4,000 articles again (many duplicates) → $13
- Run 3 (Q3 2024): Process 4,000 articles again → $13
- **Total: $39 with massive duplication**

**After (index-based):**
- Run 1 (Initial): Process 4,000 articles → $13
- Run 2 (1 month later): Process 500 new articles only → $1.60
- Run 3 (1 month later): Process 450 new articles only → $1.45
- **Total: $16.05 for same coverage**

**Savings: 60% reduction in API costs**

### 2. No Date Range Manipulation Needed
- Don't need to track "last run date"
- Don't need to update START_DATE config
- Just run whenever you want - it automatically finds new articles

### 3. Complete Coverage Guaranteed
- First run gets EVERYTHING in your date range
- Subsequent runs get EVERYTHING new since last run
- Never miss an article

## Architecture Changes

### Discovery Phase

**Old Approach:**
```python
# Get articles in date range
articles = crawler.get_articles(from_date="2024-01-01", to_date="2024-12-31")
# Process all 4,000 articles every time
```

**New Approach:**
```python
# Get ALL articles from sitemap (ignoring date range initially)
all_articles = crawler.get_all_articles()  # 58,000 URLs

# Filter by date range
articles = [a for a in all_articles if from_date <= a.date <= to_date]  # 4,000 URLs

# Filter for NEW URLs only (index-based)
new_articles = [a for a in articles if not url_index.is_crawled(a.url)]  # 500 URLs

# Process only new articles
```

## URL Index Format

`output/url_index.json`:
```json
{
  "crawled_urls": [
    "https://www.fiercebiotech.com/article1",
    "https://www.fiercepharma.com/article2",
    ...
  ],
  "url_metadata": {
    "https://www.fiercebiotech.com/article1": {
      "source": "FierceBiotech",
      "published_date": "2024-01-15",
      "crawled_at": "2024-01-20T10:30:00Z"
    },
    ...
  },
  "last_updated": "2024-01-20T10:35:00Z"
}
```

## Configuration

### Enable Incremental Crawling (Default)

```python
# In crawler.py initialization:
self.exhaustive_crawler = ExhaustiveSiteCrawler(
    from_date=config.START_DATE,
    to_date=config.end_date_resolved,
    use_index=True  # Default - enables incremental crawling
)
```

### Disable for Full Recrawl

```python
# Force recrawl of all articles (ignores index)
self.exhaustive_crawler = ExhaustiveSiteCrawler(
    from_date=config.START_DATE,
    to_date=config.end_date_resolved,
    use_index=False  # Disables index, processes everything
)
```

## Usage Patterns

### Pattern 1: Complete Historical Dataset (One-Time)

```bash
# First run - gets EVERYTHING in date range
python -m deal_finder.main --config config/config.yaml

# Result:
# - Processes 4,000 articles
# - Finds ~50 deals
# - Costs ~$13
# - Creates output/url_index.json with 4,000 URLs
```

### Pattern 2: Daily Updates (Incremental)

```bash
# Run daily to catch new articles
python -m deal_finder.main --config config/config.yaml

# Day 1: 0 new articles → $0
# Day 2: 5 new articles → $0.02
# Day 3: 12 new articles → $0.04
# ...
# Total for month: ~500 new articles → ~$1.60
```

### Pattern 3: Weekly Updates (Recommended)

```bash
# Run weekly (every Monday)
python -m deal_finder.main --config config/config.yaml

# Week 1: 100 new articles → $0.32
# Week 2: 125 new articles → $0.40
# Week 3: 110 new articles → $0.35
# Week 4: 115 new articles → $0.37
# Total for month: ~450 new articles → ~$1.45
```

### Pattern 4: Reset Index (Force Recrawl)

```bash
# Delete index to force complete recrawl
rm output/url_index.json

python -m deal_finder.main --config config/config.yaml

# Processes ALL articles again (useful if you change extraction logic)
```

## Crawling Strategy Comparison

| Strategy | Initial Run | Subsequent Runs | Cost/Month | Coverage |
|----------|-------------|-----------------|------------|----------|
| **Quarterly (Old)** | 4,000 articles | 4,000 articles (duplicates) | $39 | Gaps between quarters |
| **Weekly + Index (New)** | 4,000 articles | ~450 new articles | $14.45 | Complete |
| **Daily + Index (Overkill)** | 4,000 articles | ~500 new articles total | $13.50 | Complete |

## Advanced: Custom Index Path

```python
# Store index in custom location
from pathlib import Path

crawler = ExhaustiveSiteCrawler(
    from_date="2021-01-01",
    to_date="2024-12-31",
    use_index=True,
    index_path=Path("/custom/path/my_index.json")
)
```

## Index Management Commands

### View Index Stats

```python
from deal_finder.discovery.url_index import URLIndex

index = URLIndex()
stats = index.get_stats()
print(stats)

# Output:
# {
#   'total_urls_crawled': 4523,
#   'by_source': {
#     'FierceBiotech': 1205,
#     'FiercePharma': 982,
#     'GEN': 1456,
#     'BioPharma Dive': 567,
#     'Endpoints News': 313
#   },
#   'index_path': 'output/url_index.json'
# }
```

### Reset Index

```python
from deal_finder.discovery.url_index import URLIndex

index = URLIndex()
index.reset()
index.save()

# Or just delete the file:
# rm output/url_index.json
```

## Sitemap vs RSS vs Archive

### Sitemap (PRIMARY - Most Complete)
```
✓ Contains ALL articles ever published
✓ Updated regularly by site
✓ Fast to fetch (XML format)
✓ Has last modified dates
✗ May not have article metadata

Example: 58,000 total URLs, filtered to 4,000 in date range
```

### Archive Pages (SUPPLEMENTAL)
```
✓ Complete historical coverage
✓ Can extract article titles/dates
✗ Slower (HTML parsing)
✗ Need to fetch monthly pages

Example: Fetch 48 monthly archive pages (2021-2024)
```

### RSS Feeds (FALLBACK ONLY)
```
✗ Only recent articles (~100-500)
✗ Limited historical data
✓ Fast to fetch
✓ Has article metadata

Only used if sitemap AND archive fail
```

## Recommended Workflow

### Initial Setup (Once)
```bash
# Set date range for complete historical dataset
# config/config.yaml:
START_DATE: "2021-01-01"
END_DATE: null  # null = today

# Run initial crawl
python -m deal_finder.main --config config/config.yaml

# Wait 2-3 hours
# Result: Complete dataset + URL index
```

### Ongoing Updates (Weekly)
```bash
# Same config - don't change START_DATE!
# config/config.yaml:
START_DATE: "2021-01-01"  # Keep same
END_DATE: null

# Run weekly update
python -m deal_finder.main --config config/config.yaml

# Wait 5-10 minutes (only processes new articles)
# Result: New deals + updated index
```

## Key Insights

1. **No need to update START_DATE** - Index tracks what's already been processed
2. **Always crawl complete sitemaps** - Then filter for new URLs
3. **Incremental runs are cheap** - Only pay for new articles
4. **Complete coverage guaranteed** - Never miss an article
5. **Weekly runs recommended** - Good balance of freshness and cost

## Summary

✅ **Removed:** 10 sub-sitemap limit (now crawls ALL)
✅ **Changed:** Sitemap is primary source, RSS is fallback
✅ **Added:** Archive page scraping for extra coverage
✅ **Removed:** Google News (redundant and unreliable)
✅ **Added:** URL index for incremental crawling
✅ **Result:** Complete dataset with minimal ongoing costs
