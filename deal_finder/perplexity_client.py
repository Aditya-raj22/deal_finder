"""Perplexity API client for discovery and extraction."""

import json
import logging
import os
from typing import Any, List, Optional

import requests

logger = logging.getLogger(__name__)


class PerplexityClient:
    """Client for Perplexity API with search and extraction capabilities."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Perplexity client.

        Args:
            api_key: Perplexity API key. If None, will read from PERPLEXITY_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY not found in environment")

        self.base_url = "https://api.perplexity.ai"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def search_deals(
        self,
        query: str,
        from_date: str,
        to_date: str,
        max_results: int = 100
    ) -> List[dict]:
        """Search for biotech/pharma deals using Perplexity's deep search.

        Args:
            query: Search query (e.g., "oncology acquisition")
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            max_results: Maximum number of results to return

        Returns:
            List of article metadata dicts with keys: url, title, published_date, snippet, source
        """
        # Use max depth search for maximum breadth
        search_prompt = f"""Search for biotech and pharmaceutical industry deals related to: {query}

Time range: {from_date} to {to_date}

Find press releases and news articles about:
- Mergers and acquisitions (M&A)
- Partnerships and collaborations
- Licensing deals and option agreements
- Asset acquisitions

For each relevant article, extract:
1. Article URL (must be direct link to article, not Google News redirect)
2. Article title
3. Publication date
4. Brief snippet describing the deal

Return results as a JSON array with format:
[
  {{
    "url": "https://...",
    "title": "Company A acquires Company B",
    "published_date": "2024-01-15",
    "snippet": "Brief description...",
    "source": "Source name"
  }}
]

Focus on finding up to {max_results} unique, high-quality articles from reliable sources like:
- FierceBiotech, FiercePharma
- Endpoints News, BioPharma Dive
- GEN (Genetic Engineering & Biotechnology News)
- Company press release pages
- Business Wire, PR Newswire

IMPORTANT: Only include direct article URLs, not search result pages or redirects."""

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": "sonar-pro",  # Best model: 200K context, 2-3x more sources
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a biotech industry research assistant. Return only valid JSON arrays."
                        },
                        {
                            "role": "user",
                            "content": search_prompt
                        }
                    ],
                    "temperature": 0.0,  # Zero temperature for maximum accuracy
                    "max_tokens": 8000,  # Larger budget for comprehensive results
                    "search_domain_filter": [
                        "fiercebiotech.com"
                    ],  # Limited to FierceBiotech only (cost optimization)
                    "search_recency_filter": "month"  # Recent articles
                },
                timeout=180  # Longer timeout for sonar-pro deep search
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response
            try:
                results = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                import re
                match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
                if match:
                    results = json.loads(match.group(1))
                else:
                    logger.error(f"Failed to parse JSON from Perplexity response: {content[:500]}")
                    return []

            # Validate and clean results
            validated_results = []
            for item in results[:max_results]:
                if isinstance(item, dict) and "url" in item and item["url"]:
                    validated_results.append({
                        "url": item.get("url", "").strip(),
                        "title": item.get("title", "").strip(),
                        "published_date": item.get("published_date"),
                        "snippet": item.get("snippet", "").strip(),
                        "source": item.get("source", "Perplexity Search")
                    })

            logger.info(f"Perplexity search returned {len(validated_results)} results for query: {query}")
            return validated_results

        except Exception as e:
            logger.error(f"Perplexity search failed for query '{query}': {e}")
            return []

    def extract_deals_batch(
        self,
        articles: List[dict],
        ta_vocab: dict
    ) -> List[dict]:
        """Extract deal information from multiple articles in a single API call.

        Args:
            articles: List of dicts with keys: url, title, content (HTML text)
            ta_vocab: Therapeutic area vocabulary for matching

        Returns:
            List of extracted deal dicts, one per article
        """
        if not articles:
            return []

        # Build therapeutic area context
        ta_name = ta_vocab.get("therapeutic_area", "biotech")
        ta_includes = ta_vocab.get("includes", [])
        ta_excludes = ta_vocab.get("excludes", [])

        # Create batch extraction prompt
        batch_prompt = f"""You are a biotech deal extraction expert. Extract structured deal information from the following {len(articles)} articles.

