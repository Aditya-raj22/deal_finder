"""Production-ready API integrations for news sources."""

import os
from datetime import datetime
from typing import List, Optional

import requests


class NewsAPI:
    """Base class for news API integrations."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()

    def search(
        self, query: str, from_date: str, to_date: str, page: int = 1
    ) -> List[dict]:
        """Search for articles. Returns list of {url, title, published_date, snippet}."""
        raise NotImplementedError


class PRNewswireAPI(NewsAPI):
    """PR Newswire API integration."""

    BASE_URL = "https://api.prnewswire.com/v1"

    def search(
        self, query: str, from_date: str, to_date: str, page: int = 1
    ) -> List[dict]:
        """Search PR Newswire releases."""
        if not self.api_key:
            return []

        try:
            response = self.session.get(
                f"{self.BASE_URL}/search",
                params={
                    "q": query,
                    "from": from_date,
                    "to": to_date,
                    "page": page,
                    "apikey": self.api_key,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            return [
                {
                    "url": item.get("url"),
                    "title": item.get("title"),
                    "published_date": item.get("publishedDate"),
                    "snippet": item.get("summary"),
                    "source": "PR Newswire",
                }
                for item in data.get("results", [])
            ]
        except Exception as e:
            print(f"PR Newswire API error: {e}")
            return []


class BusinessWireAPI(NewsAPI):
    """Business Wire API integration."""

    BASE_URL = "https://api.businesswire.com/v1"

    def search(
        self, query: str, from_date: str, to_date: str, page: int = 1
    ) -> List[dict]:
        """Search Business Wire releases."""
        if not self.api_key:
            return []

        try:
            response = self.session.get(
                f"{self.BASE_URL}/releases",
                params={
                    "q": query,
                    "startDate": from_date,
                    "endDate": to_date,
                    "page": page,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            return [
                {
                    "url": item.get("permalink"),
                    "title": item.get("headline"),
                    "published_date": item.get("publishDate"),
                    "snippet": item.get("summary"),
                    "source": "Business Wire",
                }
                for item in data.get("releases", [])
            ]
        except Exception as e:
            print(f"Business Wire API error: {e}")
            return []


class NewsAPIOrg(NewsAPI):
    """NewsAPI.org integration (aggregates multiple sources)."""

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key or os.getenv("NEWSAPI_ORG_KEY"))

    def search(
        self, query: str, from_date: str, to_date: str, page: int = 1
    ) -> List[dict]:
        """Search NewsAPI.org."""
        if not self.api_key:
            return []

        try:
            response = self.session.get(
                f"{self.BASE_URL}/everything",
                params={
                    "q": f'{query} AND ("biotech" OR "pharma" OR "pharmaceutical")',
                    "from": from_date,
                    "to": to_date,
                    "page": page,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "apiKey": self.api_key,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            return [
                {
                    "url": item.get("url"),
                    "title": item.get("title"),
                    "published_date": item.get("publishedAt"),
                    "snippet": item.get("description"),
                    "source": item.get("source", {}).get("name", "NewsAPI"),
                }
                for item in data.get("articles", [])
            ]
        except Exception as e:
            print(f"NewsAPI.org error: {e}")
            return []


class APISourceRegistry:
    """Registry of production API sources."""

    def __init__(self):
        self.apis = []

        # Initialize APIs if keys are available
        prnewswire_key = os.getenv("PRNEWSWIRE_API_KEY")
        if prnewswire_key:
            self.apis.append(PRNewswireAPI(prnewswire_key))

        businesswire_key = os.getenv("BUSINESSWIRE_API_KEY")
        if businesswire_key:
            self.apis.append(BusinessWireAPI(businesswire_key))

        newsapi_key = os.getenv("NEWSAPI_ORG_KEY")
        if newsapi_key:
            self.apis.append(NewsAPIOrg(newsapi_key))

    def search_all(
        self, query: str, from_date: str, to_date: str, max_results: int = 100
    ) -> List[dict]:
        """Search all available APIs."""
        all_results = []
        seen_urls = set()

        for api in self.apis:
            page = 1
            while len(all_results) < max_results:
                results = api.search(query, from_date, to_date, page)
                if not results:
                    break

                for result in results:
                    url = result.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(result)

                    if len(all_results) >= max_results:
                        break

                page += 1

        return all_results[:max_results]

    def is_enabled(self) -> bool:
        """Check if any APIs are configured."""
        return len(self.apis) > 0
