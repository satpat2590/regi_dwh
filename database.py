"""
SQLite database layer for the SEC EDGAR financial data system.

Provides a relational store for all pipeline entities — companies, financial facts,
field metadata, point-in-time events, and TTM metrics. Can be populated from existing
JSON report files or written to incrementally by SEC.py and enrich.py.

Usage:
    # Standalone: populate DB from existing JSON reports
    python database.py

    # Programmatic: import and use in pipeline
    from database import DatabaseManager
    db = DatabaseManager()
    db.upsert_companies([company1, company2])
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from models import Company


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "financials.db")


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Reference data
CREATE TABLE IF NOT EXISTS companies (
    ticker          TEXT PRIMARY KEY,
    cik             TEXT NOT NULL,
    entity_name     TEXT DEFAULT '',
    sector          TEXT DEFAULT '',
    industry        TEXT DEFAULT '',
    sic_code        TEXT DEFAULT '',
    fye_month       TEXT DEFAULT '',
    market_cap_tier TEXT DEFAULT 'large'
);

CREATE TABLE IF NOT EXISTS fiscal_year_metadata (
    ticker                TEXT PRIMARY KEY REFERENCES companies(ticker),
    fiscal_year_end_month TEXT NOT NULL,
    confidence            TEXT DEFAULT '',
    sample_size           INTEGER DEFAULT 0,
    dominant_month_pct    REAL DEFAULT 0.0,
    filing_forms_found    TEXT DEFAULT '[]',
    recent_filing_date    TEXT DEFAULT ''
);

-- Field metadata
CREATE TABLE IF NOT EXISTS field_catalog (
    field_name      TEXT PRIMARY KEY,
    taxonomy        TEXT DEFAULT '',
    label           TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    count           INTEGER DEFAULT 0,
    companies_using TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS field_categories (
    field_name         TEXT PRIMARY KEY,
    label              TEXT DEFAULT '',
    taxonomy           TEXT DEFAULT '',
    statement_type     TEXT DEFAULT '',
    temporal_nature    TEXT DEFAULT '',
    accounting_concept TEXT DEFAULT '[]',
    is_critical        INTEGER DEFAULT 0,
    special_handling   TEXT DEFAULT '[]',
    companies_using    TEXT DEFAULT '[]',
    count              INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS field_priorities (
    field_name     TEXT PRIMARY KEY,
    priority_score REAL DEFAULT 0.0,
    availability   REAL DEFAULT 0.0,
    is_critical    INTEGER DEFAULT 0,
    tier           TEXT DEFAULT 'very_rare'
);

-- Core transactional data
CREATE TABLE IF NOT EXISTS financial_facts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL REFERENCES companies(ticker),
    cik                 TEXT NOT NULL,
    entity_name         TEXT DEFAULT '',
    sector              TEXT DEFAULT '',
    industry            TEXT DEFAULT '',
    field               TEXT NOT NULL,
    field_label         TEXT DEFAULT '',
    statement_type      TEXT DEFAULT '',
    temporal_type       TEXT DEFAULT '',
    period_start        TEXT,
    period_end          TEXT,
    value               REAL,
    unit                TEXT DEFAULT '',
    filing_date         TEXT,
    data_available_date TEXT,
    fiscal_year         INTEGER,
    fiscal_period       TEXT,
    form                TEXT DEFAULT '',
    is_amended          INTEGER DEFAULT 0,
    field_priority      REAL DEFAULT 0.0,
    taxonomy            TEXT DEFAULT '',
    account_number      TEXT,
    frame               TEXT,
    UNIQUE(ticker, field, period_end, fiscal_period, unit, account_number)
);

-- Temporal / derived
CREATE TABLE IF NOT EXISTS point_in_time_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL REFERENCES companies(ticker),
    filing_date TEXT NOT NULL,
    period_end  TEXT NOT NULL,
    form        TEXT DEFAULT '',
    fy          INTEGER,
    fp          TEXT,
    accession   TEXT,
    UNIQUE(ticker, filing_date, period_end, form, accession)
);

CREATE TABLE IF NOT EXISTS ttm_metrics (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT NOT NULL REFERENCES companies(ticker),
    metric_name    TEXT NOT NULL,
    as_of_date     TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    ttm_value      REAL NOT NULL,
    source_filing  TEXT DEFAULT '',
    UNIQUE(ticker, metric_name, as_of_date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ff_ticker_fy_fp ON financial_facts(ticker, fiscal_year, fiscal_period);
CREATE INDEX IF NOT EXISTS idx_ff_ticker_field_pe ON financial_facts(ticker, field, period_end);
CREATE INDEX IF NOT EXISTS idx_ff_sector ON financial_facts(sector);
CREATE INDEX IF NOT EXISTS idx_ff_filing_date ON financial_facts(filing_date);
CREATE INDEX IF NOT EXISTS idx_pit_ticker_fd ON point_in_time_events(ticker, filing_date);
CREATE INDEX IF NOT EXISTS idx_ttm_ticker_metric ON ttm_metrics(ticker, metric_name, as_of_date);

-- Equity market data (yfinance)
CREATE TABLE IF NOT EXISTS equity_prices (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  INTEGER,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS equity_dividends (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    amount  REAL NOT NULL,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS equity_splits (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    ratio   REAL NOT NULL,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS equity_info (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                TEXT NOT NULL,
    fetched_date          TEXT NOT NULL,
    market_cap            REAL,
    trailing_pe           REAL,
    forward_pe            REAL,
    price_to_book         REAL,
    dividend_yield        REAL,
    beta                  REAL,
    fifty_two_week_high   REAL,
    fifty_two_week_low    REAL,
    average_volume        INTEGER,
    sector                TEXT DEFAULT '',
    industry              TEXT DEFAULT '',
    UNIQUE(ticker, fetched_date)
);

CREATE INDEX IF NOT EXISTS idx_ei_ticker ON equity_info(ticker, fetched_date);

-- Crypto Market Data
CREATE TABLE IF NOT EXISTS crypto_prices (
    symbol      TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    date        TEXT NOT NULL,
    interval    TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    quote_volume REAL,
    trades      INTEGER,
    PRIMARY KEY (symbol, timestamp, interval)
);

CREATE TABLE IF NOT EXISTS crypto_info (
    symbol              TEXT PRIMARY KEY,
    name                TEXT,
    base_asset          TEXT,
    quote_asset         TEXT,
    exchange            TEXT,
    last_updated        TEXT
);

CREATE INDEX IF NOT EXISTS idx_cp_symbol_date ON crypto_prices(symbol, date);
"""


