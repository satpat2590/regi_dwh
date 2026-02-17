"""
Data access layer for SEC financial database.
Provides read-only access to SQLite database with clean query interface.
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from .config import settings


class FinancialDataProvider:
    """
    Provides financial data from SEC EDGAR database.
    Thread-safe read-only access for multi-client API server.
    """
    
    def __init__(self, db_path: str = None):
        """
        Initialize connection to financial database.
        
        Args:
            db_path: Path to financials.db (defaults to config setting)
        """
        self.db_path = db_path or settings.DB_PATH
        
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        
        # Read-only connection with WAL mode support
        self.conn = sqlite3.connect(
            f"file:{self.db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
            timeout=settings.DB_TIMEOUT
        )
        self.conn.row_factory = sqlite3.Row
    
    def close(self):
        """Close database connection."""
        self.conn.close()
    
    # ----------------------------------------------------------------
    # Company Lookup
    # ----------------------------------------------------------------
    
    def get_company_info(self, ticker: str) -> Optional[Dict]:
        """
        Get company metadata (sector, industry, SIC code).
        
        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
        
        Returns:
            Dict with company info or None if not found
        """
        cur = self.conn.execute(
            "SELECT * FROM companies WHERE ticker = ?", 
            (ticker.upper(),)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    
    def get_all_companies(self) -> List[Dict]:
        """Get all companies in the database."""
        cur = self.conn.execute(
            "SELECT * FROM companies ORDER BY ticker"
        )
        return [dict(row) for row in cur.fetchall()]
    
    def get_sector_tickers(self, sector: str) -> List[str]:
        """
        Get all tickers in a sector.
        
        Args:
            sector: Sector name (e.g., 'Technology', 'Finance')
        
        Returns:
            List of ticker symbols
        """
        cur = self.conn.execute(
            "SELECT ticker FROM companies WHERE sector = ? ORDER BY ticker",
            (sector,)
        )
        return [row['ticker'] for row in cur.fetchall()]
    
    def get_all_sectors(self) -> List[str]:
        """Get list of all unique sectors."""
        cur = self.conn.execute(
            "SELECT DISTINCT sector FROM companies WHERE sector != '' ORDER BY sector"
        )
        return [row['sector'] for row in cur.fetchall()]
    
    # ------------------------------------------------------------------
    # Crypto Access Methods
    # ------------------------------------------------------------------

    def get_crypto_symbols(self) -> List[dict]:
        """Get list of all tracked crypto symbols."""
        sql = """
            SELECT symbol, name, base_asset, quote_asset, exchange, last_updated
            FROM crypto_info
            ORDER BY symbol
        """
        cur = self.conn.execute(sql)
        return [dict(row) for row in cur.fetchall()]

    def get_crypto_info(self, symbol: str) -> Optional[dict]:
        """Get metadata for a specific crypto symbol."""
        sql = "SELECT * FROM crypto_info WHERE symbol = ?"
        cur = self.conn.execute(sql, (symbol,))
        rows = cur.fetchall()
        return dict(rows[0]) if rows else None

    def get_crypto_history(
        self, 
        symbol: str, 
        interval: str = "1d",
        limit: int = 1000
    ) -> List[dict]:
        """Get historical OHLCV data for a symbol."""
        sql = """
            SELECT * FROM crypto_prices 
            WHERE symbol = ? AND interval = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        cur = self.conn.execute(sql, (symbol, interval, limit))
        rows = [dict(row) for row in cur.fetchall()]
        # Return in ascending order for charting
        return sorted(rows, key=lambda x: x['timestamp'])

    def get_crypto_latest_price(self, symbol: str) -> Optional[dict]:
        """Get the latest price record for a symbol."""
        # Try 1d interval first, then others if needed
        sql = """
            SELECT * FROM crypto_prices 
            WHERE symbol = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        cur = self.conn.execute(sql, (symbol,))
        rows = cur.fetchall()
        return dict(rows[0]) if rows else None
    
    # ----------------------------------------------------------------
    # Financial Metrics
    # ----------------------------------------------------------------
    
    def get_latest_metric(
        self, 
        ticker: str, 
        field: str, 
        as_of_date: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Get the most recent value for a financial metric.
        
        Args:
            ticker: Stock ticker
            field: XBRL field name (e.g., 'Revenues', 'NetIncomeLoss')
            as_of_date: Optional cutoff date (YYYY-MM-DD) for point-in-time correctness
        
        Returns:
            Dict with value, filing_date, fiscal_period, etc.
        """
        if as_of_date:
            sql = """
                SELECT * FROM financial_facts
                WHERE ticker = ? AND field = ? AND filing_date <= ?
                ORDER BY filing_date DESC, period_end DESC
                LIMIT 1
            """
            params = (ticker.upper(), field, as_of_date)
        else:
            sql = """
                SELECT * FROM financial_facts
                WHERE ticker = ? AND field = ?
                ORDER BY filing_date DESC, period_end DESC
                LIMIT 1
            """
            params = (ticker.upper(), field)
        
        cur = self.conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None
    
    def get_metric_time_series(
        self, 
        ticker: str, 
        field: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        fiscal_period: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get historical time series for a metric.
        
        Args:
            ticker: Stock ticker
            field: XBRL field name
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            fiscal_period: Optional filter ('Q1', 'Q2', 'Q3', 'Q4', 'FY')
            limit: Optional max number of results
        
        Returns:
            List of dicts with values over time
        """
        conditions = ["ticker = ?", "field = ?"]
        params = [ticker.upper(), field]
        
        if start_date:
            conditions.append("period_end >= ?")
            params.append(start_date)
        
        if end_date:
            conditions.append("period_end <= ?")
            params.append(end_date)
        
        if fiscal_period:
            conditions.append("fiscal_period = ?")
            params.append(fiscal_period)
        
        sql = f"""
            SELECT * FROM financial_facts
            WHERE {' AND '.join(conditions)}
            ORDER BY period_end ASC
        """
        
        if limit:
            sql += f" LIMIT {limit}"
        
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    
    # ----------------------------------------------------------------
    # TTM Metrics (Trailing Twelve Months)
    # ----------------------------------------------------------------
    
    def get_latest_ttm(
        self, 
        ticker: str, 
        metric_name: str = "Revenue_TTM"
    ) -> Optional[Dict]:
        """
        Get latest TTM metric (Revenue_TTM or NetIncome_TTM).
        
        Args:
            ticker: Stock ticker
            metric_name: 'Revenue_TTM' or 'NetIncome_TTM'
        
        Returns:
            Dict with ttm_value, as_of_date, period_end
        """
        sql = """
            SELECT * FROM ttm_metrics
            WHERE ticker = ? AND metric_name = ?
            ORDER BY as_of_date DESC
            LIMIT 1
        """
        cur = self.conn.execute(sql, (ticker.upper(), metric_name))
        row = cur.fetchone()
        return dict(row) if row else None
    
    def get_ttm_time_series(
        self, 
        ticker: str, 
        metric_name: str = "Revenue_TTM",
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get full TTM time series for a ticker.
        
        Args:
            ticker: Stock ticker
            metric_name: 'Revenue_TTM' or 'NetIncome_TTM'
            limit: Optional max number of results
        
        Returns:
            List of TTM values over time
        """
        sql = """
            SELECT * FROM ttm_metrics
            WHERE ticker = ? AND metric_name = ?
            ORDER BY as_of_date ASC
        """
        
        if limit:
            sql += f" LIMIT {limit}"
        
        cur = self.conn.execute(sql, (ticker.upper(), metric_name))
        return [dict(row) for row in cur.fetchall()]
    
    # ----------------------------------------------------------------
    # Point-in-Time Queries (Prevents Look-Ahead Bias)
    # ----------------------------------------------------------------
    
    def get_financials_as_of_date(
        self, 
        ticker: str, 
        as_of_date: str,
        fields: Optional[List[str]] = None,
        min_priority: float = 100.0
    ) -> List[Dict]:
        """
        Get all financial data that was publicly available as of a specific date.
        Critical for backtesting to avoid look-ahead bias.
        
        Args:
            ticker: Stock ticker
            as_of_date: Date (YYYY-MM-DD) - only data filed before this date
            fields: Optional list of specific fields to retrieve
            min_priority: Minimum field priority score (default 100 = important fields)
        
        Returns:
            List of financial facts available as of that date
        """
        conditions = [
            "ticker = ?",
            "filing_date <= ?",
            "field_priority >= ?"
        ]
        params = [ticker.upper(), as_of_date, min_priority]
        
        if fields:
            placeholders = ','.join('?' * len(fields))
            conditions.append(f"field IN ({placeholders})")
            params.extend(fields)
        
        sql = f"""
            SELECT * FROM financial_facts
            WHERE {' AND '.join(conditions)}
            ORDER BY filing_date DESC, field
        """
        
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    
    # ----------------------------------------------------------------
    # Cross-Sectional Analysis
    # ----------------------------------------------------------------
    
    def get_sector_metrics(
        self, 
        sector: str, 
        field: str,
        fiscal_period: str = "FY"
    ) -> List[Dict]:
        """
        Compare a metric across all companies in a sector.
        
        Args:
            sector: Sector name
            field: XBRL field name
            fiscal_period: 'FY' for annual, or 'Q1'/'Q2'/'Q3'/'Q4' for quarterly
        
        Returns:
            List of latest values for each company in the sector
        """
        sql = """
            SELECT 
                f.ticker,
                f.entity_name,
                f.value,
                f.period_end,
                f.filing_date,
                f.fiscal_year,
                f.fiscal_period
            FROM financial_facts f
            INNER JOIN (
                SELECT ticker, MAX(filing_date) as max_date
                FROM financial_facts
                WHERE sector = ? AND field = ? AND fiscal_period = ?
                GROUP BY ticker
            ) latest ON f.ticker = latest.ticker AND f.filing_date = latest.max_date
            WHERE f.sector = ? AND f.field = ? AND f.fiscal_period = ?
            ORDER BY f.value DESC
        """
        params = (sector, field, fiscal_period, sector, field, fiscal_period)
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    
    # ----------------------------------------------------------------
    # Field Discovery
    # ----------------------------------------------------------------
    
    def get_available_fields(
        self, 
        ticker: str,
        statement_type: Optional[str] = None,
        min_priority: float = 0.0
    ) -> List[Dict]:
        """
        Discover what fields are available for a ticker.
        
        Args:
            ticker: Stock ticker
            statement_type: Optional filter ('Balance Sheet', 'Income Statement', etc.)
            min_priority: Minimum priority score
        
        Returns:
            List of unique fields with metadata
        """
        conditions = ["ticker = ?", "field_priority >= ?"]
        params = [ticker.upper(), min_priority]
        
        if statement_type:
            conditions.append("statement_type = ?")
            params.append(statement_type)
        
        sql = f"""
            SELECT DISTINCT 
                field, 
                field_label, 
                statement_type, 
                temporal_type,
                field_priority
            FROM financial_facts
            WHERE {' AND '.join(conditions)}
            ORDER BY field_priority DESC, field
        """
        
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    
    def get_field_catalog(self, min_priority: float = 0.0) -> List[Dict]:
        """
        Get the full field catalog with metadata.
        
        Args:
            min_priority: Minimum priority score to filter
        
        Returns:
            List of fields with taxonomy, label, description
        """
        sql = """
            SELECT fc.*, fp.priority_score, fp.tier
            FROM field_catalog fc
            LEFT JOIN field_priorities fp ON fc.field_name = fp.field_name
            WHERE fp.priority_score >= ?
            ORDER BY fp.priority_score DESC
        """
        cur = self.conn.execute(sql, (min_priority,))
        return [dict(row) for row in cur.fetchall()]
    
    # ----------------------------------------------------------------
    # Statistics
    # ----------------------------------------------------------------
    
    def get_database_stats(self) -> Dict:
        """Get database statistics."""
        stats = {}
        
        # Count companies
        cur = self.conn.execute("SELECT COUNT(*) as count FROM companies")
        stats['total_companies'] = cur.fetchone()['count']
        
        # Count financial facts
        cur = self.conn.execute("SELECT COUNT(*) as count FROM financial_facts")
        stats['total_facts'] = cur.fetchone()['count']
        
        # Count fields
        cur = self.conn.execute("SELECT COUNT(*) as count FROM field_catalog")
        stats['total_fields'] = cur.fetchone()['count']
        
        # Count sectors
        cur = self.conn.execute("SELECT COUNT(DISTINCT sector) as count FROM companies WHERE sector != ''")
        stats['total_sectors'] = cur.fetchone()['count']
        
        return stats
    
    # ----------------------------------------------------------------
    # Custom Queries
    # ----------------------------------------------------------------
    
    def query(self, sql: str, params: tuple = ()) -> List[Dict]:
        """
        Execute a custom SQL query.
        
        Args:
            sql: SQL query string
            params: Query parameters
        
        Returns:
            List of result rows as dicts
        """
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
