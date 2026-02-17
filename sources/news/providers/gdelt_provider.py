"""
GDELT news data provider.

Uses the GDELT DOC 2.0 API for full-text article search.
No API key required. Unlimited requests.

GDELT date format: YYYYMMDDHHMMSS
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .base import NewsDataProvider, ProviderError, NoDataError

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from utils.session import RequestSession

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltProvider(NewsDataProvider):
    """
    GDELT news data provider.

    Uses the GDELT DOC 2.0 API. No API key required.
    """

    def __init__(self):
        super().__init__(api_key=None)
        self.session = RequestSession()
        self.name = "gdelt"

    def _to_gdelt_date(self, date_str: str) -> str:
        """Convert YYYY-MM-DD to YYYYMMDDHHMMSS."""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y%m%d%H%M%S")

    def _parse_gdelt_datetime(self, gdelt_dt: str) -> str:
        """Convert GDELT datetime string to ISO format."""
        try:
            dt = datetime.strptime(gdelt_dt, "%Y%m%dT%H%M%SZ")
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            return gdelt_dt or ""

    def get_articles(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        category: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """Search GDELT for articles matching a query."""
        params = {
            "query": query,
            "mode": "ArtList",
            "maxrecords": str(min(limit, 250)),
            "format": "json",
            "sort": "DateDesc",
        }

        if from_date:
            params["startdatetime"] = self._to_gdelt_date(from_date)
        if to_date:
            params["enddatetime"] = self._to_gdelt_date(to_date)

        resp = self.session.get(GDELT_DOC_API, params=params)
        if not resp:
            raise ProviderError("Failed to fetch from GDELT API")

        data = resp.json()
        raw_articles = data.get("articles", [])
        if not raw_articles:
            return []

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        articles = []
        for a in raw_articles:
            articles.append({
                "provider": "gdelt",
                "source_name": a.get("domain", ""),
                "title": a.get("title", ""),
                "description": "",
                "url": a.get("url", ""),
                "published_at": self._parse_gdelt_datetime(a.get("seendate", "")),
                "fetched_at": now,
                "category": category,
                "sentiment": self._extract_sentiment(a),
                "sentiment_source": "gdelt_tone" if self._extract_sentiment(a) is not None else "",
                "topics": [category] if category else [],
                "image_url": a.get("socialimage", ""),
            })

        return articles

    def get_top_headlines(
        self,
        category: str = "business",
        country: str = "us",
        limit: int = 50,
    ) -> List[Dict]:
        """Get recent top news from GDELT (uses broad business query)."""
        query = f"{category} news"
        if country == "us":
            query += " United States"

        from_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self.get_articles(
            query=query,
            from_date=from_date,
            category=category,
            limit=limit,
        )

    def _extract_sentiment(self, article: dict) -> Optional[float]:
        """Extract sentiment tone from GDELT article data.

        Normalizes the raw GDELT tone (~-100 to +100) to -1..+1 scale
        so all sentiment values in the DB are comparable regardless of source.
        """
        tone = article.get("tone", "")
        if tone:
            try:
                # GDELT tone is comma-separated: tone,pos,neg,polarity,...
                parts = str(tone).split(",")
                raw = float(parts[0])
                return max(-1.0, min(1.0, raw / 100.0))
            except (ValueError, IndexError):
                pass
        return None