class DatabaseManager:
    """SQLite database manager for the financial data pipeline."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------
    # Companies
    # ------------------------------------------------------------------

    def upsert_companies(self, companies: list[Company]) -> int:
        """Insert or replace Company records. Returns count inserted."""
        sql = """
            INSERT OR REPLACE INTO companies
                (ticker, cik, entity_name, sector, industry, sic_code, fye_month, market_cap_tier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (c.ticker, c.cik, c.entity_name, c.sector.value if hasattr(c.sector, 'value') else c.sector,
             c.industry, c.sic_code, c.fye_month,
             c.market_cap_tier.value if hasattr(c.market_cap_tier, 'value') else c.market_cap_tier)
            for c in companies
        ]
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    def get_company(self, ticker: str) -> dict | None:
        cur = self.conn.execute("SELECT * FROM companies WHERE ticker = ?", (ticker,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_sector_companies(self, sector: str) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM companies WHERE sector = ?", (sector,))
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Fiscal Year Metadata
    # ------------------------------------------------------------------

    def upsert_fiscal_year_metadata(self, metadata: dict) -> int:
        """Upsert from fiscal_year_metadata.json format: {ticker: {fields...}}"""
        sql = """
            INSERT OR REPLACE INTO fiscal_year_metadata
                (ticker, fiscal_year_end_month, confidence, sample_size,
                 dominant_month_pct, filing_forms_found, recent_filing_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        rows = []
        for ticker, m in metadata.items():
            rows.append((
                ticker,
                m.get("fiscal_year_end_month", ""),
                m.get("confidence", ""),
                m.get("sample_size", 0),
                m.get("dominant_month_pct", 0.0),
                json.dumps(m.get("filing_forms_found", [])),
                m.get("recent_filing_date", ""),
            ))
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Field Catalog
    # ------------------------------------------------------------------

    def upsert_field_catalog(self, catalog: dict) -> int:
        """Upsert from field_catalog.json format: {field_name: {fields...}}"""
        sql = """
            INSERT OR REPLACE INTO field_catalog
                (field_name, taxonomy, label, description, count, companies_using)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        rows = []
        for field_name, f in catalog.items():
            rows.append((
                field_name,
                f.get("taxonomy", ""),
                f.get("label", ""),
                f.get("description", ""),
                f.get("count", 0),
                json.dumps(f.get("companies_using", [])),
            ))
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Field Categories
    # ------------------------------------------------------------------

    def upsert_field_categories(self, categories: dict) -> int:
        """Upsert from field_categories.json format: {field_name: {fields...}}"""
        sql = """
            INSERT OR REPLACE INTO field_categories
                (field_name, label, taxonomy, statement_type, temporal_nature,
                 accounting_concept, is_critical, special_handling, companies_using, count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = []
        for field_name, c in categories.items():
            rows.append((
                field_name,
                c.get("label", ""),
                c.get("taxonomy", ""),
                c.get("statement_type", ""),
                c.get("temporal_nature", ""),
                json.dumps(c.get("accounting_concept", [])),
                1 if c.get("is_critical") else 0,
                json.dumps(c.get("special_handling", [])),
                json.dumps(c.get("companies_using", [])),
                c.get("count", 0),
            ))
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Field Priorities
    # ------------------------------------------------------------------

    def upsert_field_priorities(self, priorities: dict) -> int:
        """Upsert from field_priority.json format: {field_name: {fields...}}"""
        sql = """
            INSERT OR REPLACE INTO field_priorities
                (field_name, priority_score, availability, is_critical, tier)
            VALUES (?, ?, ?, ?, ?)
        """
        rows = []
        for field_name, p in priorities.items():
            rows.append((
                field_name,
                p.get("priority_score", 0.0),
                p.get("availability", 0.0),
                1 if p.get("is_critical") else 0,
                p.get("tier", "very_rare"),
            ))
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Financial Facts
    # ------------------------------------------------------------------

    def upsert_financial_facts(self, facts: list[dict]) -> int:
        """
        Insert financial fact rows. Skips duplicates via UNIQUE constraint.
        Accepts list of dicts with keys matching the SEC.py row format.
        """
        sql = """
            INSERT OR IGNORE INTO financial_facts
                (ticker, cik, entity_name, sector, industry, field, field_label,
                 statement_type, temporal_type, period_start, period_end, value,
                 unit, filing_date, data_available_date, fiscal_year, fiscal_period,
                 form, is_amended, field_priority, taxonomy, account_number, frame)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = []
        for f in facts:
            rows.append((
                f.get("Ticker", ""),
                f.get("CIK", ""),
                f.get("EntityName", ""),
                f.get("Sector", ""),
                f.get("Industry", ""),
                f.get("Field", ""),
                f.get("FieldLabel", ""),
                f.get("StatementType", ""),
                f.get("TemporalType", ""),
                f.get("PeriodStart"),
                f.get("PeriodEnd"),
                f.get("Value"),
                f.get("Unit", ""),
                f.get("FilingDate"),
                f.get("DataAvailableDate"),
                f.get("FiscalYear"),
                f.get("FiscalPeriod"),
                f.get("Form", ""),
                1 if f.get("IsAmended") else 0,
                f.get("FieldPriority", 0.0),
                f.get("Taxonomy", ""),
                f.get("AccountNumber"),
                f.get("Frame"),
            ))
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Point-in-Time Events
    # ------------------------------------------------------------------

    def upsert_point_in_time_events(self, events_by_ticker: dict) -> int:
        """
        Upsert from point_in_time_map.json format: {ticker: [{event}, ...]}
        """
        sql = """
            INSERT OR IGNORE INTO point_in_time_events
                (ticker, filing_date, period_end, form, fy, fp, accession)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        rows = []
        for ticker, events in events_by_ticker.items():
            for e in events:
                rows.append((
                    ticker,
                    e.get("filing_date", ""),
                    e.get("period_end", ""),
                    e.get("form", ""),
                    e.get("fy"),
                    e.get("fp"),
                    e.get("accession"),
                ))
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # TTM Metrics
    # ------------------------------------------------------------------

    def upsert_ttm_metrics(self, metrics_by_ticker: dict) -> int:
        """
        Upsert from ttm_metrics.json format: {ticker: {metric_name: [{record}, ...]}}
        """
        sql = """
            INSERT OR REPLACE INTO ttm_metrics
                (ticker, metric_name, as_of_date, period_end, ttm_value, source_filing)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        rows = []
        for ticker, metrics in metrics_by_ticker.items():
            for metric_name, records in metrics.items():
                for r in records:
                    rows.append((
                        ticker,
                        metric_name,
                        r.get("as_of_date", ""),
                        r.get("period_end", ""),
                        r.get("ttm_value", 0.0),
                        r.get("source_filing", ""),
                    ))
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Incremental update helpers
    # ------------------------------------------------------------------

    def get_ticker_latest_filing(self, ticker: str) -> str | None:
        """Return the most recent filing_date for a ticker, or None if no data."""
        cur = self.conn.execute(
            "SELECT MAX(filing_date) AS latest FROM financial_facts WHERE ticker = ?",
            (ticker,),
        )
        row = cur.fetchone()
        return row["latest"] if row and row["latest"] else None

    # ------------------------------------------------------------------
    # Equity Market Data
    # ------------------------------------------------------------------

    def upsert_equity_prices(self, rows: list[dict]) -> int:
        """Insert equity price rows. Skips duplicates via UNIQUE constraint."""
        sql = """
            INSERT OR IGNORE INTO equity_prices
                (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (r["ticker"], r["date"], r.get("open"), r.get("high"),
             r.get("low"), r.get("close"), r.get("volume"))
            for r in rows
        ]
        self.conn.executemany(sql, params)
        self.conn.commit()
        return len(params)

    def upsert_equity_dividends(self, rows: list[dict]) -> int:
        """Insert equity dividend rows. Skips duplicates."""
        sql = """
            INSERT OR IGNORE INTO equity_dividends
                (ticker, date, amount)
            VALUES (?, ?, ?)
        """
        params = [(r["ticker"], r["date"], r["amount"]) for r in rows]
        self.conn.executemany(sql, params)
        self.conn.commit()
        return len(params)

    def upsert_equity_splits(self, rows: list[dict]) -> int:
        """Insert equity split rows. Skips duplicates."""
        sql = """
            INSERT OR IGNORE INTO equity_splits
                (ticker, date, ratio)
            VALUES (?, ?, ?)
        """
        params = [(r["ticker"], r["date"], r["ratio"]) for r in rows]
        self.conn.executemany(sql, params)
        self.conn.commit()
        return len(params)

    def upsert_equity_info(self, rows: list[dict]) -> int:
        """Insert equity info snapshots. Skips duplicates."""
        sql = """
            INSERT OR IGNORE INTO equity_info
                (ticker, fetched_date, market_cap, trailing_pe, forward_pe,
                 price_to_book, dividend_yield, beta, fifty_two_week_high,
                 fifty_two_week_low, average_volume, sector, industry)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (r["ticker"], r["fetched_date"], r.get("market_cap"),
             r.get("trailing_pe"), r.get("forward_pe"), r.get("price_to_book"),
             r.get("dividend_yield"), r.get("beta"), r.get("fifty_two_week_high"),
             r.get("fifty_two_week_low"), r.get("average_volume"),
             r.get("sector", ""), r.get("industry", ""))
            for r in rows
        ]
        self.conn.executemany(sql, params)
        self.conn.commit()
        return len(params)


    def get_ticker_latest_price(self, ticker: str) -> str | None:
        """Return the most recent price date for a ticker, or None if no data."""
        cur = self.conn.execute(
            "SELECT MAX(date) AS latest FROM equity_prices WHERE ticker = ?",
            (ticker,),
        )
        row = cur.fetchone()
        return row["latest"] if row and row["latest"] else None

    # ------------------------------------------------------------------
    # Crypto Market Data
    # ------------------------------------------------------------------

    def upsert_crypto_prices(self, rows: list[dict]) -> int:
        """Insert crypto price rows. Skips duplicates via PRIMARY KEY."""
        sql = """
            INSERT OR IGNORE INTO crypto_prices
                (symbol, timestamp, date, interval, open, high, low, close,
                 volume, quote_volume, trades)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (r["symbol"], r["timestamp"], r["date"], r["interval"],
             r.get("open"), r.get("high"), r.get("low"), r.get("close"),
             r.get("volume"), r.get("quote_volume"), r.get("trades"))
            for r in rows
        ]
        self.conn.executemany(sql, params)
        self.conn.commit()
        return len(params)

    def upsert_crypto_info(self, info: dict) -> int:
        """Insert or update crypto coin info."""
        sql = """
            INSERT OR REPLACE INTO crypto_info
                (symbol, name, base_asset, quote_asset, exchange, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            info["symbol"], info.get("name"), info.get("base_asset"),
            info.get("quote_asset"), info.get("exchange"), info.get("last_updated")
        )
        self.conn.execute(sql, params)
        self.conn.commit()
        return 1

    def get_crypto_latest_price(self, symbol: str, interval: str) -> int | None:
        """Return the most recent timestamp for a symbol/interval, or None."""
        cur = self.conn.execute(
            "SELECT MAX(timestamp) AS latest FROM crypto_prices WHERE symbol = ? AND interval = ?",
            (symbol, interval),
        )
        row = cur.fetchone()
        return row["latest"] if row and row["latest"] else None

    # ------------------------------------------------------------------
    # Generic query
    # ------------------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a raw SQL query and return results as list of dicts."""
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Bulk population from JSON reports
    # ------------------------------------------------------------------

    def populate_from_json(self) -> None:
        """One-shot population of all tables from existing JSON report files."""
        print("Populating database from JSON reports...\n")

        # Companies
        meta_path = os.path.join(CONFIG_DIR, "company_metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                raw = json.load(f)
            companies = [Company(**data) for data in raw.values()]
            n = self.upsert_companies(companies)
            print(f"  companies:              {n} rows")
        else:
            print("  companies:              SKIPPED (no company_metadata.json)")

        # Fiscal year metadata
        fye_path = os.path.join(REPORTS_DIR, "fiscal_year_metadata.json")
        if os.path.exists(fye_path):
            with open(fye_path, 'r') as f:
                n = self.upsert_fiscal_year_metadata(json.load(f))
            print(f"  fiscal_year_metadata:   {n} rows")

        # Field catalog
        catalog_path = os.path.join(REPORTS_DIR, "field_catalog.json")
        if os.path.exists(catalog_path):
            with open(catalog_path, 'r') as f:
                n = self.upsert_field_catalog(json.load(f))
            print(f"  field_catalog:          {n} rows")

        # Field categories
        cats_path = os.path.join(REPORTS_DIR, "field_categories.json")
        if os.path.exists(cats_path):
            with open(cats_path, 'r') as f:
                n = self.upsert_field_categories(json.load(f))
            print(f"  field_categories:       {n} rows")

        # Field priorities
        prio_path = os.path.join(REPORTS_DIR, "field_priority.json")
        if os.path.exists(prio_path):
            with open(prio_path, 'r') as f:
                n = self.upsert_field_priorities(json.load(f))
            print(f"  field_priorities:       {n} rows")

        # Point-in-time events
        pit_path = os.path.join(REPORTS_DIR, "point_in_time_map.json")
        if os.path.exists(pit_path):
            with open(pit_path, 'r') as f:
                n = self.upsert_point_in_time_events(json.load(f))
            print(f"  point_in_time_events:   {n} rows")

        # TTM metrics
        ttm_path = os.path.join(REPORTS_DIR, "ttm_metrics.json")
        if os.path.exists(ttm_path):
            with open(ttm_path, 'r') as f:
                n = self.upsert_ttm_metrics(json.load(f))
            print(f"  ttm_metrics:            {n} rows")

        print(f"\nDatabase populated: {self.db_path}")


if __name__ == "__main__":
    db = DatabaseManager()
    db.populate_from_json()
    db.close()
