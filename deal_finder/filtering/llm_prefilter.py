"""LLM-based pre-filter using GPT-4o-mini for cheap, accurate filtering."""

import logging
import os
import time
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import openai

logger = logging.getLogger(__name__)


class LLMPreFilter:
    """Filter articles using cheap LLM (GPT-4o-mini) before expensive Perplexity extraction."""

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
        """Filter articles using LLM to identify early-stage I&I deals.

        Args:
            articles: List of dicts with keys: url, title, content
            therapeutic_area: Target therapeutic area

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

        # Estimate cost: ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens
        # Assume ~300 tokens input/article, ~50 tokens output
        input_tokens = len(articles) * 300
        output_tokens = len(articles) * 50
        total_cost = (input_tokens / 1_000_000 * 0.15) + (output_tokens / 1_000_000 * 0.60)

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
        """Filter a batch of articles using GPT-4o-mini.

        Returns:
            List of dicts with keys: passes (bool), reason (str)
        """
        # Build batch prompt
        prompt = f"""You are a biotech deal filter. For each article below, determine if it describes an EARLY-STAGE deal in {therapeutic_area}.

CRITERIA FOR PASSING:
1. Must be about a business deal (M&A, partnership, licensing, collaboration)
2. Must mention {therapeutic_area} or related conditions
3. Must be EARLY STAGE: preclinical, phase 1, discovery, research-stage, or IND-enabling
4. Must involve two companies (acquirer/licensor + target/licensee)
5. Must mention money/deal value OR specific therapeutic asset

REJECT IF:
- Late stage (phase 2, phase 3, approved, marketed, commercial)
- Not a deal (just research news, clinical trial results, earnings)
- Wrong therapeutic area
- Opinion pieces, interviews, webinars
- Just mentions of past deals in passing

For each article, return JSON: {{"passes": true/false, "reason": "brief explanation"}}

"""

        # Add articles
        for i, article in enumerate(articles, 1):
            title = article.get("title", "")
            content = article.get("content", "")[:500]  # First 500 chars
            prompt += f"\n[ARTICLE {i}]\nTitle: {title}\nContent: {content}\n"

        prompt += f"\n\nReturn a JSON array with {len(articles)} objects in order:\n"
        prompt += '[{"passes": true/false, "reason": "..."}, ...]\n'

        # Call OpenAI
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",  # Cheapest model: $0.15/$0.60 per 1M tokens
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise biotech deal filter. Return only valid JSON arrays."
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
            # Handle both dict with "results" key or direct list
            if isinstance(results, dict) and "results" in results:
                results = results["results"]
            elif isinstance(results, dict) and len(results) == len(articles):
                # Convert dict to list
                results = list(results.values())

            # Flatten any nested lists (in case LLM returns [[{...}], [{...}], ...])
            flattened = []
            for item in results:
                if isinstance(item, list):
                    # If item is a list, extend with its contents (handles nested lists)
                    flattened.extend(item)
                else:
                    # If item is a dict, append as-is
                    flattened.append(item)

            results = flattened

            return results
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {content[:200]}")
            # Return all as passing (conservative)
            return [{"passes": True, "reason": "Parse error"} for _ in articles]
