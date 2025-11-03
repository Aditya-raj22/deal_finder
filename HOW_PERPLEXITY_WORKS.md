# How Perplexity Works in This Pipeline

## The Confusion: Discovery vs Extraction

You asked: *"Does Perplexity go through the link, see the data, and if it fits, return the link?"*

**Answer: NO!** That's not how we're using it. Let me clarify:

## Two Different Approaches

### ❌ Approach 1: Perplexity Search (Not Recommended)

```
You → Perplexity: "Find oncology acquisitions"
         ↓
Perplexity searches the web
         ↓
Perplexity returns: ["link1", "link2", ...]
         ↓
You fetch each link separately
         ↓
You extract deal data
```

**Problem:** Perplexity only returns links it THINKS match your keywords. You miss deals with different wording.

### ✅ Approach 2: Exhaustive Crawl + Perplexity Extraction (RECOMMENDED - DEFAULT)

```
You → Get ALL links from FierceBiotech RSS
         ↓
You have 1,000 article links
         ↓
You fetch article HTML for all 1,000 links
         ↓
You send articles in batches to Perplexity:
  "Here are 5 articles. Extract any deals."
         ↓
Perplexity reads each article's content
         ↓
Perplexity returns deal data (or null if no deal)
         ↓
You filter for matching deals
```

**This is what we're doing!** Perplexity is reading content, not searching.

## Step-by-Step Example

### Step 1: Get ALL Links from Site
```bash
# Exhaustive crawler fetches FierceBiotech RSS
RSS Feed → 1,000 article URLs

Example URLs:
- https://www.fiercebiotech.com/article1
- https://www.fiercebiotech.com/article2
- https://www.fiercebiotech.com/article3
- ... (997 more)
```

**Key:** We get EVERY article, not just deal articles. This ensures completeness.

### Step 2: Fetch HTML for Each Article
```bash
# Selenium/Requests fetches HTML
URL → HTML content → Text extraction

Example for article1:
Title: "Pfizer Acquires Arena Pharmaceuticals"
Content: "NEW YORK, Dec 13 2021 - Pfizer Inc. announced today
         that it has completed the acquisition of Arena
         Pharmaceuticals for $6.7 billion. The deal includes..."
```

### Step 3: Batch Send to Perplexity for Extraction
```python
# Batch of 5 articles sent to Perplexity
articles = [
    {"url": "article1", "content": "Pfizer acquires Arena..."},
    {"url": "article2", "content": "Stock market update..."},
    {"url": "article3", "content": "Gilead licenses from Arcus..."},
    {"url": "article4", "content": "FDA approves new drug..."},
    {"url": "article5", "content": "BMS partners with IFM..."},
]

# Perplexity prompt:
"""
Read these 5 articles. For EACH article:
1. Is there a deal? (M&A, partnership, licensing)
2. If yes, extract: parties, money, stage, therapeutic area
3. If no, return null

Return JSON array with 5 objects (one per article).
"""

# Perplexity response:
[
  {  # article1
    "article_index": 1,
    "url": "article1",
    "parties": {"acquirer": "Pfizer", "target": "Arena"},
    "deal_type": "M&A",
    "money": {"total_deal_value": 6700000000, "currency": "USD"},
    "stage": "phase 3",
    "therapeutic_area_match": true,
    ...
  },
  {  # article2 - no deal
    "article_index": 2,
    "url": "article2",
    "parties": null,
    "deal_type": null,
    ...
  },
  {  # article3
    "article_index": 3,
    "url": "article3",
    "parties": {"partner1": "Gilead", "partner2": "Arcus"},
    "deal_type": "licensing",
    "money": {"upfront_value": 375000000, "currency": "USD"},
    "stage": "preclinical",
    "therapeutic_area_match": true,
    ...
  },
  {  # article4 - no deal
    "article_index": 4,
    "url": "article4",
    "parties": null,
    "deal_type": null,
    ...
  },
  {  # article5
    "article_index": 5,
    "url": "article5",
    "parties": {"partner1": "BMS", "partner2": "IFM"},
    "deal_type": "partnership",
    "money": {"total_deal_value": 2300000000, "currency": "USD"},
    "stage": "preclinical",
    "therapeutic_area_match": true,
    ...
  }
]
```

**Key:** Perplexity reads the FULL content of each article and extracts structured data. Articles without deals return null.

