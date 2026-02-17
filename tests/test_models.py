"""Tests for Pydantic data models (NewsArticle, FredSeriesMeta, FredObservation)."""

import pytest
from pydantic import ValidationError

from models import NewsArticle, FredSeriesMeta, FredObservation


# ---------------------------------------------------------------------------
# NewsArticle
# ---------------------------------------------------------------------------

class TestNewsArticle:
    def test_required_fields(self):
        a = NewsArticle(provider="gdelt", title="T", url="http://x.com", published_at="2025-01-01")
        assert a.provider == "gdelt"
        assert a.title == "T"
        assert a.url == "http://x.com"
        assert a.published_at == "2025-01-01"

    def test_optional_sentiment_defaults_none(self):
        a = NewsArticle(provider="p", title="T", url="http://x.com", published_at="2025-01-01")
        assert a.sentiment is None

    def test_topics_defaults_empty(self):
        a = NewsArticle(provider="p", title="T", url="http://x.com", published_at="2025-01-01")
        assert a.topics == []

    def test_all_optional_defaults(self):
        a = NewsArticle(provider="p", title="T", url="http://x.com", published_at="2025-01-01")
        assert a.source_name == ""
        assert a.description == ""
        assert a.fetched_at == ""
        assert a.category == ""
        assert a.image_url == ""

    def test_missing_provider_raises(self):
        with pytest.raises(ValidationError):
            NewsArticle(title="T", url="http://x.com", published_at="2025-01-01")

    def test_missing_title_raises(self):
        with pytest.raises(ValidationError):
            NewsArticle(provider="p", url="http://x.com", published_at="2025-01-01")

    def test_missing_url_raises(self):
        with pytest.raises(ValidationError):
            NewsArticle(provider="p", title="T", published_at="2025-01-01")


# ---------------------------------------------------------------------------
# FredSeriesMeta
# ---------------------------------------------------------------------------

class TestFredSeriesMeta:
    def test_required_series_id(self):
        m = FredSeriesMeta(series_id="GDP")
        assert m.series_id == "GDP"

    def test_defaults_empty_strings(self):
        m = FredSeriesMeta(series_id="GDP")
        assert m.title == ""
        assert m.units == ""
        assert m.frequency == ""
        assert m.seasonal_adj == ""
        assert m.last_updated == ""
        assert m.notes == ""

    def test_missing_series_id_raises(self):
        with pytest.raises(ValidationError):
            FredSeriesMeta()


# ---------------------------------------------------------------------------
# FredObservation
# ---------------------------------------------------------------------------

class TestFredObservation:
    def test_required_fields(self):
        o = FredObservation(series_id="GDP", date="2024-01-01", value=27000.0)
        assert o.series_id == "GDP"
        assert o.date == "2024-01-01"
        assert o.value == 27000.0

    def test_value_optional_none(self):
        o = FredObservation(series_id="GDP", date="2024-01-01")
        assert o.value is None
