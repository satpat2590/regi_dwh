"""Tests for NewsPipeline — mocked providers + real DB."""

import datetime
import pytest
from unittest.mock import patch, MagicMock

from database import DatabaseManager
from sources.news.providers.base import RateLimitError, ProviderError


def _make_mock_provider(name, articles=None):
    """Create a mock news provider."""
    provider = MagicMock()
    provider.name = name
    provider.get_articles.return_value = articles or []
    provider.get_top_headlines.return_value = []
    return provider


@pytest.fixture
def pipeline_db(tmp_path):
    db_path = str(tmp_path / "news_pipeline.db")
    db = DatabaseManager(db_path=db_path)
    yield db, db_path
    db.close()


def _make_article(provider, url, title="Article"):
    return {
        "provider": provider,
        "source_name": "Test",
        "title": title,
        "description": "",
        "url": url,
        "published_at": "2025-01-15T10:00:00Z",
        "fetched_at": "2025-01-15T12:00:00Z",
        "category": "business",
        "sentiment": None,
        "topics": [],
        "image_url": "",
    }


class TestNewsPipeline:
    """Test NewsPipeline with mocked providers and real DB."""

    def _run_pipeline(self, db_path, providers, queries=None, force=True):
        queries = queries or ["economy"]
        with patch("sources.news.pipeline.DatabaseManager", side_effect=lambda *a, **kw: DatabaseManager(db_path=db_path)), \
             patch("sources.news.pipeline.log"), \
             patch("sources.news.pipeline.load_dotenv"), \
             patch("sources.news.pipeline.logger"):

            with patch("sources.news.pipeline.NewsPipeline._init_providers", return_value=providers):
                from sources.news.pipeline import NewsPipeline
                NewsPipeline(
                    queries=queries,
                    provider_name="all",
                    force=force,
                )

        return DatabaseManager(db_path=db_path)

    def test_url_dedup_across_providers(self, pipeline_db):
        """Same URL from two providers should appear only once."""
        db, db_path = pipeline_db
        p1 = _make_mock_provider("gdelt", [_make_article("gdelt", "http://shared.com/1")])
        p2 = _make_mock_provider("newsapi", [_make_article("newsapi", "http://shared.com/1")])
        result_db = self._run_pipeline(db_path, [p1, p2])
        rows = result_db.query("SELECT * FROM news_articles")
        assert len(rows) == 1
        result_db.close()

    def test_multi_provider_aggregation(self, pipeline_db):
        db, db_path = pipeline_db
        p1 = _make_mock_provider("gdelt", [_make_article("gdelt", "http://gdelt.com/1")])
        p2 = _make_mock_provider("newsapi", [_make_article("newsapi", "http://newsapi.com/1")])
        result_db = self._run_pipeline(db_path, [p1, p2])
        rows = result_db.query("SELECT * FROM news_articles")
        assert len(rows) == 2
        result_db.close()

    def test_articles_saved_to_db(self, pipeline_db):
        db, db_path = pipeline_db
        articles = [_make_article("gdelt", f"http://x.com/{i}", title=f"Art {i}") for i in range(3)]
        p = _make_mock_provider("gdelt", articles)
        result_db = self._run_pipeline(db_path, [p])
        rows = result_db.query("SELECT * FROM news_articles")
        assert len(rows) == 3
        result_db.close()

    def test_cache_freshness_skips_provider(self, pipeline_db):
        """If provider has fresh data, should not call get_articles."""
        db, db_path = pipeline_db
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.upsert_news_articles([_make_article("gdelt", "http://cached.com/1")])
        db.conn.execute("UPDATE news_articles SET fetched_at = ?", (now,))
        db.conn.commit()

        p = _make_mock_provider("gdelt", [_make_article("gdelt", "http://new.com/1")])
        self._run_pipeline(db_path, [p], force=False)
        p.get_articles.assert_not_called()

    def test_rate_limit_handled(self, pipeline_db):
        """RateLimitError should not crash the pipeline."""
        db, db_path = pipeline_db
        p = _make_mock_provider("newsapi")
        p.get_articles.side_effect = RateLimitError("limit hit")
        self._run_pipeline(db_path, [p])

    def test_provider_error_handled(self, pipeline_db):
        """ProviderError should not crash the pipeline."""
        db, db_path = pipeline_db
        p = _make_mock_provider("newsapi")
        p.get_articles.side_effect = ProviderError("API error")
        self._run_pipeline(db_path, [p])

    def test_empty_query_list(self, pipeline_db):
        """Empty query list should not crash."""
        db, db_path = pipeline_db
        p = _make_mock_provider("gdelt")
        self._run_pipeline(db_path, [p], queries=[])
