# Prompts and Filters Location Guide

## Where Everything Is Located

### 1. **Prompts**

#### Quick Filter Prompt (Pass 1)
**File**: `deal_finder/extraction/openai_extractor.py`
**Lines**: 315-335
**Model**: gpt-4o-mini (cheap, fast)
**Purpose**: Quick filter to reject obvious non-deals

**Key rejection criteria:**
- Compilations/roundups
- Financings, IPOs, fundraising
- Pre-2021 articles
- Wrong TA or stage
- Clinical trial results, regulatory news

#### Full Extraction Prompt (Pass 2)
**File**: `deal_finder/extraction/openai_extractor.py`
**Lines**: 491-540
**Model**: gpt-4o (high quality)
**Purpose**: Extract structured deal data from articles that passed quick filter

**Extracts:**
- Companies (acquirer, target)
- Deal type (M&A, partnership, licensing, option-to-license)
- Financials (upfront, milestones, total)
- Stage, asset focus, geography, confidence

---

### 2. **Filtering Pipeline**

#### Step 1: Dual Embedding Filter
**File**: `deal_finder/storage/article_cache_chroma.py`
**Method**: `search_articles_dual_filter()` (lines 164-226)
**Cost**: FREE (local embeddings)
**Process**:
1. Query 1: TA relevance ("immunology therapy treatment drug...")
2. Query 2: Deal relevance ("acquisition merger partnership licensing...")
3. Intersection: Keep only articles in BOTH top results
4. Result: ~20K articles → filters down significantly

#### Step 2: URL Pattern + Date Filtering
**File**: `run_pipeline.py`
**Lines**: 77-122
**Cost**: FREE (regex + string comparison)
**Rejects**:
- Bad URL patterns: `/financings`, `/roundup`, `/earnings`, etc.
- Compilation URLs: `collaborations-agreements-2008`
- Bad/missing dates
- Pre-2021 dates

**Result**: ~20K → ~2-5K articles

#### Step 3: Top 1K by Similarity
**File**: `run_pipeline.py`
**Line**: 121
**Process**: Take top 1000 articles by embedding similarity score
**Result**: 2-5K → 1K articles (highest quality)

#### Step 4: OpenAI Quick Filter
**File**: `deal_finder/extraction/openai_extractor.py`
**Method**: `_quick_filter()` (lines 294-386)
**Cost**: ~$1-2 (gpt-4o-mini on 1K articles)
**Process**: Batch of 40 articles per API call
**Result**: 1K → ~200-400 articles

#### Step 5: Deduplication
**File**: `deal_finder/extraction/openai_extractor.py`
**Method**: `deduplicate_by_title()` (lines 17-105)
**Cost**: FREE (local sentence-transformers)
**Process**: Semantic similarity >0.85 = duplicates
**Result**: 200-400 → ~150-300 unique articles

#### Step 6: OpenAI Full Extraction
**File**: `deal_finder/extraction/openai_extractor.py`
**Method**: `_extract_batch_structured()` (lines 472-595)
**Cost**: ~$5-10 (gpt-4o on 150-300 articles)
**Process**: Batch of 20 articles per API call
**Result**: 150-300 → ~40-100 valid deals

---

### 3. **Configuration**

#### URL Rejection Patterns
**File**: `run_pipeline.py`
**Lines**: 79-94
**Edit here to add/remove URL patterns**

```python
reject_patterns = [
    r'/financings?(-roundup)?/?$',
    r'/appointments-and-advancements',
    # Add more patterns here...
]
```

#### Date Range
**File**: `config/config.yaml`
**Line**: 7
```yaml
START_DATE: "2021-01-01"  # Change this to adjust date filter
```

#### Embedding Similarity Threshold
**File**: `run_pipeline.py`
**Line**: 72
```python
similarity_threshold=0.20  # Lower = more results, higher = more strict
```

#### Top-K Limit
**File**: `run_pipeline.py`
**Line**: 121
```python
articles = articles[:1000]  # Change 1000 to adjust limit
```

---

### 4. **Cost Breakdown**

| Step | Cost | Articles |
|------|------|----------|
| 1. Dual Embedding | $0 | 705K → 20K |
| 2. URL + Date Filter | $0 | 20K → 2-5K |
| 3. Top 1K | $0 | 2-5K → 1K |
| 4. Quick Filter | $1-2 | 1K → 200-400 |
| 5. Dedup | $0 | 200-400 → 150-300 |
| 6. Full Extraction | $5-10 | 150-300 → 40-100 |
| **TOTAL** | **$6-12** | **40-100 deals** |

---

### 5. **How to Modify**

#### To make filtering MORE strict:
1. Increase similarity threshold (line 72): `0.20` → `0.25`
2. Reduce top-K limit (line 121): `1000` → `500`
3. Add more URL patterns (lines 79-94)

#### To make filtering LESS strict:
1. Decrease similarity threshold (line 72): `0.20` → `0.15`
2. Increase top-K limit (line 121): `1000` → `2000`
3. Remove some URL patterns (lines 79-94)

#### To adjust prompts:
- Quick filter: `deal_finder/extraction/openai_extractor.py` lines 315-335
- Full extraction: `deal_finder/extraction/openai_extractor.py` lines 491-540

---

### 6. **Order Summary**

```
705K Embeddings
    ↓
Dual Embedding Filter (TA + Deal)
    ↓ (~20K)
URL Pattern + Date Filter
    ↓ (~2-5K)
Top 1K by Similarity
    ↓ (1K)
OpenAI Quick Filter ($1-2)
    ↓ (~200-400)
Deduplication (FREE)
    ↓ (~150-300)
OpenAI Full Extraction ($5-10)
    ↓ (~40-100)
Final Deals
```

---

**Key Files:**
- Prompts: `deal_finder/extraction/openai_extractor.py`
- Dual filter: `deal_finder/storage/article_cache_chroma.py`
- URL/Date filter: `run_pipeline.py`
- Config: `config/config.yaml`
