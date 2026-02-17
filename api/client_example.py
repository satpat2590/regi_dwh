"""
Example client for the SEC Financial Data API.

Demonstrates how to connect to the API from a trading bot or
other application.
"""

import requests
from typing import Dict, List, Optional


class SECDataClient:
    """
    Client for SEC Financial Data API.
    
    Usage:
        client = SECDataClient("http://localhost:8000")
        company = client.get_company("AAPL")
        revenue = client.get_ttm_revenue("AAPL")
    """
    
    def __init__(self, api_url: str = "http://localhost:8000"):
        """
        Initialize API client.
        
        Args:
            api_url: Base URL of the API server
        """
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
    
    def _get(self, endpoint: str, params: Dict = None) -> Dict:
        """Make GET request to API."""
        url = f"{self.api_url}{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    # ----------------------------------------------------------------
    # Health & Info
    # ----------------------------------------------------------------
    
    def health_check(self) -> Dict:
        """Check API health and get database statistics."""
        return self._get("/")
    
    def get_all_sectors(self) -> List[str]:
        """Get list of all available sectors."""
        return self._get("/sectors")
    
    # ----------------------------------------------------------------
    # Company Information
    # ----------------------------------------------------------------
    
    def get_all_companies(self) -> List[Dict]:
        """Get all companies in the database."""
        return self._get("/companies")
    
    def get_company(self, ticker: str) -> Dict:
        """
        Get company metadata.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            Company info with sector, industry, SIC code
        """
        return self._get(f"/companies/{ticker}")
    
    def get_sector_tickers(self, sector: str) -> Dict:
        """
        Get all tickers in a sector.
        
        Args:
            sector: Sector name (e.g., 'Technology')
        
        Returns:
            Dict with sector, tickers list, and count
        """
        return self._get(f"/sectors/{sector}/tickers")
    
    # ----------------------------------------------------------------
    # Financial Metrics
    # ----------------------------------------------------------------
    
    def get_latest_metric(
        self, 
        ticker: str, 
        field: str,
        as_of_date: Optional[str] = None
    ) -> Dict:
        """
        Get the most recent value for a financial metric.
        
        Args:
            ticker: Stock ticker
            field: XBRL field name (e.g., 'Revenues', 'NetIncomeLoss')
            as_of_date: Optional cutoff date (YYYY-MM-DD) for backtesting
        
        Returns:
            Metric data with value, filing_date, fiscal_period, etc.
        """
        params = {}
        if as_of_date:
            params['as_of_date'] = as_of_date
        
        return self._get(f"/metrics/{ticker}/{field}", params)
    
    def get_metric_time_series(
        self,
        ticker: str,
        field: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        fiscal_period: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict:
        """
        Get historical time series for a metric.
        
        Args:
            ticker: Stock ticker
            field: XBRL field name
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            fiscal_period: Filter by period ('Q1', 'Q2', 'Q3', 'Q4', 'FY')
            limit: Max number of results
        
        Returns:
            Dict with ticker, field, data array, and count
        """
        params = {'time_series': True}
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        if fiscal_period:
            params['fiscal_period'] = fiscal_period
        if limit:
            params['limit'] = limit
        
        return self._get(f"/metrics/{ticker}/{field}", params)
    
    # ----------------------------------------------------------------
    # TTM Metrics
    # ----------------------------------------------------------------
    
    def get_latest_ttm(
        self, 
        ticker: str, 
        metric_name: str = "Revenue_TTM"
    ) -> Dict:
        """
        Get latest TTM metric.
        
        Args:
            ticker: Stock ticker
            metric_name: 'Revenue_TTM' or 'NetIncome_TTM'
        
        Returns:
            TTM data with ttm_value, as_of_date, period_end
        """
        return self._get(f"/ttm/{ticker}/{metric_name}")
    
    def get_ttm_time_series(
        self,
        ticker: str,
        metric_name: str = "Revenue_TTM",
        limit: Optional[int] = None
    ) -> Dict:
        """
        Get TTM time series.
        
        Args:
            ticker: Stock ticker
            metric_name: 'Revenue_TTM' or 'NetIncome_TTM'
            limit: Max number of results
        
        Returns:
            Dict with ticker, metric_name, data array, and count
        """
        params = {'time_series': True}
        if limit:
            params['limit'] = limit
        
        return self._get(f"/ttm/{ticker}/{metric_name}", params)
    
    # ----------------------------------------------------------------
    # Convenience Methods
    # ----------------------------------------------------------------
    
    def get_ttm_revenue(self, ticker: str) -> float:
        """Get latest TTM revenue value."""
        result = self.get_latest_ttm(ticker, "Revenue_TTM")
        return result['ttm_value']
    
    def get_ttm_net_income(self, ticker: str) -> float:
        """Get latest TTM net income value."""
        result = self.get_latest_ttm(ticker, "NetIncome_TTM")
        return result['ttm_value']
    
    def get_latest_revenue(self, ticker: str) -> float:
        """Get latest revenue value."""
        result = self.get_latest_metric(ticker, "Revenues")
        return result['value']
    
    def get_latest_assets(self, ticker: str) -> float:
        """Get latest total assets value."""
        result = self.get_latest_metric(ticker, "Assets")
        return result['value']
    
    # ----------------------------------------------------------------
    # Sector Comparison
    # ----------------------------------------------------------------
    
    def compare_sector(
        self,
        sector: str,
        field: str,
        fiscal_period: str = "FY"
    ) -> Dict:
        """
        Compare a metric across all companies in a sector.
        
        Args:
            sector: Sector name
            field: XBRL field name
            fiscal_period: 'FY' for annual, or 'Q1'/'Q2'/'Q3'/'Q4'
        
        Returns:
            Dict with sector, field, companies array, and count
        """
        params = {
            'field': field,
            'fiscal_period': fiscal_period
        }
        return self._get(f"/sectors/{sector}/compare", params)
    
    # ----------------------------------------------------------------
    # Field Discovery
    # ----------------------------------------------------------------
    
    def get_available_fields(
        self,
        ticker: str,
        statement_type: Optional[str] = None,
        min_priority: float = 0.0
    ) -> Dict:
        """
        Discover available fields for a ticker.
        
        Args:
            ticker: Stock ticker
            statement_type: Optional filter ('Balance Sheet', 'Income Statement', etc.)
            min_priority: Minimum priority score
        
        Returns:
            Dict with ticker, fields array, and count
        """
        params = {'min_priority': min_priority}
        if statement_type:
            params['statement_type'] = statement_type
        
        return self._get(f"/fields/{ticker}", params)
    
    def get_field_catalog(self, min_priority: float = 0.0) -> Dict:
        """
        Get the full field catalog.
        
        Args:
            min_priority: Minimum priority score
        
        Returns:
            Dict with fields array and count
        """
        params = {'min_priority': min_priority}
        return self._get("/catalog", params)
    
    # ----------------------------------------------------------------
    # Backtesting
    # ----------------------------------------------------------------
    
    def get_financials_as_of_date(
        self,
        ticker: str,
        as_of_date: str,
        fields: Optional[List[str]] = None,
        min_priority: float = 100.0
    ) -> Dict:
        """
        Get all financial data available as of a specific date.
        
        Critical for backtesting - prevents look-ahead bias.
        
        Args:
            ticker: Stock ticker
            as_of_date: Cutoff date (YYYY-MM-DD)
            fields: Optional list of specific fields
            min_priority: Minimum priority score
        
        Returns:
            Dict with ticker, as_of_date, data array, and count
        """
        params = {
            'as_of_date': as_of_date,
            'min_priority': min_priority
        }
        if fields:
            params['fields'] = ','.join(fields)
        
        return self._get(f"/backtest/{ticker}", params)


# ----------------------------------------------------------------
# Example Usage
# ----------------------------------------------------------------

if __name__ == "__main__":
    # Initialize client
    client = SECDataClient("http://localhost:8000")
    
    print("=" * 60)
    print("SEC Financial Data API - Client Examples")
    print("=" * 60)
    
    # Health check
    print("\n1. Health Check")
    health = client.health_check()
    print(f"   Service: {health['service']}")
    print(f"   Status: {health['status']}")
    print(f"   Companies: {health['database_stats']['total_companies']}")
    print(f"   Facts: {health['database_stats']['total_facts']:,}")
    
    # Get company info
    print("\n2. Company Information")
    company = client.get_company("AAPL")
    print(f"   {company['ticker']}: {company['entity_name']}")
    print(f"   Sector: {company['sector']}")
    print(f"   Industry: {company['industry']}")
    
    # Get TTM revenue
    print("\n3. TTM Revenue")
    ttm_revenue = client.get_latest_ttm("AAPL", "Revenue_TTM")
    print(f"   AAPL TTM Revenue: ${ttm_revenue['ttm_value']:,.0f}")
    print(f"   As of: {ttm_revenue['as_of_date']}")
    
    # Get sector tickers
    print("\n4. Technology Sector Tickers")
    tech = client.get_sector_tickers("Technology")
    print(f"   {tech['sector']}: {', '.join(tech['tickers'])}")
    
    # Compare sector revenue
    print("\n5. Technology Sector Revenue Comparison")
    comparison = client.compare_sector("Technology", "Revenues", "FY")
    print(f"   Top 3 by revenue:")
    for i, company in enumerate(comparison['companies'][:3], 1):
        print(f"   {i}. {company['ticker']}: ${company['value']:,.0f}")
    
    # Get available fields
    print("\n6. High-Priority Fields for AAPL")
    fields = client.get_available_fields("AAPL", min_priority=150)
    print(f"   Found {fields['count']} high-priority fields")
    for field in fields['fields'][:5]:
        print(f"   - {field['field']}: {field['field_label']}")
    
    # Backtesting example
    print("\n7. Backtesting - Financials as of 2023-06-30")
    backtest = client.get_financials_as_of_date(
        "AAPL",
        "2023-06-30",
        min_priority=150
    )
    print(f"   {backtest['count']} facts available as of {backtest['as_of_date']}")
    
    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)
