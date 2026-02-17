"""
Base provider interface for news data sources.

All news data providers must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class NewsDataProvider(ABC):
    """Abstract base class for news data providers."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.name = self.__class__.__name__

    @abstractmethod
    def get_articles(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        category: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Search for articles matching a query.

        Args:
            query: Search query string
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            category: Category filter
            limit: Max articles to return

        Returns:
            List of dicts with keys: provider, source_name, title, description,
            url, published_at, category, sentiment, topics, image_url
        """
        pass

    @abstractmethod
    def get_top_headlines(
        self,
        category: str = "business",
        country: str = "us",
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get top headlines.

        Args:
            category: News category (business, technology, etc.)
            country: Country code
            limit: Max articles to return

        Returns:
            List of article dicts (same format as get_articles)
        """
        pass


class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""
    pass


class ProviderError(Exception):
    """Base exception for provider-specific errors."""
    pass


class NoDataError(Exception):
    """Raised when no data is available for the query."""
    pass
