"""
Base provider interface for equity data sources.

All equity data providers must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime


class EquityDataProvider(ABC):
    """Abstract base class for equity data providers."""
    
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
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "5y"
    ) -> List[Dict]:
        """
        Get historical OHLCV price data.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD), optional
            end_date: End date (YYYY-MM-DD), optional
            period: Period string (e.g., "5y", "1y"), used if dates not specified
        
        Returns:
            List of dicts with keys: ticker, date, open, high, low, close, volume
        """
        pass
    
    @abstractmethod
    def get_dividends(self, ticker: str) -> List[Dict]:
        """
        Get dividend history.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            List of dicts with keys: ticker, date, amount
        """
        pass
    
    @abstractmethod
    def get_splits(self, ticker: str) -> List[Dict]:
        """
        Get stock split history.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            List of dicts with keys: ticker, date, ratio
        """
        pass
    
    @abstractmethod
    def get_info(self, ticker: str) -> Optional[Dict]:
        """
        Get company info and valuation ratios.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            Dict with keys: ticker, fetched_date, market_cap, trailing_pe,
            forward_pe, price_to_book, dividend_yield, beta, etc.
        """
        pass
    
    def supports_ticker(self, ticker: str) -> bool:
        """
        Check if provider supports a specific ticker.
        
        Default implementation returns True. Override for provider-specific logic.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            True if ticker is supported
        """
        return True


class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""
    pass


class DataNotFoundError(Exception):
    """Raised when data is not available for a ticker."""
    pass


class ProviderError(Exception):
    """Base exception for provider-specific errors."""
    pass
