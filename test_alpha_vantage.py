"""
Test script for Alpha Vantage provider.

Tests the provider with BGFV (the problematic ticker from Yahoo Finance).
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from sources.equity.providers.alpha_vantage import AlphaVantageProvider
from sources.equity.providers.base import RateLimitError, DataNotFoundError, ProviderError


def test_alpha_vantage():
    """Test Alpha Vantage provider with BGFV."""
    
    # Check for API key
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print("❌ ALPHA_VANTAGE_API_KEY environment variable not set")
        print("\nTo get a free API key:")
        print("1. Visit: https://www.alphavantage.co/support/#api-key")
        print("2. Enter your email and get instant key")
        print("3. Set environment variable:")
        print("   export ALPHA_VANTAGE_API_KEY='your_key_here'")
        return
    
    print("=" * 60)
    print("Testing Alpha Vantage Provider with BGFV")
    print("=" * 60)
    
    try:
        provider = AlphaVantageProvider(api_key=api_key)
        print(f"✓ Provider initialized: {provider.name}")
        print(f"✓ API Key: {api_key[:8]}...")
        print()
        
        # Test 1: Historical prices
        print("Test 1: Historical Prices (5y)")
        print("-" * 60)
        try:
            prices = provider.get_historical_prices("BGFV", period="5y")
            print(f"✓ Retrieved {len(prices)} price records")
            if prices:
                latest = prices[0]
                print(f"  Latest: {latest['date']} - Close: ${latest['close']:.2f}, Volume: {latest['volume']:,}")
                oldest = prices[-1]
                print(f"  Oldest: {oldest['date']} - Close: ${oldest['close']:.2f}")
        except RateLimitError as e:
            print(f"⚠ Rate limit: {e}")
        except DataNotFoundError as e:
            print(f"❌ Data not found: {e}")
        except ProviderError as e:
            print(f"❌ Provider error: {e}")
        print()
        
        # Test 2: Dividends
        print("Test 2: Dividend History")
        print("-" * 60)
        try:
            dividends = provider.get_dividends("BGFV")
            print(f"✓ Retrieved {len(dividends)} dividend records")
            if dividends:
                for div in dividends[:5]:  # Show first 5
                    print(f"  {div['date']}: ${div['amount']:.4f}")
        except RateLimitError as e:
            print(f"⚠ Rate limit: {e}")
        except DataNotFoundError as e:
            print(f"❌ Data not found: {e}")
        except ProviderError as e:
            print(f"❌ Provider error: {e}")
        print()
        
        # Test 3: Splits
        print("Test 3: Stock Splits")
        print("-" * 60)
        try:
            splits = provider.get_splits("BGFV")
            print(f"✓ Retrieved {len(splits)} split records")
            if splits:
                for split in splits:
                    print(f"  {split['date']}: {split['ratio']:.4f}")
        except RateLimitError as e:
            print(f"⚠ Rate limit: {e}")
        except DataNotFoundError as e:
            print(f"❌ Data not found: {e}")
        except ProviderError as e:
            print(f"❌ Provider error: {e}")
        print()
        
        # Test 4: Company Info
        print("Test 4: Company Info")
        print("-" * 60)
        try:
            info = provider.get_info("BGFV")
            if info:
                print(f"✓ Retrieved company info")
                print(f"  Sector: {info.get('sector', 'N/A')}")
                print(f"  Industry: {info.get('industry', 'N/A')}")
                print(f"  Market Cap: ${info.get('market_cap', 0):,}" if info.get('market_cap') else "  Market Cap: N/A")
                print(f"  P/E Ratio: {info.get('trailing_pe', 'N/A')}")
                print(f"  Beta: {info.get('beta', 'N/A')}")
        except RateLimitError as e:
            print(f"⚠ Rate limit: {e}")
        except DataNotFoundError as e:
            print(f"❌ Data not found: {e}")
        except ProviderError as e:
            print(f"❌ Provider error: {e}")
        print()
        
        print("=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)
        print("\nNote: Alpha Vantage free tier has rate limits:")
        print("- 25 requests per day")
        print("- 5 calls per minute")
        print("\nThis test used 4 API calls.")
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_alpha_vantage()
