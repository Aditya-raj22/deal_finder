"""Conservative LLM-based pre-filter using GPT-3.5-turbo for cheap filtering."""

import logging
import os
import time
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import openai

logger = logging.getLogger(__name__)


class LLMPreFilter:
    """Conservative filter to discard clearly irrelevant articles before deduplication."""

    def __init__(self, api_key: Optional[str] = None, batch_size: int = 20):
        """Initialize LLM pre-filter.

        Args:
            api_key: OpenAI API key
            batch_size: Number of articles to process per API call (20-50 recommended)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self.client = openai.OpenAI(api_key=self.api_key)
        self.batch_size = batch_size

    def filter_articles(
        self,
        articles: List[dict],
        therapeutic_area: str = "immunology/inflammation"
    ) -> dict:
        """Conservatively filter out clearly irrelevant articles.

        ONLY DISCARD if article:
        1. Doesn't talk about a deal at all
        2. Explicitly says indication is NOT immunology/inflammation/oncology
        3. Explicitly mentions phase 2 or more

        When in doubt, KEEP the article.

        Args:
            articles: List of dicts with keys: url, title, content
            therapeutic_area: Target therapeutic area (for reference)

        Returns:
            Dict with keys:
                - passed: List of articles that passed filter
                - failed: List of articles that failed filter
                - cost: Estimated cost in USD
        """
        if not articles:
            return {"passed": [], "failed": [], "cost": 0.0}

        passed = []
        failed = []
        total_cost = 0.0

        # Split into batches
        batches = []
        for i in range(0, len(articles), self.batch_size):
            batch = articles[i:i + self.batch_size]
            batches.append((i//self.batch_size + 1, batch))

        logger.info(f"Processing {len(batches)} batches in parallel (10 workers max)...")

        # Process batches in parallel (10 workers to avoid rate limits)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self._filter_batch_safe, batch_num, batch, therapeutic_area): (batch_num, batch)
                for batch_num, batch in batches
            }

            for future in as_completed(futures):
                batch_num, batch = futures[future]
                try:
                    batch_results = future.result()

                    for article, result in zip(batch, batch_results):
                        if result["passes"]:
                            article["llm_filter_reason"] = result["reason"]
                            passed.append(article)
                        else:
                            failed.append({
                                "url": article["url"],
                                "title": article.get("title", ""),
                                "reason": result["reason"]
                            })

                except Exception as e:
                    logger.error(f"LLM pre-filter batch {batch_num} failed: {e}")
                    # On failure, assume all pass (conservative)
                    passed.extend(batch)

        # Estimate cost for GPT-3.5-turbo: ~$0.50 per 1M input tokens, ~$1.50 per 1M output tokens
        # Assume ~250 tokens input/article (500 chars), ~30 tokens output
        input_tokens = len(articles) * 250
        output_tokens = len(articles) * 30
        total_cost = (input_tokens / 1_000_000 * 0.50) + (output_tokens / 1_000_000 * 1.50)

        logger.info(f"LLM pre-filter: {len(passed)}/{len(articles)} passed (${total_cost:.2f})")

        return {
            "passed": passed,
            "failed": failed,
            "cost": total_cost
        }

    def _filter_batch_safe(
        self,
        batch_num: int,
        articles: List[dict],
        therapeutic_area: str
    ) -> List[dict]:
        """Thread-safe wrapper for filtering a batch."""
        logger.info(f"LLM pre-filter batch {batch_num}: {len(articles)} articles")
        return self._filter_batch(articles, therapeutic_area)

    def _filter_batch(
        self,
        articles: List[dict],
        therapeutic_area: str
    ) -> List[dict]:
        """Filter a batch of articles using GPT-3.5-turbo.

        Returns:
            List of dicts with keys: passes (bool), reason (str)
        """
        # Build batch prompt with explicit examples
        prompt = f"""You are a conservative biotech article filter. For each article below (first 500 characters), decide if it should be DISCARDED.

DISCARD ONLY IF:
1. Does NOT talk about a business deal (M&A, partnership, licensing, collaboration, acquisition, agreement)
   - Keep if it mentions any deal-related keywords
   - Keep if unclear

2. EXPLICITLY says the indication is NOT immunology/inflammation/oncology
   - If it says immunology, inflammation, oncology, autoimmune, cancer, tumor → KEEP
   - If it doesn't mention indication at all → KEEP
   - Only discard if it clearly says something like "cardiovascular", "neuro", "metabolic" with NO mention of I&I/oncology

3. EXPLICITLY mentions Phase 2, Phase 3, Phase II, Phase III, approved, marketed, or commercial product
   - If it says "preclinical", "discovery", "Phase 1", "Phase I", "IND" → KEEP
   - If it doesn't mention clinical stage → KEEP
   - Only discard if it clearly mentions phase 2 or later

WHEN IN DOUBT → KEEP THE ARTICLE

"""

        # Add articles (first 500 chars only)
        for i, article in enumerate(articles, 1):
            title = article.get("title", "")
            content = article.get("content", "")[:500]  # First 500 chars only
            prompt += f"\n[ARTICLE {i}]\nTitle: {title}\nContent: {content}...\n"

        prompt += f"""\n\nYou MUST return a JSON object with a "results" key containing an array of EXACTLY {len(articles)} objects.

REQUIRED FORMAT:
{{
  "results": [
    {{"passes": true, "reason": "mentions deal"}},
    {{"passes": false, "reason": "no deal mentioned"}},
    ...
  ]
}}

Return {len(articles)} results in the same order as the articles above.\n"""

        # Call OpenAI
        response = self.client.chat.completions.create(
            model="gpt-3.5-turbo",  # Cheap and fast: $0.50/$1.50 per 1M tokens
            messages=[
                {
                    "role": "system",
                    "content": "You are a conservative filter. When uncertain, keep the article. Return only valid JSON arrays."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.0,
            response_format={"type": "json_object"}  # Ensure JSON response
        )

        content = response.choices[0].message.content

        # Parse JSON
        import json
        try:
            results = json.loads(content)

            # Handle various response formats
            if isinstance(results, list):
                # Direct list format
                pass
            elif isinstance(results, dict):
                # Try common keys
                if "results" in results:
                    results = results["results"]
                elif "articles" in results:
                    results = results["articles"]
                else:
                    # Assume dict keys are article numbers, values are results
                    # Sort by key to maintain order
                    sorted_items = sorted(results.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
                    results = [item[1] for item in sorted_items]

            # Flatten any nested lists and validate each item is a dict
            flattened = []
            for item in results:
                if isinstance(item, list):
                    for subitem in item:
                        if isinstance(subitem, dict):
                            flattened.append(subitem)
                elif isinstance(item, dict):
                    flattened.append(item)
                else:
                    # Invalid format, use conservative default
                    logger.warning(f"Invalid result format: {item}")
                    flattened.append({"passes": True, "reason": "Invalid format"})

            results = flattened

            # Ensure we have the right number of results
            if len(results) != len(articles):
                logger.error(f"Expected {len(articles)} results, got {len(results)}. Using conservative defaults.")
                return [{"passes": True, "reason": "Count mismatch"} for _ in articles]

            return results
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}. Content: {content[:200]}")
            # Return all as passing (conservative)
            return [{"passes": True, "reason": "Parse error"} for _ in articles]
