"""
Crypto Market Data Pipeline (Multi-Provider)

Fetches cryptocurrency OHLCV prices, current prices, and coin information
from multiple data providers (Binance, Coinbase), and persists to SQLite + Excel.

Usage:
    python sources/crypto/pipeline.py                              # Default watchlist
    python sources/crypto/pipeline.py --symbols BTCUSDT ETHUSDT    # Specific symbols
    python sources/crypto/pipeline.py --provider binance           # Specify provider
    python sources/crypto/pipeline.py --provider coinbase          # Use Coinbase
    python sources/crypto/pipeline.py --interval 1h                # Custom interval
    python sources/crypto/pipeline.py --days 365                   # Lookback period
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.excel_formatter import ExcelFormatter
from utils import log
from database import DatabaseManager
from sources.crypto.providers.binance_provider import BinanceProvider
from sources.crypto.providers.coinbase_provider import CoinbaseProvider
from sources.crypto.providers.base import (
    RateLimitError,
    DataNotFoundError,
    ProviderError,
    InvalidSymbolError
)

logger = log.setup_verbose_logging("crypto")


class CryptoPipeline:
    """
    Cryptocurrency market data extractor using multiple providers.

    Fetches OHLCV prices, current prices, and coin information
    for a universe of cryptocurrencies. Supports Binance, Coinbase, etc.
    """

    CACHE_FRESHNESS_HOURS = 1  # Crypto moves fast, refresh hourly

    def __init__(
        self,
        symbols: List[str] = None,
        provider_name: str = "binance",
        interval: str = "1d",
        days: int = 365,
        force: bool = False
    ):
        self.start = datetime.datetime.now()
        self.force = force
        self.interval = interval
        self.days = days

        log.header(f"CRYPTO EXTRACTION: Fetching Market Data ({provider_name})")

        # Initialize directories BEFORE loading watchlist (which uses self.base_dir)
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        # Load watchlist if no symbols provided
        if not symbols:
            symbols = self._load_watchlist()

        self.symbols = symbols
        log.step(f"Processing {len(self.symbols)} symbols: {', '.join(self.symbols[:5])}{'...' if len(self.symbols) > 5 else ''}")

        # Initialize provider
        self.provider = self._init_provider(provider_name)
        log.info(f"Using provider: {self.provider.name}")

        # Storage for all fetched data
        self.all_prices = []
        self.all_info = []

        # Query DB for latest price timestamps to support incremental updates
        db = DatabaseManager()
        self._symbol_latest = {}
        for s in self.symbols:
            latest = db.get_crypto_latest_price(s, self.interval)
            self._symbol_latest[s] = latest
        db.close()

        # Process each symbol
        for i, symbol in enumerate(self.symbols, 1):
            if not self.force and self._symbol_latest.get(symbol):
                latest_ts = self._symbol_latest[symbol]
                age_hours = (datetime.datetime.now().timestamp() - latest_ts / 1000) / 3600
                if age_hours <= self.CACHE_FRESHNESS_HOURS:
                    log.progress(
                        i, len(self.symbols), symbol,
                        f"{log.C.DIM}cached (latest {age_hours:.1f}h ago){log.C.RESET}"
                    )
                    continue

            self._fetch_and_process(symbol, i, len(self.symbols))

        # Persist results
        log.step("Saving outputs...")
        self.save_to_database()
        self.save_to_excel()

        elapsed = datetime.datetime.now() - self.start
        log.summary_table("Crypto Extraction Summary", [
            ("Symbols processed", str(len(self.symbols))),
            ("Price records", str(len(self.all_prices))),
            ("Info snapshots", str(len(self.all_info))),
            ("Interval", self.interval),
            ("Elapsed", str(elapsed)),
        ])
        log.ok("Crypto extraction complete")

    def _load_watchlist(self) -> List[str]:
        """Load default watchlist from config file."""
        config_path = os.path.join(self.base_dir, "config", "crypto_watchlist.json")
        
        if not os.path.exists(config_path):
            log.warn(f"Watchlist not found: {config_path}")
            return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]  # Default fallback
        
        with open(config_path, "r") as f:
            config = json.load(f)
        
        symbols = [s["symbol"] for s in config.get("symbols", [])]
        log.info(f"Loaded {len(symbols)} symbols from watchlist")
        return symbols

    def _init_provider(self, provider_name: str):
        """Initialize the specified data provider."""
        if provider_name.lower() == "binance":
            # Default to US for now, could be configurable
            return BinanceProvider(tld="us")
        elif provider_name.lower() == "coinbase":
            return CoinbaseProvider()
        else:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Supported: binance, coinbase"
            )

    def _fetch_and_process(self, symbol: str, idx: int, total: int):
        """Fetch all market data for a single symbol using the provider."""
        try:
            # Calculate start date
            start_date = (datetime.datetime.now() - datetime.timedelta(days=self.days)).strftime("%Y-%m-%d")
            
            # Prices (OHLCV)
            prices = self.provider.get_historical_prices(
                symbol,
                interval=self.interval,
                start_date=start_date
            )
            self.all_prices.extend(prices)

            # Coin info
            info = self.provider.get_coin_info(symbol)
            if info:
                self.all_info.append(info)

            log.progress(
                idx, total, symbol,
                f"{log.C.OK}{len(prices):,} candles{log.C.RESET}"
            )
        
        except RateLimitError as e:
            log.err(f"{symbol}: Rate limit exceeded - {e}")
            logger.warning(f"{symbol}: Rate limit - {e}")
        
        except DataNotFoundError as e:
            log.err(f"{symbol}: Data not available - {e}")
            logger.warning(f"{symbol}: No data - {e}")
        
        except InvalidSymbolError as e:
            log.err(f"{symbol}: Invalid symbol - {e}")
            logger.warning(f"{symbol}: Invalid - {e}")
        
        except ProviderError as e:
            log.err(f"{symbol}: Provider error - {e}")
            logger.error(f"{symbol}: {e}")
        
        except Exception as e:
            log.err(f"{symbol}: {e}")
            logger.exception(f"Failed to fetch data for {symbol}")

    def save_to_database(self):
        """Write all collected crypto data to the SQLite database."""
        db = DatabaseManager()
        
        if self.all_prices:
            db.upsert_crypto_prices(self.all_prices)
            log.info(f"Saved {len(self.all_prices)} price records to database")
        else:
            log.warn("No crypto price data to write to database")
        
        if self.all_info:
            for info in self.all_info:
                db.upsert_crypto_info(info)
            log.info(f"Saved {len(self.all_info)} coin info records to database")
        
        db.close()

    def save_to_excel(self):
        """Generate Excel report with crypto data."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        xlsx_name = f"CRYPTO_DATA_{timestamp}.xlsx"
        
        ef = ExcelFormatter()
        
        # Prices sheet
        if self.all_prices:
            df_prices = pd.DataFrame(self.all_prices)
            ef.add_to_sheet(df_prices, "Prices")
        
        # Info sheet
        if self.all_info:
            df_info = pd.DataFrame(self.all_info)
            ef.add_to_sheet(df_info, "Coin Info")
        
        # Summary sheet
        summary_data = {
            "Metric": ["Symbols Processed", "Price Records", "Interval", "Provider", "Timestamp"],
            "Value": [
                len(self.symbols),
                len(self.all_prices),
                self.interval,
                self.provider.name,
                timestamp
            ]
        }
        ef.add_to_sheet(pd.DataFrame(summary_data), "Summary")
        
        ef.save(xlsx_name, self.data_dir)
        log.info(f"Excel: {os.path.join(self.data_dir, xlsx_name)}")


def main():
    parser = argparse.ArgumentParser(description="Fetch cryptocurrency market data from multiple providers")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to process (e.g., BTCUSDT ETHUSDT)")
    parser.add_argument("--provider", type=str, default="binance", 
                       help="Data provider to use (binance, coinbase)")
    parser.add_argument("--interval", type=str, default="1d",
                       help="Candlestick interval (1m, 5m, 1h, 4h, 1d, 1w)")
    parser.add_argument("--days", type=int, default=365,
                       help="Number of days of historical data to fetch")
    parser.add_argument("--force", action="store_true", 
                       help="Force re-fetch all symbols, ignoring cached data")
    args = parser.parse_args()

    CryptoPipeline(
        symbols=args.symbols,
        provider_name=args.provider,
        interval=args.interval,
        days=args.days,
        force=args.force
    )


if __name__ == "__main__":
    main()
