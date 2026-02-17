"""Tests for GDELT, NewsAPI, and Finnhub providers with mocked HTTP."""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.__bool__ = lambda self: self.status_code == 200
    return resp


# ===================================================================
# GDELT Provider — 7 tests
# ===================================================================

class TestGdeltProvider:
    def _make_provider(self):
        with patch("sources.news.providers.gdelt_provider.RequestSession"):
            from sources.news.providers.gdelt_provider import GdeltProvider
            return GdeltProvider()

    def test_article_parsing(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "articles": [{
                "domain": "reuters.com",
                "title": "GDP grows",
                "url": "http://reuters.com/1",
                "seendate": "20250115T103000Z",
                "tone": "-1.5,3.0,4.5",
                "socialimage": "http://img.com/1.jpg",
            }]
        })
        result = provider.get_articles("GDP")
        assert len(result) == 1
        a = result[0]
        assert a["provider"] == "gdelt"
        assert a["source_name"] == "reuters.com"
        assert a["title"] == "GDP grows"
        assert a["url"] == "http://reuters.com/1"
        assert a["image_url"] == "http://img.com/1.jpg"

    def test_datetime_parsing(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "articles": [{"seendate": "20250115T103000Z", "url": "http://x.com"}]
        })
        result = provider.get_articles("test")
        assert result[0]["published_at"] == "2025-01-15T10:30:00Z"

    def test_date_to_gdelt_params(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={"articles": []})
        provider.get_articles("test", from_date="2025-01-01", to_date="2025-01-15")
        _, kwargs = provider.session.get.call_args
        assert kwargs["params"]["startdatetime"] == "20250101000000"
        assert kwargs["params"]["enddatetime"] == "20250115000000"

    def test_sentiment_tone_parsing(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "articles": [{"tone": "-2.5,3.0,5.5", "url": "http://x.com"}]
        })
        result = provider.get_articles("test")
        assert result[0]["sentiment"] == pytest.approx(-0.025)

    def test_empty_tone_returns_none(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "articles": [{"tone": "", "url": "http://x.com"}]
        })
        result = provider.get_articles("test")
        assert result[0]["sentiment"] is None

    def test_empty_articles(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={"articles": []})
        assert provider.get_articles("test") == []

    def test_none_response_raises(self):
        provider = self._make_provider()
        provider.session.get.return_value = None
        from sources.news.providers.base import ProviderError
        with pytest.raises(ProviderError):
            provider.get_articles("test")


# ===================================================================
# NewsAPI Provider — 7 tests
# ===================================================================

class TestNewsApiProvider:
    def _make_provider(self):
        with patch("sources.news.providers.newsapi_provider.RequestSession"):
            from sources.news.providers.newsapi_provider import NewsApiProvider
            return NewsApiProvider(api_key="test-key")

    def test_article_parsing(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "status": "ok",
            "articles": [{
                "source": {"name": "CNN"},
                "title": "Economy booming",
                "description": "GDP up",
                "url": "http://cnn.com/1",
                "publishedAt": "2025-01-15T10:00:00Z",
                "urlToImage": "http://img.com/1.jpg",
            }]
        })
        result = provider.get_articles("economy")
        assert len(result) == 1
        a = result[0]
        assert a["provider"] == "newsapi"
        assert a["source_name"] == "CNN"
        assert a["title"] == "Economy booming"

    def test_30day_date_clamping(self):
        """Old from_date gets clamped to 30 days ago."""
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={"status": "ok", "articles": []})
        provider.get_articles("test", from_date="2020-01-01")
        _, kwargs = provider.session.get.call_args
        # The "from" param should NOT be 2020-01-01 — it gets clamped
        assert kwargs["params"]["from"] > "2020-01-01"

    def test_recent_date_not_clamped(self):
        """A recent from_date should pass through unchanged."""
        import datetime
        yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={"status": "ok", "articles": []})
        provider.get_articles("test", from_date=yesterday)
        _, kwargs = provider.session.get.call_args
        assert kwargs["params"]["from"] == yesterday

    def test_rate_limited_raises(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "status": "error", "code": "rateLimited", "message": "limit hit"
        })
        from sources.news.providers.base import RateLimitError
        with pytest.raises(RateLimitError):
            provider.get_articles("test")

    def test_api_error_raises(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "status": "error", "code": "apiKeyInvalid", "message": "bad key"
        })
        from sources.news.providers.base import ProviderError
        with pytest.raises(ProviderError):
            provider.get_articles("test")

    def test_missing_key_raises(self):
        with patch("sources.news.providers.newsapi_provider.RequestSession"):
            with patch.dict("os.environ", {}, clear=True):
                from sources.news.providers.newsapi_provider import NewsApiProvider
                with pytest.raises(ValueError, match="NewsAPI key required"):
                    NewsApiProvider(api_key="")

    def test_null_source(self):
        """When article source is None, source_name should be empty string."""
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "status": "ok",
            "articles": [{"source": None, "title": "T", "url": "http://x.com", "publishedAt": "2025-01-01"}]
        })
        result = provider.get_articles("test")
        assert result[0]["source_name"] == ""


