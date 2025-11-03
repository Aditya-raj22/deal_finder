# Changes: False Negative Prevention Update

## Summary

Updated the pipeline to **include ambiguous matches** in the dataset with `Needs Review = TRUE` rather than excluding them. This prevents false negatives (missed deals) at the cost of more false positives requiring manual review.

## What Changed

### Behavior Changes

**Before:**
- Ambiguous stage → Excluded (returned `None`)
- Ambiguous TA match → Excluded (returned `False`)
- Ambiguous deal type → Excluded (returned `None`)

**After:**
- Ambiguous stage → Included as "preclinical" with `needs_review=True`
- Ambiguous TA match → Included with `needs_review=True`
- Ambiguous deal type → Included as "Partnership" with `needs_review=True`

### Code Changes

**1. Stage Classifier** (`deal_finder/classification/stage_classifier.py`)
- Ambiguous phases (e.g., "phase 1/2") → Returns `PRECLINICAL` with `needs_review=True`
- Unknown stages → Returns `PRECLINICAL` with `needs_review=True`

**2. TA Matcher** (`deal_finder/classification/ta_matcher.py`)
- No explicit match → Returns `True` (include) with `needs_review=True`

**3. Deal Type Classifier** (`deal_finder/classification/deal_type_classifier.py`)
- Unknown deal type → Returns `PARTNERSHIP` with `needs_review=True`

**4. Pipeline** (`deal_finder/pipeline.py`)
- Updated comments to clarify hard exclusions vs. ambiguous inclusions

### Hard Exclusions (Still Rejected)

These items are still **excluded** from the dataset:
1. **Confirmed Phase 2+** - Explicitly outside early-stage scope
2. **Confirmed non-TA** - When exclude rules match (e.g., "cancer" when searching I&I)
3. **Missing required fields** - No date or URL

### Test Updates

Updated tests to reflect new behavior:
- `test_ambiguous_phase_1_2` - Now expects `PRECLINICAL` with `needs_review=True`
- `test_no_stage_found` - Now expects `PRECLINICAL` with `needs_review=True`
- `test_no_match` (TA) - Now expects `True` (include) with `needs_review=True`

## Impact

### Pros
✅ **Zero false negatives** - Won't miss any potential deals
✅ **Complete audit trail** - All ambiguous cases documented
✅ **User control** - Manual review decides inclusion

### Cons
⚠️ **More manual review** - Higher volume of `Needs Review = TRUE` items
⚠️ **Noisier dataset** - More false positives in initial export

## Usage

No changes to CLI usage. The Excel output will now contain:
- More rows overall (includes ambiguous matches)
- Higher percentage of `Needs Review = TRUE` rows
- All ambiguous cases have evidence logged for manual verification

## Recommendation

**Filter strategy:**
1. **Quick scan**: Filter to `Needs Review = FALSE` for high-confidence deals
2. **Complete review**: Review all `Needs Review = TRUE` items and update manually
3. **Re-import**: Clean dataset can replace rows after manual validation

## Rollback

To revert to strict exclusion behavior, change the following return statements to return `None` or `False`:
- `stage_classifier.py:59` - Change back to `return None, True, None`
- `stage_classifier.py:83` - Change back to `return None, True, None`
- `ta_matcher.py:83` - Change back to `return False, True, None`
- `deal_type_classifier.py:75` - Change back to `return None, True, None`
