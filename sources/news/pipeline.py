"""
News Aggregation Pipeline (Multi-Provider)

Fetches news articles from multiple providers (NewsAPI, Finnhub, GDELT)
and persists to SQLite with deduplication by URL.

Usage:
    python sources/news/pipeline.py                                          # Default watchlist, all providers
    python sources/news/pipeline.py --queries "inflation" "GDP growth"       # Specific queries
    python sources/news/pipeline.py --provider gdelt                         # Single provider (no key needed)
    python sources/news/pipeline.py --provider all --days 3                  # All providers, 3 days
    python sources/news/pipeline.py --category business --force              # Force re-fetch
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(os.path.join(Path(__file__).parent.parent.parent, ".env"))

from utils import log
from database import DatabaseManager
from sources.news.providers.base import (
    RateLimitError,
    ProviderError,
    NoDataError,
)

logger = log.setup_verbose_logging("news")


class NewsPipeline:
    """
    News aggregation pipeline using multiple data providers.

    Fetches news articles for a set of macro-focused search queries
    from NewsAPI, Finnhub, and/or GDELT, then deduplicates by URL
    and persists to SQLite.
    """

    CACHE_FRESHNESS_HOURS = 6

    def __init__(
        self,
        queries: List[str] = None,
        provider_name: str = "all",
        category: str = "",
        days: int = 7,
        force: bool = False,
    ):
        self.start = datetime.datetime.now()
        self.force = force
        self.days = days
        self.category = category
        self.provider_name = provider_name

        log.header(f"NEWS EXTRACTION: Fetching Articles ({provider_name})")

        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Load queries from config if not provided
        if not queries:
            queries, self._query_categories = self._load_watchlist()
        else:
            self._query_categories = {q: category for q in queries}

        self.queries = queries
        log.step(f"Processing {len(self.queries)} queries with provider={provider_name}")

        # Initialize providers
        self.providers = self._init_providers(provider_name)
        log.info(f"Active providers: {', '.join(p.name for p in self.providers)}")

        # Storage — deduplicate by URL
        self._seen_urls = set()
        self.all_articles = []

        # Check cache freshness per provider
        db = DatabaseManager()
        self._provider_latest = {}
        for p in self.providers:
            self._provider_latest[p.name] = db.get_news_latest_fetch(p.name)
        db.close()

        # Fetch from each provider
        from_date = (datetime.date.today() - datetime.timedelta(days=self.days)).isoformat()
        to_date = datetime.date.today().isoformat()

        for provider in self.providers:
            if not self.force and self._is_cached(provider.name):
                log.info(f"{provider.name}: cached (< {self.CACHE_FRESHNESS_HOURS}h old), skipping")
                continue

            for i, query in enumerate(self.queries, 1):
                cat = self._query_categories.get(query, self.category)
                self._fetch_articles(provider, query, from_date, to_date, cat, i, len(self.queries))

        # Persist
        log.step("Saving to database...")
        self._save_to_database()

        elapsed = datetime.datetime.now() - self.start
        log.summary_table("News Extraction Summary", [
            ("Queries processed", str(len(self.queries))),
            ("Providers", ", ".join(p.name for p in self.providers)),
            ("Articles fetched", str(len(self.all_articles))),
            ("Unique URLs", str(len(self._seen_urls))),
            ("Elapsed", str(elapsed)),
        ])
        log.ok("News extraction complete")

    def _load_watchlist(self) -> tuple[List[str], dict]:
        """Load queries from config/news_watchlist.json."""
        config_path = os.path.join(self.base_dir, "config", "news_watchlist.json")
        if not os.path.exists(config_path):
            log.warn(f"Watchlist not found: {config_path}")
            defaults = ["federal reserve interest rates", "inflation CPI", "GDP economic growth"]
            return defaults, {q: "" for q in defaults}

        with open(config_path, "r") as f:
            config = json.load(f)

        queries = []
        categories = {}
        for item in config.get("queries", []):
            q = item["query"]
            queries.append(q)
            categories[q] = item.get("category", "")

        log.info(f"Loaded {len(queries)} queries from watchlist")
        return queries, categories

    def _init_providers(self, provider_name: str) -> list:
        """Initialize the requested providers."""
        providers = []

        if provider_name in ("all", "gdelt"):
            try:
                from sources.news.providers.gdelt_provider import GdeltProvider
                providers.append(GdeltProvider())
            except Exception as e:
                log.warn(f"Could not initialize GDELT provider: {e}")

        if provider_name in ("all", "newsapi"):
            try:
                from sources.news.providers.newsapi_provider import NewsApiProvider
                providers.append(NewsApiProvider())
            except ValueError as e:
                log.warn(f"Skipping NewsAPI (no key): {e}")
            except Exception as e:
                log.warn(f"Could not initialize NewsAPI provider: {e}")

        if provider_name in ("all", "finnhub"):
            try:
                from sources.news.providers.finnhub_provider import FinnhubProvider
                providers.append(FinnhubProvider())
            except ValueError as e:
                log.warn(f"Skipping Finnhub (no key): {e}")
            except Exception as e:
                log.warn(f"Could not initialize Finnhub provider: {e}")

        if not providers:
            raise RuntimeError(
                f"No providers available for '{provider_name}'. "
                "Check API keys in .env or use --provider gdelt (no key needed)."
            )

        return providers

    def _is_cached(self, provider_name: str) -> bool:
        """Check if provider data is fresh enough to skip."""
        latest = self._provider_latest.get(provider_name)
        if not latest:
            return False
        try:
            latest_dt = datetime.datetime.fromisoformat(latest.replace("Z", "+00:00"))
            age = datetime.datetime.now(datetime.timezone.utc) - latest_dt
            return age.total_seconds() / 3600 < self.CACHE_FRESHNESS_HOURS
        except (ValueError, TypeError):
            return False

    def _fetch_articles(
        self,
        provider,
        query: str,
        from_date: str,
        to_date: str,
        category: str,
        idx: int,
        total: int,
    ):
        """Fetch articles for a single query from a single provider."""
        try:
            articles = provider.get_articles(
                query=query,
                from_date=from_date,
                to_date=to_date,
                category=category,
            )

            # Deduplicate by URL
            new_count = 0
            for a in articles:
                url = a.get("url", "")
                if url and url not in self._seen_urls:
                    self._seen_urls.add(url)
                    self.all_articles.append(a)
                    new_count += 1

            log.progress(
                idx, total, f"{provider.name}/{query[:30]}",
                f"{log.C.OK}{new_count} new articles{log.C.RESET} ({len(articles)} total)"
            )

        except RateLimitError as e:
            log.warn(f"{provider.name}: Rate limit hit — {e}")
        except NoDataError:
            log.info(f"{provider.name}/{query}: No articles found")
        except ProviderError as e:
            log.err(f"{provider.name}/{query}: {e}")
        except Exception as e:
            log.err(f"{provider.name}/{query}: {e}")
            logger.exception(f"Failed to fetch news from {provider.name} for query '{query}'")

    def _save_to_database(self):
        """Write all collected articles to the database."""
        db = DatabaseManager()
        if self.all_articles:
            n = db.upsert_news_articles(self.all_articles)
            log.info(f"Saved {n} new articles to database ({len(self.all_articles)} attempted)")
        else:
            log.warn("No news articles to write")
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch news articles from multiple providers")
    parser.add_argument("--queries", nargs="+", help="Search queries (e.g., 'inflation CPI' 'GDP growth')")
    parser.add_argument("--provider", type=str, default="all",
                        help="News provider: newsapi, finnhub, gdelt, or all (default: all)")
    parser.add_argument("--category", type=str, default="",
                        help="Category filter for articles")
    parser.add_argument("--days", type=int, default=7,
                        help="Days of history to fetch (default: 7)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-fetch, ignoring cache")
    args = parser.parse_args()

    NewsPipeline(
        queries=args.queries,
        provider_name=args.provider,
        category=args.category,
        days=args.days,
        force=args.force,
    )


if __name__ == "__main__":
    main()
