"""
NewsAPI.org news data provider.

Free tier: 100 requests/day, 1 month lookback.
https://newsapi.org/docs
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

NEWSAPI_BASE = "https://newsapi.org/v2"
MAX_LOOKBACK_DAYS = 30  # Free tier limit


class NewsApiProvider(NewsDataProvider):
    """
    NewsAPI.org news data provider.

    Free tier: 100 requests/day, 1 month lookback max.
    """

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("NEWSAPI_KEY", "")
        if not key:
            raise ValueError(
                "NewsAPI key required. Set NEWSAPI_KEY env var or pass api_key. "
                "Register at https://newsapi.org/register"
            )
        super().__init__(api_key=key)
        self.session = RequestSession()
        self.name = "newsapi"

    def _clamp_from_date(self, from_date: Optional[str]) -> str:
        """Clamp from_date to max lookback (free tier = 1 month)."""
        earliest = (datetime.utcnow() - timedelta(days=MAX_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        if not from_date or from_date < earliest:
            if from_date:
                logger.warning(
                    f"NewsAPI free tier: clamping from_date {from_date} -> {earliest} (1mo limit)"
                )
            return earliest
        return from_date

    def get_articles(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        category: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """Search for articles via NewsAPI /everything endpoint."""
        from_date = self._clamp_from_date(from_date)

        params = {
            "q": query,
            "from": from_date,
            "sortBy": "publishedAt",
            "pageSize": min(limit, 100),
            "language": "en",
            "apiKey": self.api_key,
        }
        if to_date:
            params["to"] = to_date

        resp = self.session.get(f"{NEWSAPI_BASE}/everything", params=params)
        if not resp:
            raise ProviderError("Failed to fetch from NewsAPI")

        data = resp.json()
        if data.get("status") == "error":
            code = data.get("code", "")
            if code == "rateLimited":
                raise RateLimitError(f"NewsAPI rate limit: {data.get('message', '')}")
            raise ProviderError(f"NewsAPI error: {data.get('message', '')}")

        raw = data.get("articles", [])
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        articles = []
        for a in raw:
            articles.append({
                "provider": "newsapi",
                "source_name": (a.get("source") or {}).get("name", ""),
                "title": a.get("title", "") or "",
                "description": a.get("description", "") or "",
                "url": a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
                "fetched_at": now,
                "category": category,
                "sentiment": None,
                "topics": [category] if category else [],
                "image_url": a.get("urlToImage", "") or "",
            })

        return articles

    def get_top_headlines(
        self,
        category: str = "business",
        country: str = "us",
        limit: int = 50,
    ) -> List[Dict]:
        """Get top headlines via NewsAPI /top-headlines endpoint."""
        params = {
            "category": category,
            "country": country,
            "pageSize": min(limit, 100),
            "apiKey": self.api_key,
        }

        resp = self.session.get(f"{NEWSAPI_BASE}/top-headlines", params=params)
        if not resp:
            raise ProviderError("Failed to fetch headlines from NewsAPI")

        data = resp.json()
        if data.get("status") == "error":
            raise ProviderError(f"NewsAPI error: {data.get('message', '')}")

        raw = data.get("articles", [])
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        articles = []
        for a in raw:
            articles.append({
                "provider": "newsapi",
                "source_name": (a.get("source") or {}).get("name", ""),
                "title": a.get("title", "") or "",
                "description": a.get("description", "") or "",
                "url": a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
                "fetched_at": now,
                "category": category,
                "sentiment": None,
                "topics": [category] if category else [],
                "image_url": a.get("urlToImage", "") or "",
            })

        return articles
