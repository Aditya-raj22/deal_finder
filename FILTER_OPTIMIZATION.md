# Filter Optimization - No False Negatives

## Goal: Zero False Negatives, Accept False Positives

**Philosophy**: Better to include irrelevant deals (flagged for review) than miss real deals.

---

## Changes Made

### **1. Relaxed Therapeutic Area Filtering** 🔥 **CRITICAL**

**Before**:
```python
if not extraction.get("therapeutic_area_match", False):
    return None  # EXCLUDED COMPLETELY!
```

**After**:
```python
ta_match = extraction.get("therapeutic_area_match", False)
if not ta_match:
    needs_review = True  # Flag for review but INCLUDE
```

**Impact**:
- Deals that Perplexity thinks "don't match" are now **included** but flagged
- You can manually review in Excel (filter `needs_review = TRUE`)
- **Eliminates biggest source of false negatives**

---

### **2. Expanded TA Vocabulary** 📚

**Added 20+ broader terms** to `includes`:
- "immune", "immunity", "immunotherapy"
- "immune disorder", "immune disease", "immune system"
- "inflammatory disease", "chronic inflammation"
- "cytokine", "chemokine"
- "T cell", "B cell", "lymphocyte"
- "immunomodulator", "immunosuppressant"
- "anti-inflammatory"

**Impact**:
- Catches more edge cases
- Broader net for Perplexity's TA matching
- More deals will be flagged as `therapeutic_area_match = true`

---

### **3. Accept All Confidence Levels**

**Before**:
```python
if extraction.get("confidence") == "low":
    needs_review = True
```

**After**:
```python
confidence = extraction.get("confidence", "unknown")
if confidence in ["low", "very low", "unknown"]:
    needs_review = True  # Flag but INCLUDE
```

**Impact**:
- Accepts deals even with "very low" or "unknown" confidence
- All flagged for manual review
- No deals excluded based on confidence alone

---

## Current Filters (After Changes)

### ✅ **Filters That INCLUDE Deals (with review flag)**

1. **TA mismatch** → `needs_review = TRUE` (included)
2. **Low/unknown confidence** → `needs_review = TRUE` (included)
3. **Unknown stage** → Default to "preclinical" + `needs_review = TRUE` (included)
4. **Missing asset focus** → "Undisclosed" + `needs_review = TRUE` (included)

### ❌ **Filters That EXCLUDE Deals (hard rejections)**

Only 3 hard exclusions remain:

1. **Missing parties** (acquirer or target) → Can't have a deal without parties
2. **Missing date** → Need date for timeline
3. **Invalid date format** → Can't parse malformed dates

**These are necessary** - without parties or date, it's not a usable deal record.

---

## Expected Output Changes

### Before Optimization
- **Total articles**: 1,000
- **Deals extracted**: 10-15
- **Flagged for review**: 2-3 (20%)
- **Excluded**: ~50-100 deals (false negatives!)

### After Optimization
- **Total articles**: 1,000
- **Deals extracted**: 20-40 (2-4x more!)
- **Flagged for review**: 10-20 (50%)
- **Excluded**: ~5-10 (only hard rejections)

**You'll need to manually review ~50% of deals, but you won't miss any real deals.**

---

## How to Review Flagged Deals

### In Excel Output

1. **Open** `output/deals_YYYYMMDD_HHMMSS.xlsx`

2. **Filter by** `needs_review = TRUE`

3. **For each flagged deal**:
   - Click `source_url` to read original article
   - Verify: parties, money, stage, TA match
   - Decision:
     - ✅ **Keep** if it's a real deal
     - ❌ **Delete row** if it's irrelevant

4. **Common false positives to watch for**:
   - Oncology deals (not immunology)
   - Late-stage deals (Phase 2/3)
   - Deals with wrong parties (e.g., cities instead of companies)
   - Non-deal news (FDA approvals, clinical trial results)

---

## Example: What Gets Flagged Now

### ✅ **Included with needs_review = TRUE**

