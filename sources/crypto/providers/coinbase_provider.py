"""
Coinbase cryptocurrency data provider.

Wraps the existing CoinbaseBroker class to integrate with the
provider abstraction layer.

Requires Coinbase API credentials.
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

try:
    from coinbase.rest import RESTClient
except ImportError:
    raise ImportError(
        "coinbase-advanced-py library required. Install with: pip install coinbase-advanced-py"
    )

from .base import (
    CryptoDataProvider,
    RateLimitError,
    DataNotFoundError,
    ProviderError,
    InvalidSymbolError
)

logger = logging.getLogger(__name__)


class CoinbaseProvider(CryptoDataProvider):
    """
    Coinbase cryptocurrency data provider.
    
    Provides access to Coinbase's API including:
    - Current prices and 24h changes
    - Product information
    - Portfolio data (requires authentication)
    
    Requires API key and secret for authentication.
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize Coinbase provider.
        
        Args:
            api_key: Coinbase API key (required)
            api_secret: Coinbase API secret (required)
        """
        super().__init__(api_key)
        
        # Get credentials from args or environment
        self.api_key = api_key or os.getenv("COINBASE_API_KEY")
        self.api_secret = api_secret or os.getenv("COINBASE_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Coinbase API credentials required. "
                "Set COINBASE_API_KEY and COINBASE_SECRET environment variables "
                "or pass as arguments."
            )
        
        # Initialize Coinbase client
        self.client = RESTClient(self.api_key, self.api_secret)
        
        # Cache for products
        self._products_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes
    
    def _get_products(self, force_refresh: bool = False) -> List:
        """
        Get all products from Coinbase with caching.
        
        Args:
            force_refresh: Force refresh cache
        
        Returns:
            List of product objects
        """
        now = datetime.now()
        
        # Check cache
        if (not force_refresh and 
            self._products_cache and 
            self._cache_timestamp and
            (now - self._cache_timestamp).seconds < self._cache_ttl):
            return self._products_cache
        
        # Fetch fresh data
        try:
            response = self.client.get_products()
            self._products_cache = response.products
            self._cache_timestamp = now
            return self._products_cache
        except Exception as e:
            raise ProviderError(f"Error fetching products from Coinbase: {str(e)}")
    
    def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Get historical OHLCV data from Coinbase.
        
        Note: Coinbase API has limited historical data support.
        This implementation returns current price data only.
        For full historical data, use Binance provider.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USD')
            interval: Not used (Coinbase limitation)
            start_date: Not used (Coinbase limitation)
            end_date: Not used (Coinbase limitation)
            limit: Not used (Coinbase limitation)
        
        Returns:
            List with single current price entry
        """
        logger.warning(
            "Coinbase provider has limited historical data. "
            "Returning current price only. Use Binance for historical data."
        )
        
        # Get current price
        current = self.get_current_price(symbol)
        
        if not current:
            return []
        
        # Format as OHLCV (all values same since it's current price)
        return [{
            "symbol": symbol,
            "timestamp": current["timestamp"],
            "date": current["date"],
            "interval": interval,
            "open": current["price"],
            "high": current["price"],
            "low": current["price"],
            "close": current["price"],
            "volume": 0.0,  # Not available
            "quote_volume": 0.0,  # Not available
            "trades": 0,  # Not available
        }]
    
    def get_current_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current price for a symbol from Coinbase.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USD')
        
        Returns:
            Dict with current price info
        """
        try:
            products = self._get_products()
            
            # Find matching product
            product = None
            for p in products:
                if p.product_id == symbol:
                    product = p
                    break
            
            if not product:
                raise InvalidSymbolError(f"Symbol not found: {symbol}")
            
            return {
                "symbol": symbol,
                "price": float(product.price) if product.price else 0.0,
                "price_change_24h": float(product.price_percentage_change_24h) if product.price_percentage_change_24h else 0.0,
                "volume_24h": float(product.volume_24h) if product.volume_24h else 0.0,
                "volume_change_24h": float(product.volume_percentage_change_24h) if product.volume_percentage_change_24h else 0.0,
                "timestamp": int(datetime.now().timestamp() * 1000),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        except InvalidSymbolError:
            raise
        except Exception as e:
            raise ProviderError(f"Error fetching current price from Coinbase: {str(e)}")
    
    def get_coin_info(self, symbol: str) -> Optional[Dict]:
        """
        Get trading pair information from Coinbase.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USD')
        
        Returns:
            Dict with symbol info
        """
        try:
            products = self._get_products()
            
            # Find matching product
            product = None
            for p in products:
                if p.product_id == symbol:
                    product = p
                    break
            
            if not product:
                raise InvalidSymbolError(f"Symbol not found: {symbol}")
            
            # Parse base and quote assets from product_id (e.g., "BTC-USD")
            parts = symbol.split("-")
            base_asset = parts[0] if len(parts) > 0 else ""
            quote_asset = parts[1] if len(parts) > 1 else ""
            
            return {
                "symbol": symbol,
                "name": product.base_name if hasattr(product, 'base_name') else base_asset,
                "base_asset": base_asset,
                "quote_asset": quote_asset,
                "status": "TRADING",  # Assume trading if in products list
                "exchange": "coinbase",
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        except InvalidSymbolError:
            raise
        except Exception as e:
            raise ProviderError(f"Error fetching coin info from Coinbase: {str(e)}")
    
    def get_supported_symbols(self) -> List[str]:
        """
        Get list of all trading pairs on Coinbase.
        
        Returns:
            List of symbol strings (e.g., ['BTC-USD', 'ETH-USD', ...])
        """
        try:
            products = self._get_products()
            return [p.product_id for p in products]
        except Exception as e:
            raise ProviderError(f"Error fetching supported symbols from Coinbase: {str(e)}")
    
    def get_portfolio(self) -> List[Dict]:
        """
        Get user's portfolio from Coinbase.
        
        Requires authentication.
        
        Returns:
            List of dicts with account information
        """
        try:
            account_info = self.client.get_accounts()
            
            portfolio = []
            for account in account_info.accounts:
                value = float(account.available_balance["value"])
                currency = account.available_balance["currency"]
                
                if value > 0:
                    portfolio.append({
                        "name": account.name,
                        "currency": account.currency,
                        "balance": value,
                        "balance_currency": currency,
                    })
            
            return portfolio
        
        except Exception as e:
            raise ProviderError(f"Error fetching portfolio from Coinbase: {str(e)}")
    
    def get_usd_pairs(self) -> List[str]:
        """
        Get all USD trading pairs.
        
        Convenience method for getting major trading pairs.
        
        Returns:
            List of USD pair symbols (e.g., ['BTC-USD', 'ETH-USD', ...])
        """
        all_symbols = self.get_supported_symbols()
        return [s for s in all_symbols if s.endswith("-USD")]