THERAPEUTIC AREA FOCUS: {ta_name}
- Include terms: {', '.join(ta_includes[:20])}
- Exclude terms: {', '.join(ta_excludes[:10])}

For EACH article, extract:
1. **parties**: {{
     "acquirer": "Company acquiring/licensing" or null,
     "target": "Company being acquired/licensed from" or null,
     "partner1": "First partner (for collaborations)" or null,
     "partner2": "Second partner (for collaborations)" or null
   }}
2. **deal_type**: "M&A" | "partnership" | "licensing" | "option-to-license" | "unknown"
3. **date_announced**: "YYYY-MM-DD" or null
4. **money**: {{
     "upfront_value": number or null,
     "contingent_payment": number or null,
     "total_deal_value": number or null,
     "currency": "USD" | "EUR" | "GBP" etc.
   }}
5. **asset_focus**: "Drug/therapy/technology name" or "Undisclosed"
6. **stage**: "preclinical" | "phase 1" | "phase I" | "phase 2" | "phase II" | "phase 3" | "phase III" | "approved" | "unknown"
7. **therapeutic_area_match**: true/false (does this match {ta_name}?)
8. **geography**: Country/region or null
9. **confidence**: "high" | "medium" | "low"
10. **key_evidence**: Brief quote supporting extraction

---

"""
        # Add each article to the prompt
        for i, article in enumerate(articles, 1):
            content = article.get("content", "")[:10000]  # Limit to 10k chars per article
            published_date = article.get("published_date", "Unknown")
            batch_prompt += f"""
ARTICLE {i}:
URL: {article.get('url', 'N/A')}
Title: {article.get('title', 'N/A')}
Published Date: {published_date}
Content: {content}

---

"""

        batch_prompt += f"""
Return a JSON array with {len(articles)} objects (one per article, in order):
[
  {{
    "article_index": 1,
    "url": "article URL",
    "article_published_date": "YYYY-MM-DD from article metadata (fallback if date_announced is null)",
    "parties": {{}},
    "deal_type": "...",
    "date_announced": "YYYY-MM-DD when deal was announced (extract from article text, null if not found)",
    "money": {{}},
    "asset_focus": "...",
    "stage": "...",
    "therapeutic_area_match": true/false,
    "geography": "...",
    "confidence": "...",
    "key_evidence": "..."
  }},
  ...
]

CRITICAL: Return valid JSON only. If information is not found, use null. Always include article_published_date from metadata."""

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": "sonar-pro",  # Best model: 200K context, optimal for extraction
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise data extraction system. Return only valid JSON arrays with complete data for all articles."
                        },
                        {
                            "role": "user",
                            "content": batch_prompt
                        }
                    ],
                    "temperature": 0.0,  # Zero temperature for maximum accuracy
                    "max_tokens": 16000,  # Large token budget for batch responses (5 articles)
                },
                timeout=240  # Longer timeout for batch processing with sonar-pro
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response
            try:
                results = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                import re
                match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
                if match:
                    results = json.loads(match.group(1))
                else:
                    logger.error(f"Failed to parse JSON from batch extraction: {content[:500]}")
                    return []

            logger.info(f"Successfully extracted {len(results)} deals from batch of {len(articles)} articles")
            return results

        except Exception as e:
            logger.error(f"Batch extraction failed: {e}")
            return []

    def extract_single_deal(
        self,
        url: str,
        title: str,
        content: str,
        ta_vocab: dict
    ) -> Optional[dict]:
        """Extract deal information from a single article (fallback for batch failures).

        Args:
            url: Article URL
            title: Article title
            content: Article HTML text content
            ta_vocab: Therapeutic area vocabulary

        Returns:
            Extracted deal dict or None
        """
        result = self.extract_deals_batch(
            articles=[{"url": url, "title": title, "content": content}],
            ta_vocab=ta_vocab
        )
        return result[0] if result else None
