"""
Pydantic models for API request/response validation.
Auto-generates OpenAPI documentation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Any


class CompanyResponse(BaseModel):
    """Company metadata response."""
    ticker: str
    cik: str
    entity_name: str
    sector: str
    industry: str
    sic_code: str
    fye_month: str
    market_cap_tier: str


class MetricResponse(BaseModel):
    """Single financial metric response."""
    id: Optional[int] = None
    ticker: str
    field: str
    field_label: str
    value: Optional[float]
    unit: str
    period_start: Optional[str]
    period_end: Optional[str]
    filing_date: Optional[str]
    fiscal_year: Optional[int]
    fiscal_period: Optional[str]
    statement_type: str
    temporal_type: str


class TimeSeriesResponse(BaseModel):
    """Time series data response."""
    ticker: str
    field: str
    data: List[MetricResponse]
    count: int


class TTMResponse(BaseModel):
    """TTM metric response."""
    id: Optional[int] = None
    ticker: str
    metric_name: str
    ttm_value: float
    as_of_date: str
    period_end: str
    source_filing: Optional[str] = None


class CryptoPrice(BaseModel):
    symbol: str
    timestamp: int
    date: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None
    trades: Optional[int] = None


class CryptoInfo(BaseModel):
    symbol: str
    name: Optional[str] = None
    base_asset: Optional[str] = None
    quote_asset: Optional[str] = None
    exchange: Optional[str] = None
    last_updated: Optional[str] = None


class CryptoHistoryResponse(BaseModel):
    symbol: str
    interval: str
    count: int
    prices: List[CryptoPrice]


class TTMTimeSeriesResponse(BaseModel):
    """TTM time series response."""
    ticker: str
    metric_name: str
    data: List[TTMResponse]
    count: int


class SectorTickersResponse(BaseModel):
    """Sector tickers list response."""
    sector: str
    tickers: List[str]
    count: int


class SectorComparisonItem(BaseModel):
    """Single company in sector comparison."""
    ticker: str
    entity_name: str
    value: Optional[float]
    period_end: Optional[str]
    filing_date: Optional[str]
    fiscal_year: Optional[int]
    fiscal_period: Optional[str]


class SectorComparisonResponse(BaseModel):
    """Sector comparison response."""
    sector: str
    field: str
    fiscal_period: str
    companies: List[SectorComparisonItem]
    count: int


class FieldInfo(BaseModel):
    """Available field metadata."""
    field: str
    field_label: str
    statement_type: str
    temporal_type: str
    field_priority: float


class FieldsResponse(BaseModel):
    """Available fields response."""
    ticker: str
    fields: List[FieldInfo]
    count: int


class FieldCatalogItem(BaseModel):
    """Field catalog entry."""
    field_name: str
    taxonomy: str
    label: str
    description: str
    count: int
    priority_score: Optional[float] = None
    tier: Optional[str] = None


class FieldCatalogResponse(BaseModel):
    """Field catalog response."""
    fields: List[FieldCatalogItem]
    count: int


class DatabaseStatsResponse(BaseModel):
    """Database statistics response."""
    total_companies: int
    total_facts: int
    total_fields: int
    total_sectors: int


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    error_type: Optional[str] = None


class HealthResponse(BaseModel):
    """API health check response."""
    service: str
    version: str
    status: str
    database_path: str
    database_stats: DatabaseStatsResponse
