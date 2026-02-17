"""
Binance cryptocurrency data provider.

Uses the python-binance library to fetch historical and real-time
cryptocurrency data from Binance exchange.

No API key required for public market data endpoints.
"""

import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
except ImportError:
    raise ImportError(
        "python-binance library required. Install with: pip install python-binance"
    )

from .base import (
    CryptoDataProvider,
    RateLimitError,
    DataNotFoundError,
    ProviderError,
    InvalidSymbolError
)

logger = logging.getLogger(__name__)


class BinanceProvider(CryptoDataProvider):
    """
    Binance cryptocurrency data provider.
    
    Provides access to Binance's public market data API including:
    - Historical klines (OHLCV candlestick data)
    - Current prices
    - Trading pair information
    
    No API key required for public endpoints.
    """
    
    # Binance interval mapping
    INTERVAL_MAP = {
        "1m": Client.KLINE_INTERVAL_1MINUTE,
        "3m": Client.KLINE_INTERVAL_3MINUTE,
        "5m": Client.KLINE_INTERVAL_5MINUTE,
        "15m": Client.KLINE_INTERVAL_15MINUTE,
        "30m": Client.KLINE_INTERVAL_30MINUTE,
        "1h": Client.KLINE_INTERVAL_1HOUR,
        "2h": Client.KLINE_INTERVAL_2HOUR,
        "4h": Client.KLINE_INTERVAL_4HOUR,
        "6h": Client.KLINE_INTERVAL_6HOUR,
        "8h": Client.KLINE_INTERVAL_8HOUR,
        "12h": Client.KLINE_INTERVAL_12HOUR,
        "1d": Client.KLINE_INTERVAL_1DAY,
        "3d": Client.KLINE_INTERVAL_3DAY,
        "1w": Client.KLINE_INTERVAL_1WEEK,
        "1M": Client.KLINE_INTERVAL_1MONTH,
    }
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, tld: str = "us"):
        """
        Initialize Binance provider.
        
        Args:
            api_key: Binance API key (optional)
            api_secret: Binance API secret (optional)
            tld: Top-level domain ('com' or 'us'). Defaults to 'us' for US users.
        """
        super().__init__(api_key)
        self.api_secret = api_secret
        self.tld = tld
        
        # Initialize client
        # Note: tld='us' is required for US users
        self.client = Client(api_key, api_secret, tld=tld)
        
        # Cache for exchange info (trading pairs)
        self._exchange_info = None
        self._supported_symbols = None
    
    def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Get historical OHLCV data from Binance.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Candlestick interval ('1m', '5m', '1h', '4h', '1d', '1w')
            start_date: Start date (YYYY-MM-DD), optional
            end_date: End date (YYYY-MM-DD), optional
            limit: Maximum number of candles (max 1000 per request)
        
        Returns:
            List of price dicts
        
        Raises:
            InvalidSymbolError: If symbol not supported
            RateLimitError: If rate limit exceeded
            DataNotFoundError: If no data available
            ProviderError: For other API errors
        """
        # Validate interval
        if interval not in self.INTERVAL_MAP:
            raise ValueError(
                f"Invalid interval: {interval}. "
                f"Supported: {list(self.INTERVAL_MAP.keys())}"
            )
        
        binance_interval = self.INTERVAL_MAP[interval]
        
        try:
            # Prepare parameters
            params = {
                "symbol": symbol.upper(),
                "interval": binance_interval,
                "limit": min(limit, 1000)  # Binance max is 1000
            }
            
            # Add date range if provided
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                params["startTime"] = int(start_dt.timestamp() * 1000)
            
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                params["endTime"] = int(end_dt.timestamp() * 1000)
            
            # Fetch klines
            klines = self.client.get_klines(**params)
            
            if not klines:
                raise DataNotFoundError(f"No data available for {symbol}")
            
            # Convert to standard format
            prices = []
            for kline in klines:
                prices.append({
                    "symbol": symbol.upper(),
                    "timestamp": kline[0],  # Open time (milliseconds)
                    "date": datetime.fromtimestamp(kline[0] / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                    "interval": interval,
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5]),  # Base asset volume
                    "quote_volume": float(kline[7]),  # Quote asset volume
                    "trades": int(kline[8]),  # Number of trades
                })
            
            return prices
        
        except BinanceAPIException as e:
            if e.code == -1003:  # Rate limit
                raise RateLimitError(f"Binance rate limit exceeded: {e.message}")
            elif e.code == -1121:  # Invalid symbol
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            else:
                raise ProviderError(f"Binance API error: {e.message}")
        
        except Exception as e:
            raise ProviderError(f"Error fetching data from Binance: {str(e)}")
    
    def get_current_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current price for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
        
        Returns:
            Dict with current price info
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol.upper())
            
            return {
                "symbol": symbol.upper(),
                "price": float(ticker["price"]),
                "timestamp": int(time.time() * 1000),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        except BinanceAPIException as e:
            if e.code == -1121:
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            raise ProviderError(f"Binance API error: {e.message}")
        
        except Exception as e:
            raise ProviderError(f"Error fetching current price: {str(e)}")
    
    def get_coin_info(self, symbol: str) -> Optional[Dict]:
        """
        Get trading pair information from Binance.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
        
        Returns:
            Dict with symbol info
        """
        try:
            # Get exchange info if not cached
            if not self._exchange_info:
                self._exchange_info = self.client.get_exchange_info()
            
            # Find symbol info
            symbol_upper = symbol.upper()
            symbol_info = None
            
            for s in self._exchange_info["symbols"]:
                if s["symbol"] == symbol_upper:
                    symbol_info = s
                    break
            
            if not symbol_info:
                raise InvalidSymbolError(f"Symbol not found: {symbol}")
            
            return {
                "symbol": symbol_upper,
                "base_asset": symbol_info["baseAsset"],
                "quote_asset": symbol_info["quoteAsset"],
                "status": symbol_info["status"],
                "exchange": "binance",
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        except BinanceAPIException as e:
            raise ProviderError(f"Binance API error: {e.message}")
        
        except Exception as e:
            raise ProviderError(f"Error fetching coin info: {str(e)}")
    
    def get_supported_symbols(self) -> List[str]:
        """
        Get list of all trading pairs on Binance.
        
        Returns:
            List of symbol strings
        """
        try:
            # Use cache if available
            if self._supported_symbols:
                return self._supported_symbols
            
            # Get exchange info
            if not self._exchange_info:
                self._exchange_info = self.client.get_exchange_info()
            
            # Extract symbols
            symbols = [
                s["symbol"] for s in self._exchange_info["symbols"]
                if s["status"] == "TRADING"
            ]
            
            self._supported_symbols = symbols
            return symbols
        
        except BinanceAPIException as e:
            raise ProviderError(f"Binance API error: {e.message}")
        
        except Exception as e:
            raise ProviderError(f"Error fetching supported symbols: {str(e)}")
    
    def get_usdt_pairs(self) -> List[str]:
        """
        Get all USDT trading pairs.
        
        Convenience method for getting major trading pairs.
        
        Returns:
            List of USDT pair symbols (e.g., ['BTCUSDT', 'ETHUSDT', ...])
        """
        all_symbols = self.get_supported_symbols()
        return [s for s in all_symbols if s.endswith("USDT")]
    
    def get_btc_pairs(self) -> List[str]:
        """
        Get all BTC trading pairs.
        
        Returns:
            List of BTC pair symbols
        """
        all_symbols = self.get_supported_symbols()
        return [s for s in all_symbols if s.endswith("BTC")]
