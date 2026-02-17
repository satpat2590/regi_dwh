"""
Equity Market Data Pipeline (Multi-Provider)

Fetches daily OHLCV prices, dividends, splits, and valuation ratios
from multiple data providers (Alpha Vantage, Polygon.io, etc.),
and persists to SQLite + Excel.

Usage:
    python sources/equity/pipeline.py                              # Tickers from input.txt
    python sources/equity/pipeline.py --tickers AAPL MSFT JPM      # Specific tickers
    python sources/equity/pipeline.py --input-file my_tickers.txt  # Custom file
    python sources/equity/pipeline.py --force                      # Bypass cache
    python sources/equity/pipeline.py --provider alpha_vantage     # Specify provider
"""

import argparse
import datetime
import os
import sys
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.excel_formatter import ExcelFormatter
from utils.input_parser import parse_input_file, DEFAULT_INPUT_FILE
from utils import log
from database import DatabaseManager
from sources.equity.providers.alpha_vantage import AlphaVantageProvider
from sources.equity.providers.base import RateLimitError, DataNotFoundError, ProviderError

logger = log.setup_verbose_logging("equity")


class Equity:
    """
    Equity market data extractor using multiple providers.

    Fetches daily OHLCV prices, dividends, splits, and key valuation
    ratios for a universe of tickers. Supports Alpha Vantage, Polygon.io, etc.
    """

    CACHE_FRESHNESS_DAYS = 1  # prices are daily, so 1 day = fresh

    def __init__(self, tickers: list[str] = None, force: bool = False, provider_name: str = "alpha_vantage"):
        self.start = datetime.datetime.now()
        self.force = force

        log.header(f"EQUITY EXTRACTION: Fetching Market Data ({provider_name})")

        self.tickers = tickers if tickers else ['AAPL', 'MSFT', 'GOOGL']
        log.step(f"Processing {len(self.tickers)} tickers: {', '.join(self.tickers)}")

        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        # Initialize provider
        self.provider = self._init_provider(provider_name)
        if not self.provider:
            log.warn("No provider available, skipping equity extraction")
            return
        log.info(f"Using provider: {self.provider.name}")

        # Storage for all fetched data
        self.all_prices = []
        self.all_dividends = []
        self.all_splits = []
        self.all_info = []

        # Query DB for latest price dates to support incremental updates
        db = DatabaseManager()
        self._ticker_latest = {}
        for t in self.tickers:
            self._ticker_latest[t] = db.get_ticker_latest_price(t)
        db.close()

        # Process each ticker
        for i, ticker in enumerate(self.tickers, 1):
            if not self.force and self._ticker_latest.get(ticker):
                latest = datetime.datetime.strptime(self._ticker_latest[ticker], '%Y-%m-%d')
                age = (datetime.datetime.now() - latest).days
                if age <= self.CACHE_FRESHNESS_DAYS:
                    log.progress(
                        i, len(self.tickers), ticker,
                        f"{log.C.DIM}cached (latest price {self._ticker_latest[ticker]}, {age}d ago){log.C.RESET}"
                    )
                    continue

            self._fetch_and_process(ticker, i, len(self.tickers))

        # Persist results
        log.step("Saving outputs...")
        self.save_to_database()
        self.save_to_excel()

        elapsed = datetime.datetime.now() - self.start
        log.summary_table("Equity Extraction Summary", [
            ("Tickers processed", str(len(self.tickers))),
            ("Price records", str(len(self.all_prices))),
            ("Dividend records", str(len(self.all_dividends))),
            ("Split records", str(len(self.all_splits))),
            ("Info snapshots", str(len(self.all_info))),
            ("Elapsed", str(elapsed)),
        ])
        log.ok("Equity extraction complete")

    def _init_provider(self, provider_name: str):
        """Initialize the specified data provider."""
        if provider_name.lower() == "alpha_vantage":
            try:
                return AlphaVantageProvider()
            except ValueError as e:
                log.warn(f"Alpha Vantage provider initialization failed: {e}")
                log.warn("Equity extraction will be skipped. Set ALPHA_VANTAGE_API_KEY environment variable to enable.")
                return None
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def _fetch_and_process(self, ticker: str, idx: int, total: int):
        """Fetch all market data for a single ticker using the provider."""
        try:
            # Prices
            prices = self.provider.get_historical_prices(ticker, period="5y")
            self.all_prices.extend(prices)

            # Dividends
            divs = self.provider.get_dividends(ticker)
            self.all_dividends.extend(divs)

            # Splits
            splits = self.provider.get_splits(ticker)
            self.all_splits.extend(splits)

            # Info snapshot
            info = self.provider.get_info(ticker)
            if info:
                self.all_info.append(info)

            log.progress(
                idx, total, ticker,
                f"{log.C.OK}{len(prices):,} prices{log.C.RESET} | "
                f"{len(divs)} dividends | {len(splits)} splits"
            )
        
        except RateLimitError as e:
            log.err(f"{ticker}: Rate limit exceeded - {e}")
            logger.warning(f"{ticker}: Rate limit - {e}")
        
        except DataNotFoundError as e:
            log.err(f"{ticker}: Data not available - {e}")
            logger.warning(f"{ticker}: No data - {e}")
        
        except ProviderError as e:
            log.err(f"{ticker}: Provider error - {e}")
            logger.error(f"{ticker}: {e}")
        
        except Exception as e:
            log.err(f"{ticker}: {e}")
            logger.exception(f"Failed to fetch data for {ticker}")


    def save_to_database(self):
        """Write all collected equity data to the SQLite database."""
        if not any([self.all_prices, self.all_dividends, self.all_splits, self.all_info]):
            log.warn("No equity data to write to database")
            return

        db = DatabaseManager()

        if self.all_prices:
            n = db.upsert_equity_prices(self.all_prices)
            log.info(f"Database: {n:,} price records")

        if self.all_dividends:
            n = db.upsert_equity_dividends(self.all_dividends)
            log.info(f"Database: {n:,} dividend records")

        if self.all_splits:
            n = db.upsert_equity_splits(self.all_splits)
            log.info(f"Database: {n:,} split records")

        if self.all_info:
            n = db.upsert_equity_info(self.all_info)
            log.info(f"Database: {n:,} info snapshots")

        db.close()
        log.ok(f"Database: equity data written to {db.db_path}")

    def save_to_excel(self):
        """Save equity summary and price stats to Excel."""
        ef = ExcelFormatter()

        # Equity_Summary sheet (from info snapshots)
        if self.all_info:
            info_df = pd.DataFrame(self.all_info)
            ef.add_to_sheet(info_df, sheet_name="Equity_Summary")
            log.info(f"Sheet: Equity_Summary ({len(info_df)} tickers)")

        # Price_Stats sheet (per-ticker aggregates)
        if self.all_prices:
            prices_df = pd.DataFrame(self.all_prices)
            stats = prices_df.groupby("ticker").agg(
                latest_date=("date", "max"),
                latest_close=("close", "last"),
                min_close=("close", "min"),
                max_close=("close", "max"),
                avg_volume=("volume", "mean"),
                total_records=("date", "count"),
            ).reset_index()
            stats["avg_volume"] = stats["avg_volume"].round(0).astype("Int64")
            ef.add_to_sheet(stats, sheet_name="Price_Stats")
            log.info(f"Sheet: Price_Stats ({len(stats)} tickers)")

        xlsx_name = f"EQUITY_DATA_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        ef.save(xlsx_name, self.data_dir)
        log.info(f"Excel: {os.path.join(self.data_dir, xlsx_name)}")


def main():
    parser = argparse.ArgumentParser(description="Fetch equity market data from multiple providers")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to process")
    parser.add_argument("--input-file", type=str, help="Path to file with ticker list (default: input.txt)")
    parser.add_argument("--force", action="store_true", help="Force re-fetch all tickers, ignoring cached data")
    parser.add_argument("--provider", type=str, default="alpha_vantage", 
                       help="Data provider to use (default: alpha_vantage)")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.input_file:
        tickers = parse_input_file(args.input_file)
    elif os.path.exists(DEFAULT_INPUT_FILE):
        tickers = parse_input_file()
        log.info(f"Reading tickers from {DEFAULT_INPUT_FILE}")
    else:
        tickers = None  # Will use default in Equity.__init__

    Equity(tickers=tickers, force=args.force, provider_name=args.provider)


if __name__ == "__main__":
    main()
