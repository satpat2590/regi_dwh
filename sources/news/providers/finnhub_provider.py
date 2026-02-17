"""
Finnhub news data provider.

Free tier: 60 calls/minute. Provides sentiment scores.
https://finnhub.io/docs/api/general-news
https://finnhub.io/docs/api/market-news
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .base import NewsDataProvider, ProviderError, RateLimitError, NoDataError

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from utils.session import RequestSession

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


class FinnhubProvider(NewsDataProvider):
    """
    Finnhub news data provider.

    Free tier: 60 API calls/minute. Includes sentiment data.
    """

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("FINNHUB_KEY", "")
        if not key:
            raise ValueError(
                "Finnhub API key required. Set FINNHUB_KEY env var or pass api_key. "
                "Register at https://finnhub.io/register"
            )
        super().__init__(api_key=key)
        self.session = RequestSession()
        self.name = "finnhub"

    def get_articles(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        category: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Search Finnhub for general news.

        Finnhub's general-news endpoint uses category filter, not free-text query.
        We use the market news endpoint with category=general and filter results
        client-side by query terms.
        """
        if not from_date:
            from_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        if not to_date:
            to_date = datetime.utcnow().strftime("%Y-%m-%d")

        params = {
            "category": "general",
            "minId": 0,
            "token": self.api_key,
        }

        resp = self.session.get(f"{FINNHUB_BASE}/news", params=params)
        if not resp:
            raise ProviderError("Failed to fetch from Finnhub")

        if resp.status_code == 429:
            raise RateLimitError("Finnhub rate limit exceeded (60 calls/min)")

        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise ProviderError(f"Finnhub error: {data['error']}")

        if not isinstance(data, list):
            return []

        # Filter by query terms (client-side)
        query_terms = query.lower().split()
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        articles = []

        for item in data:
            title = (item.get("headline") or "").lower()
            summary = (item.get("summary") or "").lower()
            text = title + " " + summary

            # Check if any query term appears
            if not any(term in text for term in query_terms):
                continue

            # Check date range
            ts = item.get("datetime", 0)
            if ts:
                pub_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                if pub_date < from_date or pub_date > to_date:
                    continue
                published_at = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                published_at = ""

            articles.append({
                "provider": "finnhub",
                "source_name": item.get("source", ""),
                "title": item.get("headline", ""),
                "description": item.get("summary", ""),
                "url": item.get("url", ""),
                "published_at": published_at,
                "fetched_at": now,
                "category": category or item.get("category", ""),
                "sentiment": None,  # Finnhub general news doesn't include sentiment score
                "topics": [category] if category else [],
                "image_url": item.get("image", ""),
            })

            if len(articles) >= limit:
                break

        return articles

    def get_top_headlines(
        self,
        category: str = "business",
        country: str = "us",
        limit: int = 50,
    ) -> List[Dict]:
        """Get market news from Finnhub (category-based)."""
        # Map common categories to Finnhub categories
        finnhub_category = "general"
        cat_map = {
            "business": "general",
            "technology": "technology",
            "crypto": "crypto",
            "forex": "forex",
            "merger": "merger",
        }
        finnhub_category = cat_map.get(category, "general")

        params = {
            "category": finnhub_category,
            "minId": 0,
            "token": self.api_key,
        }

        resp = self.session.get(f"{FINNHUB_BASE}/news", params=params)
        if not resp:
            raise ProviderError("Failed to fetch headlines from Finnhub")

        if resp.status_code == 429:
            raise RateLimitError("Finnhub rate limit exceeded")

        data = resp.json()
        if not isinstance(data, list):
            return []

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        articles = []
        for item in data[:limit]:
            ts = item.get("datetime", 0)
            published_at = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""

            articles.append({
                "provider": "finnhub",
                "source_name": item.get("source", ""),
                "title": item.get("headline", ""),
                "description": item.get("summary", ""),
                "url": item.get("url", ""),
                "published_at": published_at,
                "fetched_at": now,
                "category": category,
                "sentiment": None,
                "topics": [category] if category else [],
                "image_url": item.get("image", ""),
            })

        return articles
