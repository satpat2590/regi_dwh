"""Tests for the NLP sentiment enrichment pipeline."""

import pytest
from sources.news.enrich_sentiment import SentimentEnricher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def enricher(tmp_db):
    """SentimentEnricher backed by a temp DB."""
    e = SentimentEnricher.__new__(SentimentEnricher)
    e.db = tmp_db
    e.batch_size = 500
    e.analyzer = SentimentEnricher._init_vader()
    return e


def _insert_article(db, url, title="Title", description="Desc", provider="test",
                     sentiment=None, sentiment_source=""):
    """Helper to insert a raw article into the temp DB."""
    db.conn.execute(
        """INSERT INTO news_articles
            (provider, source_name, title, description, url,
             published_at, fetched_at, category, sentiment, image_url,
             sentiment_label, sentiment_source)
        VALUES (?, '', ?, ?, ?, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z',
                '', ?, '', '', ?)""",
        (provider, title, description, url, sentiment, sentiment_source),
    )
    db.conn.commit()


# ---------------------------------------------------------------------------
# score() tests
# ---------------------------------------------------------------------------

class TestScore:
    def test_positive_text(self, enricher):
        result = enricher.score("This is an amazing, wonderful, great achievement!")
        assert result["compound"] > 0
        assert result["label"] == "positive"

    def test_negative_text(self, enricher):
        result = enricher.score("This is terrible, horrible, and absolutely awful.")
        assert result["compound"] < 0
        assert result["label"] == "negative"

    def test_neutral_text(self, enricher):
        result = enricher.score("The meeting is scheduled for Tuesday.")
        assert result["label"] == "neutral"
        assert -0.05 < result["compound"] < 0.05

    def test_empty_string(self, enricher):
        result = enricher.score("")
        assert result["label"] == "neutral"
        assert result["compound"] == 0.0

    def test_label_threshold_positive(self, enricher):
        """Compound exactly at 0.05 should be positive."""
        # We can't easily force VADER to a specific score, so just verify
        # the threshold logic with a known-positive string
        result = enricher.score("good")
        assert result["compound"] >= 0.05
        assert result["label"] == "positive"

    def test_label_threshold_negative(self, enricher):
        result = enricher.score("bad")
        assert result["compound"] <= -0.05
        assert result["label"] == "negative"


# ---------------------------------------------------------------------------
# DB method tests
# ---------------------------------------------------------------------------

class TestDBMethods:
    def test_get_unenriched_articles(self, tmp_db):
        _insert_article(tmp_db, "https://a.com/1", sentiment_source="")
        _insert_article(tmp_db, "https://a.com/2", sentiment_source="vader")
        rows = tmp_db.get_unenriched_articles()
        assert len(rows) == 1
        assert rows[0]["id"] is not None

    def test_get_unenriched_articles_force(self, tmp_db):
        _insert_article(tmp_db, "https://a.com/1", sentiment_source="")
        _insert_article(tmp_db, "https://a.com/2", sentiment_source="vader")
        rows = tmp_db.get_unenriched_articles(force=True)
        assert len(rows) == 2

    def test_get_unenriched_articles_limit(self, tmp_db):
        for i in range(5):
            _insert_article(tmp_db, f"https://a.com/{i}")
        rows = tmp_db.get_unenriched_articles(limit=2)
        assert len(rows) == 2

    def test_update_article_sentiment(self, tmp_db):
        _insert_article(tmp_db, "https://a.com/1")
        rows = tmp_db.get_unenriched_articles()
        article_id = rows[0]["id"]

        tmp_db.update_article_sentiment(article_id, 0.75, "positive", "vader")
        tmp_db.conn.commit()

        result = tmp_db.query("SELECT sentiment, sentiment_label, sentiment_source FROM news_articles WHERE id = ?", (article_id,))
        assert result[0]["sentiment"] == 0.75
        assert result[0]["sentiment_label"] == "positive"
        assert result[0]["sentiment_source"] == "vader"


# ---------------------------------------------------------------------------
# enrich_articles() integration tests
# ---------------------------------------------------------------------------

class TestEnrichArticles:
    def test_enriches_null_articles(self, enricher):
        _insert_article(enricher.db, "https://a.com/1", title="Great news", description="Economy booming")
        _insert_article(enricher.db, "https://a.com/2", title="Terrible crash", description="Markets plummet")

        count = enricher.enrich_articles()
        assert count == 2

        rows = enricher.db.query("SELECT sentiment, sentiment_label, sentiment_source FROM news_articles ORDER BY id")
        assert all(r["sentiment_source"] == "vader" for r in rows)
        assert all(r["sentiment"] is not None for r in rows)
        assert all(r["sentiment_label"] in ("positive", "negative", "neutral") for r in rows)

    def test_skips_already_scored(self, enricher):
        _insert_article(enricher.db, "https://a.com/1", sentiment=0.5, sentiment_source="gdelt_tone")
        _insert_article(enricher.db, "https://a.com/2", title="New article")

        count = enricher.enrich_articles()
        assert count == 1

        rows = enricher.db.query("SELECT sentiment_source FROM news_articles ORDER BY id")
        assert rows[0]["sentiment_source"] == "gdelt_tone"
        assert rows[1]["sentiment_source"] == "vader"

    def test_force_rescores_all(self, enricher):
        _insert_article(enricher.db, "https://a.com/1", sentiment=0.5, sentiment_source="gdelt_tone")

        count = enricher.enrich_articles(force=True)
        assert count == 1

        rows = enricher.db.query("SELECT sentiment_source FROM news_articles")
        assert rows[0]["sentiment_source"] == "vader"

    def test_empty_title_and_description(self, enricher):
        _insert_article(enricher.db, "https://a.com/1", title="", description="")

        count = enricher.enrich_articles()
        assert count == 1

        rows = enricher.db.query("SELECT sentiment, sentiment_label FROM news_articles")
        assert rows[0]["sentiment_label"] == "neutral"

    def test_no_articles_returns_zero(self, enricher):
        count = enricher.enrich_articles()
        assert count == 0


# ---------------------------------------------------------------------------
# GDELT normalization test
# ---------------------------------------------------------------------------

class TestGdeltNormalization:
    def test_tone_50_normalizes_to_half(self):
        from sources.news.providers.gdelt_provider import GdeltProvider
        provider = GdeltProvider()
        article = {"tone": "50,30,20,10"}
        result = provider._extract_sentiment(article)
        assert result == pytest.approx(0.5)

    def test_tone_negative_200_clamps_to_minus_one(self):
        from sources.news.providers.gdelt_provider import GdeltProvider
        provider = GdeltProvider()
        article = {"tone": "-200,0,100,100"}
        result = provider._extract_sentiment(article)
        assert result == -1.0

    def test_tone_positive_200_clamps_to_one(self):
        from sources.news.providers.gdelt_provider import GdeltProvider
        provider = GdeltProvider()
        article = {"tone": "200,100,0,100"}
        result = provider._extract_sentiment(article)
        assert result == 1.0