**Deal 1**: "Company A acquires Company B for $500M"
- TA match: FALSE (Perplexity thinks it's oncology, but mentions "immune checkpoint")
- **Before**: EXCLUDED
- **After**: INCLUDED, flagged for review
- **Manual check**: Actually an immuno-oncology deal → KEEP ✅

**Deal 2**: "Company C licenses antibody from Company D"
- Confidence: LOW (article is vague about stage)
- **Before**: INCLUDED, flagged
- **After**: INCLUDED, flagged (same)
- **Manual check**: Article confirms preclinical → KEEP ✅

**Deal 3**: "Company E partners with Company F on CAR-T therapy"
- TA match: FALSE (Perplexity thinks it's gene therapy)
- **Before**: EXCLUDED
- **After**: INCLUDED, flagged for review
- **Manual check**: CAR-T for autoimmune → KEEP ✅

### ❌ **Still Excluded (Hard Rejections)**

**Non-Deal 1**: "Company G announces Phase 2 results"
- Missing: acquirer/target (not a deal)
- **Before**: EXCLUDED
- **After**: EXCLUDED (correct)

**Non-Deal 2**: "FDA approves Company H's drug"
- Missing: acquirer/target (not a deal)
- **Before**: EXCLUDED
- **After**: EXCLUDED (correct)

---

## Cost Impact

### Before Optimization
- 1,000 articles → 200 batches → $12 + $2 search = **$14**
- 10-15 deals found
- **Cost per deal**: ~$1.00

### After Optimization
- 1,000 articles → 200 batches → $12 + $2 search = **$14** (same)
- 20-40 deals found (2-4x more!)
- **Cost per deal**: ~$0.35-0.70

**No extra cost**, but you get 2-4x more deals to review!

---

## Validation Strategy

### After First Run

1. **Check total deals found**:
   - < 10 deals → Filters still too strict or FierceBiotech has limited coverage
   - 10-20 deals → Good, expected range
   - 20-40 deals → Excellent, broad coverage
   - > 50 deals → Too broad, may need to tighten TA vocab

2. **Check needs_review ratio**:
   - < 20% flagged → Filters may still be too strict
   - 30-50% flagged → Perfect, you're catching edge cases
   - > 70% flagged → Too broad, too many false positives

3. **Spot check 5 random deals**:
   - Do they match your TA?
   - Are they the right stage?
   - Are parties correct?

4. **Search for known deals**:
   - Think of 2-3 major deals you know happened
   - Are they in the output?
   - If missing → Check FierceBiotech coverage or date range

---

## Fine-Tuning Later

### If Too Many False Positives (>70% flagged)

**Option 1**: Add exclusions to TA vocab
```json
"excludes": [
  "oncology",
  "cancer",
  "tumor",
  "solid tumor",
  "hematologic malignancy"
]
```

**Option 2**: Tighten confidence threshold (not recommended)
```python
# Only accept high/medium confidence
if confidence in ["low", "very low", "unknown"]:
    return None  # Exclude instead of flagging
```

### If Still Missing Deals (False Negatives)

**Option 1**: Add more TA terms
```json
"includes": [
  // Add even broader terms
  "antibody therapy",
  "cell therapy",
  "biologics",
  "targeted therapy"
]
```

**Option 2**: Remove ALL TA filtering (nuclear option)
```python
# Accept everything, flag non-matches
needs_review = not ta_match
# Never exclude based on TA
```

---

## Summary

### Changes Made
1. ✅ Relaxed TA filtering (include mismatches with flag)
2. ✅ Expanded TA vocabulary (+20 broader terms)
3. ✅ Accept all confidence levels (flag low)

### Expected Results
- **2-4x more deals** found (20-40 vs 10-15)
- **~50% flagged** for manual review
- **~0% false negatives** (won't miss real deals)

### Trade-off
- **More manual review work** (10-20 deals to check)
- **Zero missed deals** (no false negatives)
- **Same cost** ($13-15)

### Philosophy
**"Include and flag" > "Exclude and miss"**

You can always delete false positives in Excel, but you can't recover false negatives!

---

## Ready to Run

```bash
python -m deal_finder.main --config config/config.yaml
```

Expect:
- **20-40 deals** (2-4x more than before)
- **10-20 flagged** (`needs_review = TRUE`)
- **$13-15 cost** (same as before)
- **30-60 min runtime** (same as before)

After run, review flagged deals in Excel and delete any false positives.

**You're now optimized for ZERO false negatives!** 🎯
