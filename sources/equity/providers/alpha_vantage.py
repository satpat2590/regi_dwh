"""
Alpha Vantage equity data provider.

Official API documentation: https://www.alphavantage.co/documentation/
"""

import os
import time
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

from .base import EquityDataProvider, RateLimitError, DataNotFoundError, ProviderError


logger = logging.getLogger(__name__)


class AlphaVantageProvider(EquityDataProvider):
    """
    Alpha Vantage equity data provider.
    
    Free tier: 25 requests/day, 5 calls/minute
    Paid tiers: Remove daily cap, increase rate limits
    
    API Key: Get from https://www.alphavantage.co/support/#api-key
    """
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    # Rate limiting (conservative defaults for free tier)
    CALLS_PER_MINUTE = 5
    SECONDS_BETWEEN_CALLS = 60 / CALLS_PER_MINUTE
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Alpha Vantage provider.
        
        Args:
            api_key: Alpha Vantage API key. If not provided, reads from
                    ALPHA_VANTAGE_API_KEY environment variable.
        """
        if not api_key:
            api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        
        if not api_key:
            raise ValueError(
                "Alpha Vantage API key required. Set ALPHA_VANTAGE_API_KEY "
                "environment variable or pass api_key parameter."
            )
        
        super().__init__(api_key)
        self.session = requests.Session()
        self.last_call_time = 0
    
    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.SECONDS_BETWEEN_CALLS:
            sleep_time = self.SECONDS_BETWEEN_CALLS - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_call_time = time.time()
    
    def _make_request(self, params: Dict) -> Dict:
        """
        Make API request with error handling.
        
        Args:
            params: Query parameters
        
        Returns:
            JSON response
        
        Raises:
            RateLimitError: If rate limit exceeded
            DataNotFoundError: If data not available
            ProviderError: For other API errors
        """
        self._rate_limit()
        
        params["apikey"] = self.api_key
        
        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Check for API error messages
            if "Error Message" in data:
                raise DataNotFoundError(data["Error Message"])
            
            if "Note" in data and "API call frequency" in data["Note"]:
                raise RateLimitError(data["Note"])
            
            if "Information" in data:
                # Usually means invalid API key or other config issue
                raise ProviderError(data["Information"])
            
            return data
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            raise ProviderError(f"HTTP error: {e}")
        
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"Request failed: {e}")
    
    def get_historical_prices(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "5y"
    ) -> List[Dict]:
        """
        Get historical daily prices from Alpha Vantage.
        
        Uses TIME_SERIES_DAILY_ADJUSTED endpoint for full history.
        """
        logger.info(f"Fetching historical prices for {ticker}")
        
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": ticker,
            "outputsize": "full"  # Get full history (20+ years)
        }
        
        try:
            data = self._make_request(params)
            
            if "Time Series (Daily)" not in data:
                logger.warning(f"{ticker}: No time series data in response")
                return []
            
            time_series = data["Time Series (Daily)"]
            
            # Convert to our standard format
            prices = []
            for date_str, values in time_series.items():
                # Parse date
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                
                # Filter by date range if specified
                if start_date:
                    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
                    if date_obj < start_obj:
                        continue
                
                if end_date:
                    end_obj = datetime.strptime(end_date, "%Y-%m-%d")
                    if date_obj > end_obj:
                        continue
                
                # Apply period filter if no explicit dates
                if not start_date and not end_date:
                    cutoff = self._parse_period(period)
                    if date_obj < cutoff:
                        continue
                
                prices.append({
                    "ticker": ticker,
                    "date": date_str,
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["5. adjusted close"]),  # Use adjusted
                    "volume": int(values["6. volume"])
                })
            
            logger.info(f"{ticker}: Retrieved {len(prices)} price records")
            return prices
        
        except (RateLimitError, DataNotFoundError, ProviderError):
            raise
        except Exception as e:
            logger.exception(f"{ticker}: Unexpected error fetching prices")
            raise ProviderError(f"Failed to fetch prices: {e}")
    
    def get_dividends(self, ticker: str) -> List[Dict]:
        """
        Get dividend history.
        
        Alpha Vantage doesn't have a dedicated dividends endpoint,
        but we can extract from TIME_SERIES_DAILY_ADJUSTED.
        """
        logger.info(f"Fetching dividends for {ticker}")
        
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": ticker,
            "outputsize": "full"
        }
        
        try:
            data = self._make_request(params)
            
            if "Time Series (Daily)" not in data:
                return []
            
            time_series = data["Time Series (Daily)"]
            
            dividends = []
            for date_str, values in time_series.items():
                dividend_amount = float(values.get("7. dividend amount", 0))
                if dividend_amount > 0:
                    dividends.append({
                        "ticker": ticker,
                        "date": date_str,
                        "amount": dividend_amount
                    })
            
            logger.info(f"{ticker}: Retrieved {len(dividends)} dividend records")
            return dividends
        
        except (RateLimitError, DataNotFoundError, ProviderError):
            raise
        except Exception as e:
            logger.exception(f"{ticker}: Unexpected error fetching dividends")
            raise ProviderError(f"Failed to fetch dividends: {e}")
    
    def get_splits(self, ticker: str) -> List[Dict]:
        """
        Get stock split history.
        
        Alpha Vantage provides split coefficient in daily data.
        """
        logger.info(f"Fetching splits for {ticker}")
        
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": ticker,
            "outputsize": "full"
        }
        
        try:
            data = self._make_request(params)
            
            if "Time Series (Daily)" not in data:
                return []
            
            time_series = data["Time Series (Daily)"]
            
            splits = []
            for date_str, values in time_series.items():
                split_coefficient = float(values.get("8. split coefficient", 1.0))
                if split_coefficient != 1.0:
                    splits.append({
                        "ticker": ticker,
                        "date": date_str,
                        "ratio": split_coefficient
                    })
            
            logger.info(f"{ticker}: Retrieved {len(splits)} split records")
            return splits
        
        except (RateLimitError, DataNotFoundError, ProviderError):
            raise
        except Exception as e:
            logger.exception(f"{ticker}: Unexpected error fetching splits")
            raise ProviderError(f"Failed to fetch splits: {e}")
    
    def get_info(self, ticker: str) -> Optional[Dict]:
        """
        Get company overview and valuation ratios.
        
        Uses OVERVIEW endpoint for fundamental data.
        """
        logger.info(f"Fetching company info for {ticker}")
        
        params = {
            "function": "OVERVIEW",
            "symbol": ticker
        }
        
        try:
            data = self._make_request(params)
            
            # Check if we got valid data
            if not data or "Symbol" not in data:
                logger.warning(f"{ticker}: No overview data available")
                return None
            
            # Extract relevant fields
            info = {
                "ticker": ticker,
                "fetched_date": datetime.now().date().isoformat(),
                "market_cap": self._parse_float(data.get("MarketCapitalization")),
                "trailing_pe": self._parse_float(data.get("TrailingPE")),
                "forward_pe": self._parse_float(data.get("ForwardPE")),
                "price_to_book": self._parse_float(data.get("PriceToBookRatio")),
                "dividend_yield": self._parse_float(data.get("DividendYield")),
                "beta": self._parse_float(data.get("Beta")),
                "fifty_two_week_high": self._parse_float(data.get("52WeekHigh")),
                "fifty_two_week_low": self._parse_float(data.get("52WeekLow")),
                "average_volume": self._parse_int(data.get("Volume")),
                "sector": data.get("Sector", ""),
                "industry": data.get("Industry", "")
            }
            
            logger.info(f"{ticker}: Retrieved company info")
            return info
        
        except (RateLimitError, DataNotFoundError, ProviderError):
            raise
        except Exception as e:
            logger.exception(f"{ticker}: Unexpected error fetching info")
            raise ProviderError(f"Failed to fetch info: {e}")
    
    @staticmethod
    def _parse_float(value) -> Optional[float]:
        """Parse float value, return None if invalid."""
        if value is None or value == "None" or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _parse_int(value) -> Optional[int]:
        """Parse int value, return None if invalid."""
        if value is None or value == "None" or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _parse_period(period: str) -> datetime:
        """
        Parse period string to cutoff date.
        
        Args:
            period: Period string like "5y", "1y", "6mo"
        
        Returns:
            Cutoff datetime
        """
        now = datetime.now()
        
        if period.endswith("y"):
            years = int(period[:-1])
            return now - timedelta(days=years * 365)
        elif period.endswith("mo"):
            months = int(period[:-2])
            return now - timedelta(days=months * 30)
        elif period.endswith("d"):
            days = int(period[:-1])
            return now - timedelta(days=days)
        else:
            # Default to 5 years
            return now - timedelta(days=5 * 365)