### Step 4: Filter and Save
```python
# Filter for valid deals
deals = [
    article1_deal,  # Pfizer + Arena
    article3_deal,  # Gilead + Arcus
    article5_deal,  # BMS + IFM
]

# Save to Excel
output/deals_abc123.xlsx
```

## Why This Approach is Better

### Old Way (Regex Patterns)
```python
# Regex pattern
r"([A-Z][A-Za-z0-9]+) acquires ([A-Z][A-Za-z0-9]+)"

# Works for:
"Pfizer acquires Arena"

# Fails for:
"Pfizer Inc. announced the completion of its acquisition of Arena Pharmaceuticals"
"Arena Pharmaceuticals to be acquired by Pfizer"
"Pfizer completes Arena deal"
```

**Problem:** Rigid patterns miss variations.

### New Way (Perplexity LLM)
```python
# Perplexity understands:
- "Pfizer acquires Arena"
- "Arena acquired by Pfizer"
- "Pfizer completes acquisition of Arena"
- "Arena deal with Pfizer finalized"
- "Pfizer announces Arena purchase"

# All extract as:
{"acquirer": "Pfizer", "target": "Arena", "deal_type": "M&A"}
```

**Advantage:** Context understanding handles all variations.

## Credits Usage

### Discovery (FREE)
```
RSS feeds from FierceBiotech, FiercePharma, etc.
Cost: $0
Perplexity credits used: 0
```

### Extraction (PAID)
```
4,000 articles ÷ 5 per batch = 800 API calls

Each API call:
- Input: 5 articles × 3k tokens each = 15k tokens
- Output: JSON response = ~2k tokens
- Total: ~17k tokens per call

800 calls × 17k tokens = 13.6M tokens
13.6M tokens × $1/1M = $13.60

Total cost: ~$13.60 for complete dataset
```

## Key Takeaways

1. **Perplexity is NOT doing the discovery** (finding links)
   - We get links from RSS feeds (free)
   - We crawl ALL articles from trusted sites

2. **Perplexity IS doing the extraction** (reading content)
   - We send article text to Perplexity
   - Perplexity extracts deal data
   - Perplexity filters for matching criteria

3. **Credits are ONLY used for extraction**
   - Discovery is free (RSS/sitemaps)
   - Extraction costs ~$13.60 per full run
   - This gives you COMPLETE dataset

4. **The goal is completeness**
   - Get EVERY article from trusted sources
   - Let Perplexity find the deals
   - Build comprehensive dataset

## Comparison Table

| Task | What We Do | Who Does It | Cost |
|------|-----------|-------------|------|
| **Find article URLs** | Crawl RSS/sitemaps | Exhaustive crawler | $0 |
| **Fetch article HTML** | HTTP requests | Selenium/Requests | $0 |
| **Read article content** | Send to LLM | Perplexity API | $13.60 |
| **Extract deal data** | LLM extraction | Perplexity API | (included) |
| **Filter for matches** | LLM filtering | Perplexity API | (included) |
| **Deduplicate** | Python logic | Our code | $0 |
| **Export to Excel** | Python logic | Our code | $0 |

## Your Specific Question

> "so u'r saying that the api call will go through the link, see the data, if data fits only returns link (to save credits)"

**Answer:** Not quite! Here's what actually happens:

1. **We get the links** (RSS feeds, no Perplexity)
2. **We fetch the content** (HTTP requests, no Perplexity)
3. **We send content to Perplexity** (this uses credits)
4. **Perplexity extracts deal data** (this uses credits)
5. **Perplexity returns structured data** (not just the link)

Perplexity is NOT "going through links" - we're sending it the article text directly.

## To Maximize Link Coverage

> "I want to focus the api calls on those websites, and see if we can make sure that it looks through every single link on that website eg. FiercePharma"

**Good news:** That's exactly what the exhaustive crawler does!

```python
# In exhaustive_crawler.py
PRIORITY_SITES = {
    'FiercePharma': {
        'rss_feeds': [
            'https://www.fiercepharma.com/rss/xml',      # Main feed
            'https://www.fiercepharma.com/m-a/rss',      # M&A feed
            'https://www.fiercepharma.com/partnering/rss', # Partnering feed
        ],
        'sitemap': 'https://www.fiercepharma.com/sitemap.xml',  # ALL articles
    }
}
```

This gets:
- ALL articles from main RSS
- ALL articles from M&A RSS
- ALL articles from partnering RSS
- ALL articles from XML sitemap

Result: **EVERY article from FiercePharma** in your date range!

Then Perplexity reads each one and extracts deals.
