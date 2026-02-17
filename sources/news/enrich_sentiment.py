"""
NLP Sentiment Enrichment for News Articles.

Scores unenriched articles using VADER sentiment analysis and writes
the results back to the database. Designed to run as a post-ingest step.

Usage:
    python sources/news/enrich_sentiment.py                  # Enrich all NULL articles
    python sources/news/enrich_sentiment.py --limit 1000     # Batch limit
    python sources/news/enrich_sentiment.py --force           # Re-score all (including GDELT)
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from database import DatabaseManager
from utils import log


class SentimentEnricher:
    """Scores news articles with VADER sentiment and updates the DB."""

    def __init__(self, db_path: str | None = None, batch_size: int = 500):
        self.db = DatabaseManager(db_path) if db_path else DatabaseManager()
        self.batch_size = batch_size
        self.analyzer = self._init_vader()

    @staticmethod
    def _init_vader() -> SentimentIntensityAnalyzer:
        return SentimentIntensityAnalyzer()

    def score(self, text: str) -> dict:
        """Score a text string with VADER.

        Returns:
            dict with 'compound' (float, -1 to +1) and 'label' (str).
        """
        scores = self.analyzer.polarity_scores(text)
        compound = scores["compound"]
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        return {"compound": compound, "label": label}

    def enrich_articles(self, limit: int | None = None, force: bool = False) -> int:
        """Fetch unenriched articles, score them, and update the DB.

        Args:
            limit: Max articles to process (None = all).
            force: If True, re-score ALL articles including already-scored ones.

        Returns:
            Number of articles enriched.
        """
        articles = self.db.get_unenriched_articles(limit=limit, force=force)
        if not articles:
            return 0

        enriched = 0
        for i, article in enumerate(articles):
            title = article.get("title") or ""
            description = article.get("description") or ""
            text = (title + " " + description).strip()

            result = self.score(text)
            self.db.update_article_sentiment(
                article_id=article["id"],
                sentiment=result["compound"],
                label=result["label"],
                source="vader",
            )
            enriched += 1

            # Commit in batches
            if enriched % self.batch_size == 0:
                self.db.conn.commit()

        # Final commit
        self.db.conn.commit()
        return enriched


def main():
    parser = argparse.ArgumentParser(description="Enrich news articles with VADER sentiment")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to enrich")
    parser.add_argument("--force", action="store_true", help="Re-score all articles (including already scored)")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite database")
    args = parser.parse_args()

    log.header("NLP Sentiment Enrichment")

    enricher = SentimentEnricher(db_path=args.db_path)

    mode = "force (re-score all)" if args.force else "unenriched only"
    log.info(f"Mode: {mode}")
    if args.limit:
        log.info(f"Limit: {args.limit} articles")

    count = enricher.enrich_articles(limit=args.limit, force=args.force)

    if count > 0:
        log.ok(f"Enriched {count} articles with VADER sentiment")
    else:
        log.info("No articles to enrich")

    enricher.db.close()


if __name__ == "__main__":
    main()
