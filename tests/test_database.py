"""Tests for DatabaseManager — news and FRED methods with real SQLite in tmpdir."""

import pytest

from database import DatabaseManager


# ---------------------------------------------------------------------------
# News Articles
# ---------------------------------------------------------------------------

class TestUpsertNewsArticles:
    def test_single_insert(self, tmp_db, sample_news_article):
        a = sample_news_article()
        n = tmp_db.upsert_news_articles([a])
        assert n == 1
        rows = tmp_db.query("SELECT * FROM news_articles")
        assert len(rows) == 1
        assert rows[0]["title"] == "Test Article Title"

    def test_duplicate_url_skipped(self, tmp_db, sample_news_article):
        a = sample_news_article()
        tmp_db.upsert_news_articles([a])
        n = tmp_db.upsert_news_articles([a])
        assert n == 0
        rows = tmp_db.query("SELECT * FROM news_articles")
        assert len(rows) == 1

    def test_multiple_unique(self, tmp_db, sample_news_article):
        a1 = sample_news_article(url="http://a.com/1")
        a2 = sample_news_article(url="http://a.com/2")
        n = tmp_db.upsert_news_articles([a1, a2])
        assert n == 2

    def test_topics_junction_table(self, tmp_db, sample_news_article):
        a = sample_news_article(topics=["economy", "fed"])
        tmp_db.upsert_news_articles([a])
        topics = tmp_db.query("SELECT topic FROM news_article_topics ORDER BY topic")
        assert [t["topic"] for t in topics] == ["economy", "fed"]

    def test_empty_topics(self, tmp_db, sample_news_article):
        a = sample_news_article(topics=[])
        tmp_db.upsert_news_articles([a])
        topics = tmp_db.query("SELECT * FROM news_article_topics")
        assert len(topics) == 0

    def test_null_sentiment(self, tmp_db, sample_news_article):
        a = sample_news_article(sentiment=None)
        tmp_db.upsert_news_articles([a])
        rows = tmp_db.query("SELECT sentiment FROM news_articles")
        assert rows[0]["sentiment"] is None

    def test_float_sentiment(self, tmp_db, sample_news_article):
        a = sample_news_article(sentiment=-2.5)
        tmp_db.upsert_news_articles([a])
        rows = tmp_db.query("SELECT sentiment FROM news_articles")
        assert rows[0]["sentiment"] == pytest.approx(-2.5)


class TestGetNewsLatestFetch:
    def test_empty_returns_none(self, tmp_db):
        assert tmp_db.get_news_latest_fetch("gdelt") is None

    def test_returns_max_fetched_at(self, tmp_db, sample_news_article):
        a1 = sample_news_article(url="http://a.com/1", fetched_at="2025-01-10T00:00:00Z")
        a2 = sample_news_article(url="http://a.com/2", fetched_at="2025-01-15T00:00:00Z")
        tmp_db.upsert_news_articles([a1, a2])
        assert tmp_db.get_news_latest_fetch("test") == "2025-01-15T00:00:00Z"

    def test_filters_by_provider(self, tmp_db, sample_news_article):
        a1 = sample_news_article(provider="gdelt", url="http://a.com/1", fetched_at="2025-01-15T00:00:00Z")
        a2 = sample_news_article(provider="newsapi", url="http://a.com/2", fetched_at="2025-01-10T00:00:00Z")
        tmp_db.upsert_news_articles([a1, a2])
        assert tmp_db.get_news_latest_fetch("gdelt") == "2025-01-15T00:00:00Z"
        assert tmp_db.get_news_latest_fetch("newsapi") == "2025-01-10T00:00:00Z"


# ---------------------------------------------------------------------------
# FRED Series Meta
# ---------------------------------------------------------------------------

class TestUpsertFredSeriesMeta:
    def test_insert(self, tmp_db, sample_fred_meta):
        n = tmp_db.upsert_fred_series_meta(sample_fred_meta)
        assert n == 1
        rows = tmp_db.query("SELECT * FROM fred_series_meta WHERE series_id = 'GDP'")
        assert rows[0]["title"] == "Gross Domestic Product"

    def test_replace_on_conflict(self, tmp_db, sample_fred_meta):
        tmp_db.upsert_fred_series_meta(sample_fred_meta)
        updated = dict(sample_fred_meta, title="Updated GDP Title")
        tmp_db.upsert_fred_series_meta(updated)
        rows = tmp_db.query("SELECT * FROM fred_series_meta WHERE series_id = 'GDP'")
        assert rows[0]["title"] == "Updated GDP Title"


# ---------------------------------------------------------------------------
# FRED Observations
# ---------------------------------------------------------------------------

class TestUpsertFredObservations:
    def test_insert_with_fk(self, tmp_db, sample_fred_meta, sample_fred_observations):
        tmp_db.upsert_fred_series_meta(sample_fred_meta)
        n = tmp_db.upsert_fred_observations(sample_fred_observations)
        assert n == 3

    def test_null_value_stored(self, tmp_db, sample_fred_meta):
        tmp_db.upsert_fred_series_meta(sample_fred_meta)
        tmp_db.upsert_fred_observations([{"series_id": "GDP", "date": "2024-07-01", "value": None}])
        rows = tmp_db.query("SELECT value FROM fred_observations WHERE date = '2024-07-01'")
        assert rows[0]["value"] is None

    def test_duplicate_ignored(self, tmp_db, sample_fred_meta, sample_fred_observations):
        tmp_db.upsert_fred_series_meta(sample_fred_meta)
        tmp_db.upsert_fred_observations(sample_fred_observations)
        # Insert same data again
        tmp_db.upsert_fred_observations(sample_fred_observations)
        rows = tmp_db.query("SELECT * FROM fred_observations")
        assert len(rows) == 3


class TestGetFredLatestObservation:
    def test_empty_returns_none(self, tmp_db):
        assert tmp_db.get_fred_latest_observation("GDP") is None

    def test_returns_max_date(self, tmp_db, sample_fred_meta, sample_fred_observations):
        tmp_db.upsert_fred_series_meta(sample_fred_meta)
        tmp_db.upsert_fred_observations(sample_fred_observations)
        assert tmp_db.get_fred_latest_observation("GDP") == "2024-07-01"

    def test_filters_by_series_id(self, tmp_db, sample_fred_meta):
        tmp_db.upsert_fred_series_meta(sample_fred_meta)
        tmp_db.upsert_fred_series_meta({"series_id": "UNRATE", "title": "Unemployment"})
        tmp_db.upsert_fred_observations([
            {"series_id": "GDP", "date": "2024-01-01", "value": 27000.0},
            {"series_id": "UNRATE", "date": "2024-06-01", "value": 3.5},
        ])
        assert tmp_db.get_fred_latest_observation("GDP") == "2024-01-01"
        assert tmp_db.get_fred_latest_observation("UNRATE") == "2024-06-01"
