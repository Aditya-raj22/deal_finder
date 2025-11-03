"""Source registry for news sources."""

from typing import List


class Source:
    """News source definition."""

    def __init__(self, name: str, base_url: str, source_type: str, search_template: str):
        self.name = name
        self.base_url = base_url
        self.source_type = source_type  # IR, newswire, trade_press
        self.search_template = search_template


class SourceRegistry:
    """Registry of deal news sources."""

    def __init__(self):
        self.sources = self._build_sources()

    def _build_sources(self) -> List[Source]:
        """Build list of news sources."""
        sources = []

        # Newswires
        sources.append(
            Source(
                name="PR Newswire",
                base_url="https://www.prnewswire.com",
                source_type="newswire",
                search_template="https://www.prnewswire.com/search/news/?keyword={query}&page={page}",
            )
        )

        sources.append(
            Source(
                name="Business Wire",
                base_url="https://www.businesswire.com",
                source_type="newswire",
                search_template="https://www.businesswire.com/portal/site/home/search/?searchType=news&searchTerm={query}&searchPage={page}",
            )
        )

        sources.append(
            Source(
                name="GlobeNewswire",
                base_url="https://www.globenewswire.com",
                source_type="newswire",
                search_template="https://www.globenewswire.com/search/keyword/{query}?page={page}",
            )
        )

        # Trade press
        sources.append(
            Source(
                name="Endpoints News",
                base_url="https://endpts.com",
                source_type="trade_press",
                search_template="https://endpts.com/?s={query}&page={page}",
            )
        )

        sources.append(
            Source(
                name="FierceBiotech",
                base_url="https://www.fiercebiotech.com",
                source_type="trade_press",
                search_template="https://www.fiercebiotech.com/search?s={query}&page={page}",
            )
        )

        return sources

    def get_sources_by_type(self, source_type: str) -> List[Source]:
        """Get sources by type."""
        return [s for s in self.sources if s.source_type == source_type]

    def get_all_sources(self) -> List[Source]:
        """Get all sources."""
        return self.sources
