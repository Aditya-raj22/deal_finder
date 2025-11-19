# Pipeline Flow - Deal Finder

## Overview
This document explains how the deal finder pipeline uses your 705K embedded articles to extract biotech deals.

## Architecture: Embedding Search + OpenAI Validation

### ✅ What Uses Embedding Search (Fast & Cheap)
1. **Therapeutic Area Filter** - Semantic similarity search in ChromaDB
2. **Deal-Related Filter** - Enhanced query with deal keywords
3. **Date Filter** - Post-2021 metadata filter (exact)
4. **Source Filter** - Metadata filter by news source

**Result**: ~1,000-5,000 relevant articles from 705K total

### ✅ What Uses OpenAI (Precise Extraction)
1. **Deal Type Validation** - Confirm it's M&A/partnership/licensing/option-to-license
2. **Stage Classification** - Extract development stage (preclinical, Phase 1-3, etc.)
3. **TA Reinforcement** - Confirm therapeutic area match
4. **Financial Extraction** - Extract upfront, milestones, total value
5. **Company Extraction** - Extract acquirer and target

**Result**: High-precision deals with structured data

---

## Step-by-Step Flow

### User Submits Search via UI
```
Input:
- Therapeutic Area: "oncology"
- Date Range: 2021-01-01 to today
- Sources: ["STAT", "Endpoints News", "BioWorld"]
- Stages: ["preclinical", "phase 1"]
```

### STEP 1: ChromaDB Semantic Search (Instant)
```python
# run_pipeline.py:38-60

# Build enhanced query
query = "oncology deals partnerships acquisitions M&A licensing transactions agreements biotech pharma financial"

# Search 705K embedded articles
articles = chromadb.search_articles_semantic(
    query=query,
    start_date="2021-01-01",
    end_date=today,
    sources=["STAT", "Endpoints News", "BioWorld"],
    similarity_threshold=0.20,  # Low = high recall
    top_k=50000  # No practical limit
)

# Result: ~2,000 oncology deal-related articles
```

**Speed**: <1 second (vector similarity search is instant)
**Cost**: $0 (uses pre-computed embeddings)

---

### STEP 2: OpenAI Quick Filter (2-5 min)
```python
# openai_extractor.py:294-386

# Pass 1: Quick filter using GPT-4.1-nano (cheap, fast)
# Processes in batches of 40 articles
# Uses first 1000 chars only

prompt = """
Determine if this is a BIOTECH DEAL in oncology.

PASS if ALL:
1. M&A/partnership/licensing/option-to-license
2. Related to oncology
3. Stage is preclinical or phase 1

REJECT if ANY:
- Not a deal (clinical results, regulatory approval, news, opinion)
- Not biotech deal type (fundraising, IPO, equity investment)
- Wrong stage (phase 2, phase 3, etc.)
- Wrong TA
"""

# Result: ~500 articles pass quick filter
```

**Speed**: 2-5 minutes
**Cost**: ~$0.50 (nano model is cheap)

---

### STEP 3: Deduplication (1-2 min)
```python
# openai_extractor.py:17-105

# Semantic deduplication using all-mpnet-base-v2
# Removes duplicate articles (>0.85 similarity)
# Keeps longest version of each duplicate group

# Result: ~400 unique articles after dedup
```

**Speed**: 1-2 minutes
**Cost**: $0 (local embedding model)

---

### STEP 4: OpenAI Full Extraction (10-30 min)
```python
# openai_extractor.py:388-595

# Pass 2: Full extraction using GPT-4.1 (best quality)
# Processes in batches of 20 articles
# Uses first 10K chars for full context

prompt = """
Extract oncology-related BIOTECH DEAL information.

CRITICAL DEAL TYPE VALIDATION:
- ONLY extract: M&A, partnership, licensing, option-to-license
- REJECT: fundraising, IPO, clinical trials, regulatory approvals

Extract:
- Companies (acquirer, target)
- Deal type
- Financials (upfront, milestones, total)
- Asset focus (drug/therapy name)
- Stage (preclinical, phase 1, etc.)
- Date announced
- Geography
"""

# Result: ~300 valid deals extracted
```

**Speed**: 10-30 minutes (depends on article count)
**Cost**: ~$5-15 (GPT-4.1 on 400 articles × 10K chars)

---

### STEP 5: Split by Stage & Export (Instant)
```python
# run_pipeline.py:161-199

# Split deals into 3 groups
early_stages = filter_by_stage(deals, ["preclinical", "phase 1", "first-in-human"])
mid_stages = filter_by_stage(deals, ["phase 2", "phase 3"])
undisclosed = filter_by_stage(deals, ["unknown", "undisclosed"])

# Export to 3 Excel files
ExcelWriter().write(early_stages, "deals_oncology_EARLY_STAGE_20251119.xlsx")
ExcelWriter().write(mid_stages, "deals_oncology_MID_STAGE_20251119.xlsx")
ExcelWriter().write(undisclosed, "deals_oncology_UNDISCLOSED_20251119.xlsx")
```

**Speed**: <1 second
**Cost**: $0

---

## Summary

| Step | What Happens | Speed | Cost | Output |
|------|-------------|-------|------|--------|
| 1. Semantic Search | ChromaDB vector search on 705K articles | <1s | $0 | ~2K articles |
| 2. Quick Filter | GPT-4.1-nano validates deal + TA + stage | 2-5m | $0.50 | ~500 articles |
| 3. Deduplication | Semantic dedup with embeddings | 1-2m | $0 | ~400 articles |
| 4. Full Extraction | GPT-4.1 extracts deal details | 10-30m | $5-15 | ~300 deals |
| 5. Export | Split by stage, write 3 Excel files | <1s | $0 | 3 files |

**Total Time**: 15-40 minutes
**Total Cost**: $5-16 per search

---

## Key Filters

### Embedding Search Handles:
- ✅ Therapeutic Area matching (semantic similarity)
- ✅ Deal-related content (enhanced query)
- ✅ Date range (post-2021 metadata filter)
- ✅ Source filtering (metadata filter)

### OpenAI Reinforces:
- ✅ Biotech deal type validation (M&A/partnership/licensing only)
- ✅ Stage classification (preclinical, Phase 1-3)
- ✅ TA confirmation (reject off-topic)
- ✅ Financial extraction (upfront, milestones, total)
- ✅ Company extraction (acquirer, target)

---

## Output Files

### File 1: `deals_{TA}_EARLY_STAGE_{timestamp}.xlsx`
- Preclinical, Phase 1, First-in-Human, Discovery
- Not yet started Phase 2

### File 2: `deals_{TA}_MID_STAGE_{timestamp}.xlsx`
- Phase 2, Phase 3

### File 3: `deals_{TA}_UNDISCLOSED_{timestamp}.xlsx`
- Unknown stage, Undisclosed, Clinical (unspecified)

---

## Why This Architecture Works

1. **High Recall**: Embedding search with 0.20 threshold catches all relevant deals
2. **High Precision**: OpenAI validates deal type and extracts structured data
3. **Cost Efficient**: Only send filtered articles to OpenAI (not all 705K!)
4. **Fast**: Vector search is instant, total pipeline runs in 15-40 minutes
5. **Checkpoints**: Can resume if interrupted at any stage
6. **Post-2021**: Date filter ensures recent deals only
7. **Deal Focus**: Rejects fundraising, IPOs, clinical results, regulatory approvals
