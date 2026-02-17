"""
FastAPI application for SEC Financial Data API.

Exposes financial database via HTTP endpoints with auto-generated
OpenAPI documentation at /docs.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import logging

from .config import settings
from .data_access import FinancialDataProvider
from .models import (
    CompanyResponse,
    MetricResponse,
    TimeSeriesResponse,
    TTMResponse,
    TTMTimeSeriesResponse,
    SectorTickersResponse,
    SectorComparisonResponse,
    SectorComparisonItem,
    CryptoInfo,
    CryptoHistoryResponse,
    CryptoPrice,
    FieldsResponse,
    FieldInfo,
    FieldCatalogResponse,
    FieldCatalogItem,
    HealthResponse,
    DatabaseStatsResponse,
    ErrorResponse
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize data provider
try:
    data = FinancialDataProvider()
    logger.info(f"Connected to database: {data.db_path}")
except Exception as e:
    logger.error(f"Failed to connect to database: {e}")
    raise


# ----------------------------------------------------------------
# Health & Info
# ----------------------------------------------------------------

@app.get("/", response_model=HealthResponse, tags=["Health"])
def root():
    """
    API health check and information.
    
    Returns service status and database statistics.
    """
    try:
        stats = data.get_database_stats()
        return {
            "service": settings.API_TITLE,
            "version": settings.API_VERSION,
            "status": "healthy",
            "database_path": data.db_path,
            "database_stats": stats
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/sectors/{sector}/metrics/{field}", response_model=SectorComparisonResponse, tags=["Sectors"])
async def get_sector_metrics(
    sector: str, 
    field: str, 
    fiscal_period: str = "FY"
):
    """
    Compare a specific metric across all companies in a sector.
    Useful for benchmarking and peer analysis.
    """
    # Assuming 'data' (FinancialDataProvider) has a method for this
    # Or, if 'db' is a new instance, it needs to be defined or 'data' should be used.
    # For now, assuming 'data' is the correct provider.
    results = data.get_sector_metrics(sector, field, fiscal_period)
    
    return SectorComparisonResponse(
        sector=sector,
        field=field,
        fiscal_period=fiscal_period,
        companies=[SectorComparisonItem(**item) for item in results],
        count=len(results)
    )


# ----------------------------------------------------------------------------
# Crypto Routes
# ----------------------------------------------------------------------------

@app.get("/api/v1/crypto/symbols", response_model=List[CryptoInfo], tags=["Crypto"])
async def get_crypto_symbols():
    """Get list of all tracked cryptocurrency symbols."""
    results = data.get_crypto_symbols() # Assuming 'data' is the provider
    return [CryptoInfo(**item) for item in results]


@app.get("/api/v1/crypto/{symbol}/history", response_model=CryptoHistoryResponse, tags=["Crypto"])
async def get_crypto_history(
    symbol: str, 
    interval: str = "1d",
    limit: int = 365
):
    """
    Get historical OHLCV data for a cryptocurrency.
    
    - **symbol**: Trading pair (e.g., BTCUSDT)
    - **interval**: Timeframe (e.g., 1d, 1h)
    - **limit**: Number of candles to return (default 365)
    """
    results = data.get_crypto_history(symbol, interval, limit) # Assuming 'data' is the provider
    
    if not results:
        # Check if symbol exists
        info = data.get_crypto_info(symbol) # Assuming 'data' is the provider
        if not info:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        return CryptoHistoryResponse(
            symbol=symbol,
            interval=interval,
            count=0,
            prices=[]
        )
    
    return CryptoHistoryResponse(
        symbol=symbol,
        interval=interval,
        count=len(results),
        prices=[CryptoPrice(**item) for item in results]
    )


# ----------------------------------------------------------------
# Utility Routes
# ----------------------------------------------------------------

@app.get("/sectors", response_model=list[str], tags=["Companies"])
def get_all_sectors():
    """
    Get list of all available sectors.
    
    Returns:
        List of sector names
    """
    try:
        return data.get_all_sectors()
    except Exception as e:
        logger.error(f"Error fetching sectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------
# Company Endpoints
# ----------------------------------------------------------------

@app.get("/companies", response_model=list[CompanyResponse], tags=["Companies"])
def get_all_companies():
    """
    Get all companies in the database.
    
    Returns:
        List of all companies with metadata
    """
    try:
        companies = data.get_all_companies()
        return companies
    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/companies/{ticker}", response_model=CompanyResponse, tags=["Companies"])
def get_company(ticker: str):
    """
    Get company metadata by ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
    
    Returns:
        Company information including sector, industry, SIC code
    """
    try:
        company = data.get_company_info(ticker)
        if not company:
            raise HTTPException(
                status_code=404, 
                detail=f"Ticker '{ticker}' not found"
            )
        return company
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching company {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sectors/{sector}/tickers", response_model=SectorTickersResponse, tags=["Companies"])
def get_sector_tickers(sector: str):
    """
    Get all tickers in a specific sector.
    
    Args:
        sector: Sector name (e.g., 'Technology', 'Finance')
    
    Returns:
        List of ticker symbols in the sector
    """
    try:
        tickers = data.get_sector_tickers(sector)
        return {
            "sector": sector,
            "tickers": tickers,
            "count": len(tickers)
        }
    except Exception as e:
        logger.error(f"Error fetching tickers for sector {sector}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------
# Financial Metrics Endpoints
# ----------------------------------------------------------------

@app.get("/metrics/{ticker}/{field}", tags=["Metrics"])
def get_metric(
    ticker: str,
    field: str,
    as_of_date: Optional[str] = Query(None, description="Point-in-time cutoff date (YYYY-MM-DD)"),
    time_series: bool = Query(False, description="Return time series instead of latest value"),
    start_date: Optional[str] = Query(None, description="Start date for time series (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for time series (YYYY-MM-DD)"),
    fiscal_period: Optional[str] = Query(None, description="Filter by fiscal period (Q1, Q2, Q3, Q4, FY)"),
    limit: Optional[int] = Query(None, description="Max number of results for time series")
):
    """
    Get financial metric for a ticker.
    
    **Single Value Mode** (time_series=false):
    - Returns the most recent value for the field
    - Use `as_of_date` for point-in-time correctness (backtesting)
    
    **Time Series Mode** (time_series=true):
    - Returns historical values
    - Filter by `start_date`, `end_date`, `fiscal_period`
    
    Args:
        ticker: Stock ticker symbol
        field: XBRL field name (e.g., 'Revenues', 'NetIncomeLoss', 'Assets')
        as_of_date: Optional cutoff date for point-in-time queries
        time_series: If true, return full time series
        start_date: Start date for time series
        end_date: End date for time series
        fiscal_period: Filter by fiscal period
        limit: Max results for time series
    
    Returns:
        Single metric value or time series data
    """
    try:
        if time_series:
            results = data.get_metric_time_series(
                ticker=ticker,
                field=field,
                start_date=start_date,
                end_date=end_date,
                fiscal_period=fiscal_period,
                limit=limit
            )
            return {
                "ticker": ticker,
                "field": field,
                "data": results,
                "count": len(results)
            }
        else:
            result = data.get_latest_metric(ticker, field, as_of_date)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"No data found for {ticker}/{field}"
                )
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching metric {ticker}/{field}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------
# TTM Metrics Endpoints
# ----------------------------------------------------------------

@app.get("/ttm/{ticker}/{metric_name}", tags=["TTM Metrics"])
def get_ttm(
    ticker: str,
    metric_name: str,
    time_series: bool = Query(False, description="Return full time series"),
    limit: Optional[int] = Query(None, description="Max number of results for time series")
):
    """
    Get TTM (Trailing Twelve Months) metric.
    
    TTM metrics smooth out seasonal variations and are better for
    cross-company comparisons.
    
    **Single Value Mode** (time_series=false):
    - Returns the most recent TTM value
    
    **Time Series Mode** (time_series=true):
    - Returns historical TTM values over time
    
    Args:
        ticker: Stock ticker symbol
        metric_name: 'Revenue_TTM' or 'NetIncome_TTM'
        time_series: If true, return full historical series
        limit: Max results for time series
    
    Returns:
        TTM metric value or time series
    """
    try:
        if time_series:
            results = data.get_ttm_time_series(ticker, metric_name, limit)
            return {
                "ticker": ticker,
                "metric_name": metric_name,
                "data": results,
                "count": len(results)
            }
        else:
            result = data.get_latest_ttm(ticker, metric_name)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"No TTM data for {ticker}/{metric_name}"
                )
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching TTM {ticker}/{metric_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------
# Sector Comparison Endpoints
# ----------------------------------------------------------------

@app.get("/sectors/{sector}/compare", response_model=SectorComparisonResponse, tags=["Sector Analysis"])
def compare_sector(
    sector: str,
    field: str = Query(..., description="XBRL field name to compare"),
    fiscal_period: str = Query("FY", description="Fiscal period (FY, Q1, Q2, Q3, Q4)")
):
    """
    Compare a financial metric across all companies in a sector.
    
    Returns the latest value for each company, sorted by value (descending).
    
    Args:
        sector: Sector name (e.g., 'Technology', 'Finance')
        field: XBRL field name (e.g., 'Revenues', 'NetIncomeLoss')
        fiscal_period: 'FY' for annual, or 'Q1'/'Q2'/'Q3'/'Q4' for quarterly
    
    Returns:
        Comparison of metric across all companies in sector
    """
    try:
        results = data.get_sector_metrics(sector, field, fiscal_period)
        return {
            "sector": sector,
            "field": field,
            "fiscal_period": fiscal_period,
            "companies": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Error comparing sector {sector}/{field}: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ----------------------------------------------------------------------------
# Crypto Routes
# ----------------------------------------------------------------------------

@app.get("/api/v1/crypto/symbols", response_model=List[CryptoInfo], tags=["Crypto"])
async def get_crypto_symbols():
    """Get list of all tracked cryptocurrency symbols."""
    results = data.get_crypto_symbols()
    return [CryptoInfo(**item) for item in results]


@app.get("/api/v1/crypto/{symbol}/history", response_model=CryptoHistoryResponse, tags=["Crypto"])
async def get_crypto_history(
    symbol: str, 
    interval: str = "1d",
    limit: int = 365
):
    """
    Get historical OHLCV data for a cryptocurrency.
    
    - **symbol**: Trading pair (e.g., BTCUSDT)
    - **interval**: Timeframe (e.g., 1d, 1h)
    - **limit**: Number of candles to return (default 365)
    """
    results = data.get_crypto_history(symbol, interval, limit)
    
    if not results:
        # Check if symbol exists
        info = data.get_crypto_info(symbol)
        if not info:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        return CryptoHistoryResponse(
            symbol=symbol,
            interval=interval,
            count=0,
            prices=[]
        )
    
    return CryptoHistoryResponse(
        symbol=symbol,
        interval=interval,
        count=len(results),
        prices=[CryptoPrice(**item) for item in results]
    )


# ----------------------------------------------------------------
# Field Discovery Endpoints
# ----------------------------------------------------------------

@app.get("/fields/{ticker}", response_model=FieldsResponse, tags=["Field Discovery"])
def get_available_fields(
    ticker: str,
    statement_type: Optional[str] = Query(None, description="Filter by statement type"),
    min_priority: float = Query(0.0, description="Minimum field priority score")
):
    """
    Discover what financial fields are available for a ticker.
    
    Useful for exploring what data is reported by a specific company.
    
    Args:
        ticker: Stock ticker symbol
        statement_type: Optional filter ('Balance Sheet', 'Income Statement', 'Cash Flow Statement')
        min_priority: Minimum priority score (100+ for important fields)
    
    Returns:
        List of available fields with metadata
    """
    try:
        fields = data.get_available_fields(ticker, statement_type, min_priority)
        return {
            "ticker": ticker,
            "fields": fields,
            "count": len(fields)
        }
    except Exception as e:
        logger.error(f"Error fetching fields for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/catalog", response_model=FieldCatalogResponse, tags=["Field Discovery"])
def get_field_catalog(
    min_priority: float = Query(0.0, description="Minimum priority score")
):
    """
    Get the full field catalog with metadata.
    
    Returns all XBRL fields discovered across the company universe,
    with taxonomy, labels, descriptions, and priority scores.
    
    Args:
        min_priority: Minimum priority score to filter (100+ for important fields)
    
    Returns:
        Field catalog with metadata
    """
    try:
        fields = data.get_field_catalog(min_priority)
        return {
            "fields": fields,
            "count": len(fields)
        }
    except Exception as e:
        logger.error(f"Error fetching field catalog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------
# Backtesting Endpoint
# ----------------------------------------------------------------

@app.get("/backtest/{ticker}", tags=["Backtesting"])
def get_financials_as_of_date(
    ticker: str,
    as_of_date: str = Query(..., description="Date (YYYY-MM-DD) for point-in-time query"),
    fields: Optional[str] = Query(None, description="Comma-separated list of fields"),
    min_priority: float = Query(100.0, description="Minimum field priority")
):
    """
    Get all financial data available as of a specific date.
    
    **Critical for backtesting** - prevents look-ahead bias by only
    returning data that was publicly available (filed) before the
    specified date.
    
    Args:
        ticker: Stock ticker symbol
        as_of_date: Cutoff date (YYYY-MM-DD) - only data filed before this
        fields: Optional comma-separated list of specific fields
        min_priority: Minimum field priority (default 100 = important fields)
    
    Returns:
        All financial facts available as of that date
    """
    try:
        field_list = fields.split(',') if fields else None
        results = data.get_financials_as_of_date(
            ticker=ticker,
            as_of_date=as_of_date,
            fields=field_list,
            min_priority=min_priority
        )
        return {
            "ticker": ticker,
            "as_of_date": as_of_date,
            "data": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Error fetching backtest data for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------

@app.on_event("shutdown")
def shutdown_event():
    """Close database connection on shutdown."""
    data.close()
    logger.info("Database connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info"
    )
