"""OpenAI GPT-4o-mini extractor with two-pass filtering and structured outputs."""

import logging
import os
import time
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import openai
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Cache for sentence transformer model (loaded once, reused)
_SENTENCE_TRANSFORMER_MODEL = None


def deduplicate_by_title(articles: list) -> list:
    """
    Remove duplicate articles using embeddings-based semantic similarity.

    Strategy (Optimized):
    1. Generate embeddings for article titles + first 200 chars of content
    2. Use k-NN to find only similar articles (not full O(n²) matrix)
    3. Group similar articles (>0.85 similarity)
    4. Keep longest version from each group

    Args:
        articles: List of article dicts with "title" and "content" keys

    Returns:
        Deduplicated list
    """
    global _SENTENCE_TRANSFORMER_MODEL
    from sklearn.neighbors import NearestNeighbors

    if not articles:
        return articles

    # Load better model once and cache it (all-mpnet-base-v2 for best accuracy)
    if _SENTENCE_TRANSFORMER_MODEL is None:
        logger.info("Loading sentence transformer model all-mpnet-base-v2 (best accuracy)...")
        from sentence_transformers import SentenceTransformer
        _SENTENCE_TRANSFORMER_MODEL = SentenceTransformer('all-mpnet-base-v2')
    else:
        logger.info("Using cached sentence transformer model...")

    model = _SENTENCE_TRANSFORMER_MODEL

    # Create text to embed: title + first 200 chars of content
    texts = []
    for article in articles:
        title = article.get("title", "")
        content = article.get("content", "")[:200]
        text = f"{title} {content}"
        texts.append(text)

    logger.info(f"Generating embeddings for {len(texts)} articles...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=256)

    # Use k-NN instead of full similarity matrix (10GB → 100MB memory savings!)
    logger.info("Finding similar articles using k-NN (memory-efficient)...")
    n_neighbors = min(20, len(articles))  # Find top 20 neighbors max
    nbrs = NearestNeighbors(n_neighbors=n_neighbors, metric='cosine', algorithm='auto')
    nbrs.fit(embeddings)

    # For each article, find its nearest neighbors
    distances, indices = nbrs.kneighbors(embeddings)

    # Find duplicates (similarity > 0.85)
    SIMILARITY_THRESHOLD = 0.85
    seen = set()
    duplicates_removed = 0
    final_articles = []

    for i in range(len(articles)):
        if i in seen:
            continue

        # Convert cosine distance to similarity (1 - distance)
        similarities = 1 - distances[i]
        similar_indices = [indices[i][j] for j in range(len(similarities))
                          if similarities[j] > SIMILARITY_THRESHOLD and indices[i][j] != i]

        if similar_indices:
            # Found duplicates - keep the longest one
            group = [i] + similar_indices
            longest_idx = max(group, key=lambda idx: len(articles[idx].get("content", "")))

            # Mark others as seen
            for idx in group:
                if idx != longest_idx:
                    seen.add(idx)
                    duplicates_removed += 1

            # Add longest version if not already added
            if longest_idx not in seen:
                final_articles.append(articles[longest_idx])
                seen.add(longest_idx)
        else:
            # No duplicates found
            final_articles.append(articles[i])
            seen.add(i)

    logger.info(f"Embeddings deduplication: {len(articles)} → {len(final_articles)} ({duplicates_removed} removed)")
    return final_articles


# Pydantic models for structured outputs
class DealParties(BaseModel):
    acquirer: Optional[str] = Field(None, description="Company acquiring/licensing")
    target: Optional[str] = Field(None, description="Company being acquired/licensed from")


class DealMoney(BaseModel):
    upfront_value: Optional[float] = Field(None, description="Upfront payment in millions USD")
    contingent_payment: Optional[float] = Field(None, description="Milestone payments in millions USD")
    total_deal_value: Optional[float] = Field(None, description="Total deal value in millions USD")
    currency: str = Field("USD", description="Currency code")


class DealExtraction(BaseModel):
    url: str = Field(..., description="Article URL")
    parties: DealParties
    deal_type: str = Field(..., description="M&A, partnership, licensing, or option-to-license")
    date_announced: Optional[str] = Field(None, description="Deal announcement date YYYY-MM-DD")
    money: DealMoney
    asset_focus: str = Field("Undisclosed", description="Drug/therapy/technology name")
    stage: str = Field("unknown", description="Development stage: preclinical, phase 1, etc.")
    therapeutic_area_match: bool = Field(..., description="Does this match target therapeutic area?")
    geography: Optional[str] = Field(None, description="Country/region")
    confidence: str = Field("medium", description="Confidence level: high, medium, low")
    key_evidence: str = Field(..., description="Brief quote supporting extraction")


class OpenAIExtractor:
    """Extract deals using GPT-4o-mini with two-pass filtering and parallel processing."""

    def __init__(self, api_key: Optional[str] = None, batch_size: int = 20, quick_filter_batch: int = 40):
        """Initialize OpenAI extractor.

        Args:
            api_key: OpenAI API key
            batch_size: Number of articles for full extraction per batch (10 recommended)
            quick_filter_batch: Number of articles for quick filter per batch (20 recommended)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self.client = openai.OpenAI(api_key=self.api_key)
        self.batch_size = batch_size
        self.quick_filter_batch = quick_filter_batch

    def _api_call_with_retry(self, model: str, messages: list, temperature: float = 0.0, max_retries: int = 5):
        """Make OpenAI API call with exponential backoff retry.

        Args:
            model: Model name
            messages: Chat messages
            temperature: Temperature setting
            max_retries: Maximum retry attempts

        Returns:
            API response
        """
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"}
                )
                return response
            except openai.RateLimitError as e:
                if attempt < max_retries - 1:
                    # More aggressive backoff: 5s, 10s, 20s, 40s
                    wait_time = (2 ** attempt) * 5.0
                    logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Rate limit exceeded after {max_retries} attempts")
                    raise
            except Exception as e:
                logger.error(f"API call failed: {e}")
                raise

    def extract_batch(
        self,
        articles: List[dict],
        ta_vocab: dict,
        allowed_stages: List[str] = None
    ) -> List[Optional[dict]]:
        """Extract deals with two-pass filtering, deduplication, and parallel processing.

        Pass 1: Quick filter (nano - title + 1000 chars)
        Deduplication: Embeddings-based semantic dedup (>0.85 similarity)
        Pass 2: Full extraction (gpt-4.1 - 10k chars)

        Args:
            articles: List of dicts with keys: url, title, content
            ta_vocab: Therapeutic area vocabulary
            allowed_stages: List of allowed development stages (e.g., ["preclinical", "phase 1"])

        Returns:
            List of extracted deal dicts (None for rejected articles)
        """
        if not articles:
            return []

        therapeutic_area = ta_vocab.get("therapeutic_area", "biotech")
        allowed_stages = allowed_stages or ["preclinical", "phase 1", "first-in-human"]

        # Check for existing quick filter checkpoint
        from pathlib import Path
        import json
        from datetime import datetime, timezone

        quick_filter_checkpoint = Path("output/quick_filter_checkpoint.json")

        if quick_filter_checkpoint.exists():
            logger.info("Found existing quick filter checkpoint, loading...")
            with open(quick_filter_checkpoint) as f:
                checkpoint_data = json.load(f)
                passed_articles = checkpoint_data.get("passed_articles", [])
                logger.info(f"✓ Loaded {len(passed_articles)} articles from quick filter checkpoint")
                logger.info(f"  Skipping Pass 1, proceeding directly to Pass 2")
        else:
            # PASS 1: Quick filter
            logger.info(f"Pass 1: Quick filtering {len(articles)} articles...")
            passed_articles = self._quick_filter(articles, therapeutic_area, allowed_stages)
            logger.info(f"Pass 1 results: {len(passed_articles)}/{len(articles)} passed quick filter")

            # Save quick filter checkpoint
            quick_filter_checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with open(quick_filter_checkpoint, 'w') as f:
                json.dump({
                    "passed_articles": passed_articles,
                    "total_input": len(articles),
                    "passed_count": len(passed_articles),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
            logger.info(f"✓ Saved quick filter checkpoint: {len(passed_articles)} articles passed")

        if not passed_articles:
            return [None] * len(articles)

        # DEDUPLICATION: Check for existing dedup checkpoint
        dedup_checkpoint = Path("output/dedup_checkpoint.json")

        if dedup_checkpoint.exists():
            logger.info("Found existing deduplication checkpoint, loading...")
            with open(dedup_checkpoint) as f:
                checkpoint_data = json.load(f)
                deduped_articles = checkpoint_data.get("deduped_articles", [])
                logger.info(f"✓ Loaded {len(deduped_articles)} articles from dedup checkpoint")
                logger.info(f"  Skipping deduplication, proceeding directly to Pass 2")
        else:
            # Deduplicate passed articles (embeddings-based)
            logger.info(f"Deduplicating {len(passed_articles)} articles using embeddings...")
            deduped_articles = deduplicate_by_title(passed_articles)
            logger.info(f"Deduplication results: {len(passed_articles)} → {len(deduped_articles)} articles")

            # Save dedup checkpoint
            dedup_checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with open(dedup_checkpoint, 'w') as f:
                json.dump({
                    "deduped_articles": deduped_articles,
                    "pre_dedup_count": len(passed_articles),
                    "post_dedup_count": len(deduped_articles),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
            logger.info(f"✓ Saved deduplication checkpoint: {len(deduped_articles)} articles")

        # PASS 2: Full extraction (parallel)
        logger.info(f"Pass 2: Full extraction on {len(deduped_articles)} articles (parallel)...")
        extractions = self._parallel_extract(deduped_articles, ta_vocab, allowed_stages)

        # Map results back to original articles
        extraction_map = {e["url"]: e for e in extractions if e and isinstance(e, dict) and "url" in e}

        # Warn if some extractions don't have URLs
        missing_urls = [e for e in extractions if e and isinstance(e, dict) and "url" not in e]
        if missing_urls:
            logger.warning(f"Found {len(missing_urls)} extractions without URLs (will be dropped)")

        results = []
        for article in articles:
            url = article.get("url")
            results.append(extraction_map.get(url))

        return results

    def _quick_filter(
        self,
        articles: List[dict],
        therapeutic_area: str,
        allowed_stages: List[str]
    ) -> List[dict]:
        """Quick filter using consensus voting prompt + 1000 chars.

        Returns:
            Articles that passed filter
        """
        passed = []

        # Format allowed stages for prompt
        stages_text = ", ".join(allowed_stages)
        not_allowed = "Any stages NOT in this list (e.g., if 'phase 2' is not selected, reject phase 2 deals)"

        # Process in batches using GPT-3.5-turbo (cheap and fast)
        for i in range(0, len(articles), self.quick_filter_batch):
            batch = articles[i:i + self.quick_filter_batch]

            prompt = f"""For each article below, determine if it describes a deal in {therapeutic_area} at the RIGHT development stage.

PASS if ALL conditions are met:
1. Article describes a business deal (M&A, partnership, licensing, collaboration)
2. Deal is related to {therapeutic_area} (Oncology is OK if {therapeutic_area}-related)
3. PRIMARY asset development stage is ONE OF: {stages_text}

REJECT if:
- Development stage is NOT in the allowed list: {not_allowed}
- Not a deal (just news, research results, opinion)
- Wrong therapeutic area

For each article below, return {{"passes": true}} or {{"passes": false}}

"""
            for j, article in enumerate(batch, 1):
                title = article.get("title", "")
                content = article.get("content", "")[:1000]  # First 1000 chars
                prompt += f"\n[{j}] Title: {title}\nContent: {content}\n"

            prompt += f"\nReturn JSON array with {len(batch)} objects: [{{'passes': true/false}}, ...]\n"

            try:
                # Use retry wrapper for API call
                response = self._api_call_with_retry(
                    model="gpt-4.1-nano-2025-04-14",
                    messages=[
                        {"role": "system", "content": "You are a precise biotech deal filter. Return only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0
                )

                import json
                content = response.choices[0].message.content
                results = json.loads(content)

                # Handle different response formats
                if isinstance(results, dict):
                    if "results" in results:
                        results = results["results"]
                    else:
                        results = list(results.values())

                # Flatten any nested lists (in case LLM returns [[{...}], [{...}], ...])
                flattened = []
                for item in results:
                    if isinstance(item, list):
                        # If item is a list, extend with its contents (handles nested lists)
                        flattened.extend(item)
                    else:
                        # If item is a dict or bool, append as-is
                        flattened.append(item)

                results = flattened

                for article, result in zip(batch, results):
                    if isinstance(result, dict) and result.get("passes"):
                        passed.append(article)
                    elif isinstance(result, bool) and result:
                        passed.append(article)

            except Exception as e:
                logger.error(f"Quick filter batch failed: {e}")
                # Conservative: pass all on error
                passed.extend(batch)

            # Small delay between batches to avoid rate limits
            if i + self.quick_filter_batch < len(articles):
                time.sleep(0.5)

        return passed

    def _parallel_extract(
        self,
        articles: List[dict],
        ta_vocab: dict,
        allowed_stages: List[str]
    ) -> List[dict]:
        """Extract deals with checkpointing every 250 articles.

        Returns:
            List of extracted deals
        """
        from pathlib import Path
        import json
        from datetime import datetime, timezone

        CHECKPOINT_INTERVAL = 250
        partial_checkpoint = Path("output/partial_extraction_checkpoint.json")

        # Check for existing partial checkpoint
        start_idx = 0
        all_results = []

        if partial_checkpoint.exists():
            logger.info("Found partial extraction checkpoint, resuming...")
            with open(partial_checkpoint) as f:
                checkpoint_data = json.load(f)
                all_results = checkpoint_data.get("results", [])
                start_idx = checkpoint_data.get("processed_count", 0)
                logger.info(f"✓ Resuming from article {start_idx}/{len(articles)}")

        # Split into batches
        batches = [articles[i:i + self.batch_size]
                   for i in range(start_idx, len(articles), self.batch_size)]

        # Process batches sequentially with small delays (avoids rate limit hell)
        for batch_idx, batch in enumerate(batches):
            try:
                # Process this batch
                results = self._extract_batch_structured(batch, ta_vocab, allowed_stages)
                all_results.extend(results)

                # Current total processed
                articles_processed = start_idx + (batch_idx + 1) * len(batch)

                logger.info(f"Progress: {articles_processed}/{len(articles)} articles extracted")

                # Save checkpoint every CHECKPOINT_INTERVAL articles
                if articles_processed % CHECKPOINT_INTERVAL < self.batch_size:
                    partial_checkpoint.parent.mkdir(parents=True, exist_ok=True)
                    with open(partial_checkpoint, 'w') as f:
                        json.dump({
                            "results": all_results,
                            "processed_count": articles_processed,
                            "total": len(articles),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }, f)
                    logger.info(f"✓ Saved checkpoint at {articles_processed} articles")

                # Delay between batches to avoid rate limits (0.5s = faster processing)
                if batch_idx < len(batches) - 1:
                    time.sleep(0.5)  # Reduced from 1.5s - upgrade VM to handle higher throughput

            except Exception as e:
                logger.error(f"Extraction batch failed at index {articles_processed}: {e}")
                # Save checkpoint on error
                partial_checkpoint.parent.mkdir(parents=True, exist_ok=True)
                with open(partial_checkpoint, 'w') as f:
                    json.dump({
                        "results": all_results,
                        "processed_count": articles_processed,
                        "total": len(articles),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "error": str(e)
                    }, f)
                logger.info(f"✓ Saved error checkpoint at {articles_processed} articles")
                raise

        # Clear partial checkpoint on successful completion
        if partial_checkpoint.exists():
            partial_checkpoint.unlink()
            logger.info("✓ Extraction complete, removed partial checkpoint")

        return all_results

    def _extract_batch_structured(
        self,
        articles: List[dict],
        ta_vocab: dict,
        allowed_stages: List[str]
    ) -> List[dict]:
        """Extract a batch using structured outputs.

        Returns:
            List of extracted deals
        """
        therapeutic_area = ta_vocab.get("therapeutic_area", "biotech")
        ta_includes = ta_vocab.get("includes", [])
        stages_text = ", ".join(allowed_stages)
        not_allowed = "Any stages NOT in this list should be REJECTED"

        prompt = f"""Extract {therapeutic_area}-related business deal information from these articles.

TARGET THERAPEUTIC AREA: {therapeutic_area}
Include terms: {', '.join(ta_includes[:20])}

ALLOWED DEVELOPMENT STAGES: {stages_text}
REJECT if stage is NOT in the allowed list: {not_allowed}

For each article, extract:
- parties (acquirer, target) - extract what's mentioned, use null if not found
- deal_type (M&A, partnership, licensing, option-to-license) - use "partnership" if unclear
- date_announced (YYYY-MM-DD) - extract if mentioned, use null otherwise
- money - CAREFULLY extract financial terms (all values in millions USD):
  * upfront_value: Initial payment (e.g., "$50M upfront" → 50, "$2 billion" → 2000, "€40M" → 40 with currency=EUR)
  * contingent_payment: Milestone/earnout payments (e.g., "$300M in milestones" → 300, "up to $1B" → 1000)
  * total_deal_value: Total deal value (e.g., "$350M total" → 350, or upfront + contingent if total not stated)
  * currency: Original currency code (USD, EUR, GBP, JPY, etc.)
  * SPECIAL CASES:
    - "undisclosed" / "not disclosed" / "terms not disclosed" → use null for all money fields
    - "up to $X" → use X as the value (it's the maximum)
    - "$X billion" → multiply by 1000 (e.g., "$2B" → 2000)
    - If only total is mentioned, put it in total_deal_value, leave upfront/contingent as null
    - If upfront + milestones mentioned separately, extract both AND calculate total
  * EXAMPLES:
    - "$50M upfront, $200M milestones" → upfront: 50, contingent: 200, total: 250
    - "up to $1 billion" → total: 1000
    - "$75 million acquisition" → upfront: 75, total: 75
    - "undisclosed financial terms" → all null
- asset_focus (drug/therapy name) - use "Undisclosed" if not mentioned
- stage (preclinical, phase 1, phase 1a, phase 1b, first-in-human, discovery, etc.) - use "unknown" if not mentioned
- therapeutic_area_match (true/false) - true if related to {therapeutic_area}
- geography (country/region) - use null if not mentioned
- confidence (high/medium/low)
- key_evidence (brief quote from article that includes deal parties and financial terms if mentioned)

CRITICAL STAGE FILTERING:
- ONLY extract deals where the PRIMARY asset stage is in the allowed list: {stages_text}
- REJECT (return null) if the PRIMARY asset stage is NOT in the allowed list
- Prioritize deals in allowed stages

IMPORTANT:
- Only extract information EXPLICITLY stated in the article
- Use null for fields not found - DO NOT infer or guess
- If only one party is mentioned, extract it and use null for the other
- If article mentions multiple assets at different stages, focus on the PRIMARY asset being transacted

"""
        for i, article in enumerate(articles, 1):
            content = article.get("content", "")[:10000]  # 10k chars for more context
            prompt += f"\n[ARTICLE {i}]\nURL: {article['url']}\nTitle: {article.get('title', '')}\nContent: {content}\n\n"

        prompt += f"Return JSON array with {len(articles)} deal objects or null if rejected.\n"

        try:
            # Use retry wrapper for API call
            response = self._api_call_with_retry(
                model="gpt-4.1-2025-04-14",
                messages=[
                    {"role": "system", "content": "You are a precise biotech deal extractor. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )

            import json
            content = response.choices[0].message.content
            results = json.loads(content)

            # Handle different response formats
            if isinstance(results, dict) and "results" in results:
                results = results["results"]
            elif isinstance(results, dict):
                results = list(results.values())

            # Flatten any nested lists (in case LLM returns [[deal], [deal], ...])
            flattened = []
            for item in results:
                if isinstance(item, list):
                    # If item is a list, extend with its contents (handles nested lists)
                    flattened.extend(item)
                else:
                    # If item is a dict or None, append as-is
                    flattened.append(item)

            results = flattened

            # Ensure each result has the URL from the corresponding article
            for i, result in enumerate(results):
                if result and isinstance(result, dict) and i < len(articles):
                    # Add URL if missing
                    if "url" not in result:
                        result["url"] = articles[i]["url"]

            # Warn if we have more/fewer results than articles
            if len(results) != len(articles):
                logger.warning(f"Batch returned {len(results)} results for {len(articles)} articles")
                # Truncate or pad to match article count
                if len(results) > len(articles):
                    results = results[:len(articles)]
                else:
                    results.extend([None] * (len(articles) - len(results)))

            logger.info(f"Extracted {len([r for r in results if r])}/{len(articles)} deals from batch")
            return results

        except Exception as e:
            logger.error(f"Structured extraction failed: {e}")
            return [None] * len(articles)

    def _extract_financials_regex_fallback(self, content: str) -> dict:
        """Fallback regex-based financial extractor for when OpenAI misses values.

        Looks for common patterns like:
        - "$50M upfront"
        - "$200 million in milestones"
        - "$1.5 billion acquisition"
        - "€40M"

        Args:
            content: Article text

        Returns:
            Dict with extracted financial values (in millions USD)
        """
        import re

        result = {
            "upfront_value": None,
            "contingent_payment": None,
            "total_deal_value": None,
            "currency": "USD"
        }

        # Pattern: $X million/billion (or M/B shorthand)
        # Matches: $50M, $200 million, $1.5B, $2.3 billion, €40M, £100M
        patterns = [
            # Currency symbol + number + M/B/million/billion
            r'([€£$¥])?\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)(?:\s+(?:upfront|initial|down))?',
            # "up to $X" constructions
            r'up to\s+([€£$¥])?\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)',
            # Milestone patterns
            r'(\d+(?:\.\d+)?)\s*(million|billion|M|B)\s+(?:in\s+)?(?:milestones|contingent|earnout)',
        ]

        all_values = []
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                # Extract currency (if present)
                currency_symbol = match.group(1) if len(match.groups()) >= 1 else None
                # Extract number
                number_str = match.group(2) if len(match.groups()) >= 2 else match.group(1)
                # Extract unit (million/billion)
                unit = match.group(3) if len(match.groups()) >= 3 else match.group(2)

                try:
                    value = float(number_str)

                    # Convert to millions
                    if unit.lower() in ['b', 'billion']:
                        value *= 1000

                    # Map currency symbol
                    currency_map = {'$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY'}
                    currency = currency_map.get(currency_symbol, 'USD')

                    all_values.append({
                        'value': value,
                        'currency': currency,
                        'text': match.group(0)
                    })
                except ValueError:
                    continue

        # If we found values, use the first one as total (simple heuristic)
        if all_values:
            result['total_deal_value'] = all_values[0]['value']
            result['currency'] = all_values[0]['currency']
            logger.info(f"Regex fallback extracted: {all_values[0]['value']}M {all_values[0]['currency']}")

        return result

    def _validate_and_fix_financials(self, money: dict) -> dict:
        """Validate and fix financial data extracted by OpenAI.

        Handles common extraction errors:
        - Billion/million confusion
        - Missing total when upfront + contingent provided
        - Negative values
        - Unrealistic values (>$100B or <$0.1M for biotech deals)

        Args:
            money: Raw money dict from extraction

        Returns:
            Cleaned money dict
        """
        if not isinstance(money, dict):
            return {}

        cleaned = {}

        # Extract values
        upfront = money.get("upfront_value")
        contingent = money.get("contingent_payment")
        total = money.get("total_deal_value")
        currency = money.get("currency", "USD")

        # Clean up values (convert to float, handle None)
        def clean_value(val):
            if val is None:
                return None
            try:
                val = float(val)
                # Filter out unrealistic values
                if val < 0:
                    logger.warning(f"Negative financial value detected: {val}, setting to null")
                    return None
                if val > 200000:  # >$200B in millions is unrealistic for biotech
                    logger.warning(f"Unrealistic value detected (might be billions as millions): {val}")
                    # Could be billions misinterpreted - don't auto-fix, just warn
                return val
            except (ValueError, TypeError):
                return None

        upfront = clean_value(upfront)
        contingent = clean_value(contingent)
        total = clean_value(total)

        # Auto-calculate total if missing but components provided
        if total is None and upfront is not None and contingent is not None:
            total = upfront + contingent
            logger.info(f"Calculated total: {upfront} + {contingent} = {total}")

        # Validate: total should be >= upfront + contingent
        if total is not None and upfront is not None and contingent is not None:
            calculated_total = upfront + contingent
            if abs(total - calculated_total) > 1.0:  # Allow 1M rounding error
                logger.warning(
                    f"Total mismatch: stated={total}, calculated={calculated_total}. "
                    f"Using stated total."
                )

        cleaned["upfront_value"] = upfront
        cleaned["contingent_payment"] = contingent
        cleaned["total_deal_value"] = total
        cleaned["currency"] = currency

        return cleaned

    def parse_extracted_deal(
        self,
        extraction: dict,
        ta_name: str
    ) -> Optional[dict]:
        """Parse extraction into standardized format (compatible with existing code).

        Args:
            extraction: Raw extraction dict
            ta_name: Therapeutic area name

        Returns:
            Standardized deal dict or None
        """
        if not extraction:
            return None

        # Flatten nested structure for compatibility
        flattened = {}

        # Extract parties (nested)
        parties = extraction.get("parties", {})
        if isinstance(parties, dict):
            flattened["target"] = parties.get("target")
            flattened["acquirer"] = parties.get("acquirer")

        # Extract and validate money (nested)
        money = extraction.get("money", {})
        if isinstance(money, dict):
            # Apply validation and cleanup
            cleaned_money = self._validate_and_fix_financials(money)

            # Regex fallback: if all money fields are null, try regex extraction on key_evidence
            if (cleaned_money.get("upfront_value") is None and
                cleaned_money.get("contingent_payment") is None and
                cleaned_money.get("total_deal_value") is None):

                key_evidence = extraction.get("key_evidence", "")
                if key_evidence:
                    logger.info("OpenAI missed financial data, trying regex fallback on key_evidence...")
                    regex_money = self._extract_financials_regex_fallback(key_evidence)

                    # Use regex values if found
                    if regex_money.get("total_deal_value") is not None:
                        cleaned_money.update(regex_money)
                        logger.info(f"Regex fallback succeeded: {regex_money}")

            flattened["upfront_value_usd"] = cleaned_money.get("upfront_value")
            flattened["contingent_payment_usd"] = cleaned_money.get("contingent_payment")
            flattened["total_deal_value_usd"] = cleaned_money.get("total_deal_value")
            flattened["currency"] = cleaned_money.get("currency", "USD")

        # Copy flat fields
        flattened["url"] = extraction.get("url")
        flattened["deal_type"] = extraction.get("deal_type")
        flattened["date_announced"] = extraction.get("date_announced")
        flattened["asset_focus"] = extraction.get("asset_focus", "Undisclosed")
        flattened["stage"] = extraction.get("stage", "unknown")
        flattened["therapeutic_area"] = ta_name
        flattened["geography"] = extraction.get("geography")
        flattened["confidence"] = extraction.get("confidence", "medium")
        flattened["key_evidence"] = extraction.get("key_evidence", "")
        flattened["needs_review"] = False

        return flattened
