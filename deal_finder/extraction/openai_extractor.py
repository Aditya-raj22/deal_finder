"""OpenAI GPT-4o-mini extractor with two-pass filtering and structured outputs."""

import logging
import os
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import openai
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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

    def __init__(self, api_key: Optional[str] = None, batch_size: int = 10):
        """Initialize OpenAI extractor.

        Args:
            api_key: OpenAI API key
            batch_size: Number of articles to process per batch (10-20 recommended)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self.client = openai.OpenAI(api_key=self.api_key)
        self.batch_size = batch_size

    def extract_batch(
        self,
        articles: List[dict],
        ta_vocab: dict
    ) -> List[Optional[dict]]:
        """Extract deals with two-pass filtering and parallel processing.

        Pass 1: Quick filter (title + 500 chars)
        Pass 2: Full extraction on survivors

        Args:
            articles: List of dicts with keys: url, title, content
            ta_vocab: Therapeutic area vocabulary

        Returns:
            List of extracted deal dicts (None for rejected articles)
        """
        if not articles:
            return []

        therapeutic_area = ta_vocab.get("therapeutic_area", "biotech")

        # PASS 1: Quick filter
        logger.info(f"Pass 1: Quick filtering {len(articles)} articles...")
        passed_articles = self._quick_filter(articles, therapeutic_area)
        logger.info(f"Pass 1 results: {len(passed_articles)}/{len(articles)} passed quick filter")

        if not passed_articles:
            return [None] * len(articles)

        # PASS 2: Full extraction (parallel)
        logger.info(f"Pass 2: Full extraction on {len(passed_articles)} articles (parallel)...")
        extractions = self._parallel_extract(passed_articles, ta_vocab)

        # Map results back to original articles
        extraction_map = {e["url"]: e for e in extractions if e}
        results = []
        for article in articles:
            url = article.get("url")
            results.append(extraction_map.get(url))

        return results

    def _quick_filter(
        self,
        articles: List[dict],
        therapeutic_area: str
    ) -> List[dict]:
        """Quick filter using title + 500 chars snippet.

        Returns:
            Articles that passed filter
        """
        passed = []

        # Process in batches
        for i in range(0, len(articles), self.batch_size * 2):  # Larger batches for filtering
            batch = articles[i:i + self.batch_size * 2]

            prompt = f"""Filter articles for EARLY-STAGE {therapeutic_area} deals.

PASS if:
- Business deal (M&A, partnership, licensing)
- {therapeutic_area} related
- EARLY stage (preclinical, phase 1, discovery)
- Mentions money OR specific asset

REJECT if:
- Late stage (phase 2+, approved, marketed)
- Wrong therapeutic area
- Not a deal
- Opinion/interview

For each article, return: {{"passes": true/false}}

"""
            for j, article in enumerate(batch, 1):
                title = article.get("title", "")
                snippet = article.get("content", "")[:500]
                prompt += f"\n[{j}] Title: {title}\nSnippet: {snippet}\n"

            prompt += f"\nReturn JSON array with {len(batch)} booleans: [{{'passes': true/false}}, ...]\n"

            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a biotech deal filter. Return only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"}
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

        return passed

    def _parallel_extract(
        self,
        articles: List[dict],
        ta_vocab: dict
    ) -> List[dict]:
        """Extract deals in parallel with structured outputs.

        Returns:
            List of extracted deals
        """
        # Split into batches
        batches = [articles[i:i + self.batch_size] for i in range(0, len(articles), self.batch_size)]

        all_results = []

        # Process batches in parallel (5 workers max to avoid rate limits)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._extract_batch_structured, batch, ta_vocab): batch
                for batch in batches
            }

            for future in as_completed(futures):
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Parallel extraction batch failed: {e}")

        return all_results

    def _extract_batch_structured(
        self,
        articles: List[dict],
        ta_vocab: dict
    ) -> List[dict]:
        """Extract a batch using structured outputs.

        Returns:
            List of extracted deals
        """
        therapeutic_area = ta_vocab.get("therapeutic_area", "biotech")
        ta_includes = ta_vocab.get("includes", [])

        prompt = f"""Extract EARLY-STAGE {therapeutic_area} deals from these articles.

TARGET THERAPEUTIC AREA: {therapeutic_area}
Include terms: {', '.join(ta_includes[:20])}

For each article, extract:
- parties (acquirer, target)
- deal_type (M&A, partnership, licensing, option-to-license)
- date_announced (YYYY-MM-DD)
- money (upfront, contingent, total in millions USD, currency)
- asset_focus (drug/therapy name)
- stage (preclinical, phase 1, etc.)
- therapeutic_area_match (true/false)
- geography (country/region)
- confidence (high/medium/low)
- key_evidence (brief quote)

REJECT if late-stage (phase 2+, approved, marketed).

"""
        for i, article in enumerate(articles, 1):
            content = article.get("content", "")[:15000]  # 15k chars
            prompt += f"\n[ARTICLE {i}]\nURL: {article['url']}\nTitle: {article.get('title', '')}\nContent: {content}\n\n"

        prompt += f"Return JSON array with {len(articles)} deal objects or null if rejected.\n"

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a precise biotech deal extractor. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
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

            logger.info(f"Extracted {len([r for r in results if r])}/{len(articles)} deals from batch")
            return results

        except Exception as e:
            logger.error(f"Structured extraction failed: {e}")
            return [None] * len(articles)

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

        # Extract money (nested)
        money = extraction.get("money", {})
        if isinstance(money, dict):
            flattened["upfront_value_usd"] = money.get("upfront_value")
            flattened["contingent_payment_usd"] = money.get("contingent_payment")
            flattened["total_deal_value_usd"] = money.get("total_deal_value")
            flattened["currency"] = money.get("currency", "USD")

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
