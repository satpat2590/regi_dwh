"""
FRED Macro Economic Data Pipeline

Fetches economic indicator time series from the Federal Reserve Economic Data
(FRED) API and persists to SQLite.

Usage:
    python sources/fred/pipeline.py                              # Default series from config
    python sources/fred/pipeline.py --series GDP UNRATE          # Specific series
    python sources/fred/pipeline.py --days 3650                  # 10 years of history
    python sources/fred/pipeline.py --force                      # Ignore cache
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import List

sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(os.path.join(Path(__file__).parent.parent.parent, ".env"))

from utils import log
from database import DatabaseManager
from sources.fred.provider import FredProvider

logger = log.setup_verbose_logging("fred")


class FredPipeline:
    """
    FRED macro economic data extractor.

    Fetches series metadata and observations for a set of economic indicators
    from the FRED API and persists to SQLite.
    """

    CACHE_FRESHNESS_HOURS = 24

    def __init__(
        self,
        series_ids: List[str] = None,
        days: int = 3650,
        force: bool = False,
    ):
        self.start = datetime.datetime.now()
        self.force = force
        self.days = days

        log.header("FRED EXTRACTION: Macro Economic Indicators")

        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Load series list from config if not provided
        if not series_ids:
            series_ids = self._load_config()

        self.series_ids = series_ids
        log.step(f"Processing {len(self.series_ids)} series: {', '.join(self.series_ids[:5])}{'...' if len(self.series_ids) > 5 else ''}")

        # Initialize provider
        self.provider = FredProvider()
        log.info(f"Using provider: {self.provider.name}")

        # Storage
        self.all_observations = []
        self.meta_count = 0

        # Query DB for latest observation dates (incremental)
        db = DatabaseManager()
        self._series_latest = {}
        for sid in self.series_ids:
            self._series_latest[sid] = db.get_fred_latest_observation(sid)
        db.close()

        # Process each series
        for i, sid in enumerate(self.series_ids, 1):
            self._fetch_series(sid, i, len(self.series_ids))

        # Persist
        log.step("Saving to database...")
        self._save_to_database()

        elapsed = datetime.datetime.now() - self.start
        log.summary_table("FRED Extraction Summary", [
            ("Series processed", str(len(self.series_ids))),
            ("Metadata saved", str(self.meta_count)),
            ("Observations", str(len(self.all_observations))),
            ("Elapsed", str(elapsed)),
        ])
        log.ok("FRED extraction complete")

    def _load_config(self) -> List[str]:
        """Load default series list from config/fred_series.json."""
        config_path = os.path.join(self.base_dir, "config", "fred_series.json")
        if not os.path.exists(config_path):
            log.warn(f"Config not found: {config_path}")
            return ["GDP", "UNRATE", "CPIAUCSL", "FEDFUNDS", "DGS10"]

        with open(config_path, "r") as f:
            config = json.load(f)

        ids = [s["id"] for s in config.get("series", [])]
        log.info(f"Loaded {len(ids)} series from config")
        return ids

    def _fetch_series(self, series_id: str, idx: int, total: int):
        """Fetch metadata + observations for a single FRED series."""
        try:
            # Check cache freshness (use latest observation date as proxy)
            if not self.force and self._series_latest.get(series_id):
                latest = self._series_latest[series_id]
                days_old = (datetime.date.today() - datetime.date.fromisoformat(latest)).days
                if days_old <= 1:
                    log.progress(idx, total, series_id, f"{log.C.DIM}cached (latest {latest}){log.C.RESET}")
                    return

            # Metadata
            meta = self.provider.get_series_info(series_id)
            self.meta_count += 1

            # Observations — incremental if we have prior data
            start_date = None
            if self._series_latest.get(series_id) and not self.force:
                start_date = self._series_latest[series_id]
            else:
                start_date = (datetime.date.today() - datetime.timedelta(days=self.days)).isoformat()

            observations = self.provider.get_observations(
                series_id,
                start_date=start_date,
            )
            self.all_observations.extend(observations)

            # Save metadata immediately
            db = DatabaseManager()
            db.upsert_fred_series_meta(meta)
            db.close()

            log.progress(
                idx, total, series_id,
                f"{log.C.OK}{len(observations)} observations{log.C.RESET}"
            )

        except Exception as e:
            log.err(f"{series_id}: {e}")
            logger.exception(f"Failed to fetch FRED series {series_id}")

    def _save_to_database(self):
        """Write all observations to the database."""
        db = DatabaseManager()
        if self.all_observations:
            n = db.upsert_fred_observations(self.all_observations)
            log.info(f"Saved {n} observation records to database")
        else:
            log.warn("No FRED observation data to write")
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch FRED macro economic data")
    parser.add_argument("--series", nargs="+", help="Specific FRED series IDs (e.g., GDP UNRATE)")
    parser.add_argument("--days", type=int, default=3650, help="Days of history to fetch (default: 3650 = ~10y)")
    parser.add_argument("--force", action="store_true", help="Force re-fetch, ignoring cache")
    args = parser.parse_args()

    FredPipeline(
        series_ids=args.series,
        days=args.days,
        force=args.force,
    )


if __name__ == "__main__":
    main()
