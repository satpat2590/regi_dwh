"""
Pydantic data models for the SEC EDGAR financial data system.

These models enforce type safety, validation, and provide a clear schema
for all core entities flowing through the pipeline. They mirror the
entity-relationship schema defined in ENTITY_RELATIONSHIP.md.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Sector(str, Enum):
    TECHNOLOGY = "Technology"
    FINANCE = "Finance"
    RETAIL = "Retail"
    HEALTHCARE = "Healthcare"
    ENERGY = "Energy"
    MINING = "Mining/Materials"
    INDUSTRIAL = "Industrial"
    TELECOM = "Telecom"
    UTILITIES = "Utilities"
    REAL_ESTATE = "Real Estate"
    TRANSPORTATION = "Transportation"
    UNKNOWN = "Unknown"


class MarketCapTier(str, Enum):
    MEGA = "mega"
    LARGE = "large"
    MID = "mid"
    SMALL = "small"
    MICRO = "micro"


class TemporalType(str, Enum):
    POINT_IN_TIME = "Point-in-Time"
    PERIOD = "Period"


class AvailabilityTier(str, Enum):
    UNIVERSAL = "universal"
    VERY_COMMON = "very_common"
    COMMON = "common"
    MODERATE = "moderate"
    RARE = "rare"
    VERY_RARE = "very_rare"


# ---------------------------------------------------------------------------
# Core Entities
# ---------------------------------------------------------------------------

class Company(BaseModel):
    """
    Central entity representing a publicly traded company.
    Enriched with sector/industry data from SEC SIC codes.
    """
    ticker: str
    cik: str
    entity_name: str = ""
    sector: Sector = Sector.UNKNOWN
    industry: str = ""
    sic_code: str = ""
    fye_month: str = ""
    market_cap_tier: MarketCapTier = MarketCapTier.LARGE


class FiscalYearMetadata(BaseModel):
    """Metadata about a company's fiscal calendar."""
    ticker: str
    fiscal_year_end_month: str
    confidence: str
    sample_size: int
    dominant_month_pct: float
    filing_forms_found: list[str] = []
    recent_filing_date: str


class FinancialFact(BaseModel):
    """
    A single financial data point extracted from an SEC filing.
    This is the primary entity for analysis and trading.
    """
    ticker: str
    cik: str
    entity_name: str
    field: str
    field_label: str = ""
    statement_type: str = ""
    temporal_type: str = ""
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    value: Optional[float] = None
    unit: str = ""
    filing_date: Optional[str] = None
    data_available_date: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    form: str = ""
    is_amended: bool = False
    field_priority: float = 0.0
    taxonomy: str = ""
    account_number: Optional[str] = None
    frame: Optional[str] = None
    # Enrichment fields
    sector: str = ""
    industry: str = ""


class FieldCatalogEntry(BaseModel):
    """A field discovered in the XBRL taxonomy across the company universe."""
    field_name: str
    taxonomy: str = ""
    label: str = ""
    description: str = ""
    count: int = 0
    companies_using: list[str] = []


class FieldCategory(BaseModel):
    """Classification metadata for a financial field."""
    field_name: str
    label: str = ""
    taxonomy: str = ""
    statement_type: str = ""
    temporal_nature: str = ""
    accounting_concept: list[str] = []
    is_critical: bool = False
    special_handling: list[str] = []
    companies_using: list[str] = []
    count: int = 0


class FieldPriority(BaseModel):
    """Ranked importance of a field for trading and fundamental analysis."""
    field_name: str
    priority_score: float = 0.0
    availability: float = 0.0
    is_critical: bool = False
    tier: AvailabilityTier = AvailabilityTier.VERY_RARE


class PointInTimeEvent(BaseModel):
    """
    A filing event in the historical timeline.
    Maps fiscal periods to their actual public disclosure dates.
    """
    ticker: str
    filing_date: str
    period_end: str
    form: str = ""
    fy: Optional[int] = None
    fp: Optional[str] = None
    accession: Optional[str] = None


class TTMMetric(BaseModel):
    """Trailing Twelve Month annualized metric for a company."""
    ticker: str
    metric_name: str
    as_of_date: str
    period_end: str
    ttm_value: float
    source_filing: str = ""


# ---------------------------------------------------------------------------
# Equity Market Data (yfinance)
# ---------------------------------------------------------------------------

class EquityPrice(BaseModel):
    """Daily OHLCV price record for a ticker."""
    ticker: str
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None


class EquityDividend(BaseModel):
    """Dividend payment event."""
    ticker: str
    date: str
    amount: float


class EquitySplit(BaseModel):
    """Stock split event."""
    ticker: str
    date: str
    ratio: float


class EquityInfo(BaseModel):
    """Snapshot of key market data and valuation ratios from yfinance."""
    ticker: str
    fetched_date: str
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    price_to_book: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    average_volume: Optional[int] = None
    sector: str = ""
    industry: str = ""


# ---------------------------------------------------------------------------
# News Articles
# ---------------------------------------------------------------------------

class NewsArticle(BaseModel):
    """A news article fetched from a news data provider."""
    provider: str
    source_name: str = ""
    title: str
    description: str = ""
    url: str
    published_at: str
    fetched_at: str = ""
    category: str = ""
    sentiment: Optional[float] = None
    sentiment_label: str = ""
    sentiment_source: str = ""
    image_url: str = ""
    topics: list[str] = []


# ---------------------------------------------------------------------------
# FRED Macro Economic Indicators
# ---------------------------------------------------------------------------

class FredSeriesMeta(BaseModel):
    """Metadata for a FRED economic data series."""
    series_id: str
    title: str = ""
    units: str = ""
    frequency: str = ""
    seasonal_adj: str = ""
    last_updated: str = ""
    notes: str = ""


class FredObservation(BaseModel):
    """A single observation (data point) from a FRED series."""
    series_id: str
    date: str
    value: Optional[float] = None