# ===================================================================
# Finnhub Provider — 8 tests
# ===================================================================

class TestFinnhubProvider:
    def _make_provider(self):
        with patch("sources.news.providers.finnhub_provider.RequestSession"):
            from sources.news.providers.finnhub_provider import FinnhubProvider
            return FinnhubProvider(api_key="test-key")

    def _make_finnhub_article(self, headline="Economy news", summary="GDP growth strong",
                               url="http://finnhub.com/1", datetime_ts=1705312800,
                               source="Reuters", category="general"):
        return {
            "headline": headline,
            "summary": summary,
            "url": url,
            "datetime": datetime_ts,
            "source": source,
            "category": category,
        }

    def test_client_side_query_filtering(self):
        """Only articles matching query terms are returned."""
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data=[
            self._make_finnhub_article(headline="Economy grows", url="http://x.com/1"),
            self._make_finnhub_article(headline="Sports update", summary="football scores", url="http://x.com/2"),
        ])
        result = provider.get_articles("economy", from_date="2020-01-01", to_date="2030-12-31")
        assert len(result) == 1
        assert result[0]["title"] == "Economy grows"

    def test_date_range_filtering(self):
        """Articles outside date range are excluded."""
        provider = self._make_provider()
        # ts 1705312800 = 2024-01-15
        provider.session.get.return_value = _make_response(json_data=[
            self._make_finnhub_article(headline="economy news", datetime_ts=1705312800, url="http://x.com/1"),
        ])
        result = provider.get_articles("economy", from_date="2025-01-01", to_date="2025-12-31")
        assert len(result) == 0

    def test_timestamp_to_iso(self):
        provider = self._make_provider()
        # 1705312800 = 2024-01-15T10:00:00Z
        provider.session.get.return_value = _make_response(json_data=[
            self._make_finnhub_article(headline="economy news", datetime_ts=1705312800),
        ])
        result = provider.get_articles("economy", from_date="2024-01-01", to_date="2024-12-31")
        assert "2024-01-15" in result[0]["published_at"]

    def test_429_raises_rate_limit(self):
        provider = self._make_provider()
        resp = _make_response(status_code=429, json_data=[])
        resp.__bool__ = lambda self: True  # Finnhub checks status_code directly
        provider.session.get.return_value = resp
        from sources.news.providers.base import RateLimitError
        with pytest.raises(RateLimitError):
            provider.get_articles("economy")

    def test_error_dict_raises(self):
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={"error": "invalid token"})
        from sources.news.providers.base import ProviderError
        with pytest.raises(ProviderError):
            provider.get_articles("economy")

    def test_missing_key_raises(self):
        with patch("sources.news.providers.finnhub_provider.RequestSession"):
            with patch.dict("os.environ", {}, clear=True):
                from sources.news.providers.finnhub_provider import FinnhubProvider
                with pytest.raises(ValueError, match="Finnhub API key required"):
                    FinnhubProvider(api_key="")

    def test_non_list_returns_empty(self):
        """When API returns a non-list (e.g. error obj without 'error' key), return []."""
        provider = self._make_provider()
        provider.session.get.return_value = _make_response(json_data={"something": "unexpected"})
        result = provider.get_articles("economy")
        assert result == []

    def test_limit_respected(self):
        provider = self._make_provider()
        articles = [
            self._make_finnhub_article(
                headline=f"economy article {i}", url=f"http://x.com/{i}", datetime_ts=1705312800
            )
            for i in range(10)
        ]
        provider.session.get.return_value = _make_response(json_data=articles)
        result = provider.get_articles("economy", from_date="2024-01-01", to_date="2024-12-31", limit=3)
        assert len(result) == 3
