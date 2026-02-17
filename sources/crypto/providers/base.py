"""
Base provider interface for cryptocurrency data sources.

All crypto data providers must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime


class CryptoDataProvider(ABC):
    """Abstract base class for cryptocurrency data providers."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the provider.
        
        Args:
            api_key: API key for the provider (if required)
        """
        self.api_key = api_key
        self.name = self.__class__.__name__
    
    @abstractmethod
    def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Get historical OHLCV price data.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Candlestick interval ('1m', '5m', '1h', '4h', '1d', '1w')
            start_date: Start date (YYYY-MM-DD), optional
            end_date: End date (YYYY-MM-DD), optional
            limit: Maximum number of candles to return
        
        Returns:
            List of dicts with keys: symbol, timestamp, date, interval,
            open, high, low, close, volume, quote_volume, trades
        """
        pass
    
    @abstractmethod
    def get_current_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current price for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
        
        Returns:
            Dict with keys: symbol, price, timestamp
        """
        pass
    
    @abstractmethod
    def get_coin_info(self, symbol: str) -> Optional[Dict]:
        """
        Get coin/token information.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
        
        Returns:
            Dict with keys: symbol, name, base_asset, quote_asset,
            market_cap, circulating_supply, etc.
        """
        pass
    
    @abstractmethod
    def get_supported_symbols(self) -> List[str]:
        """
        Get list of supported trading pair symbols.
        
        Returns:
            List of symbol strings (e.g., ['BTCUSDT', 'ETHUSDT', ...])
        """
        pass
    
    def supports_symbol(self, symbol: str) -> bool:
        """
        Check if provider supports a specific symbol.
        
        Default implementation checks against get_supported_symbols().
        
        Args:
            symbol: Trading pair symbol
        
        Returns:
            True if symbol is supported
        """
        return symbol in self.get_supported_symbols()


class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""
    pass


class DataNotFoundError(Exception):
    """Raised when data is not available for a symbol."""
    pass


class ProviderError(Exception):
    """Base exception for provider-specific errors."""
    pass


class InvalidSymbolError(Exception):
    """Raised when symbol is not supported by provider."""
    pass
