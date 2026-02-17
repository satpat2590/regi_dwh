# Company Financials Data Warehouse

A comprehensive multi-asset data pipeline for extracting, normalizing, enriching, and storing financial data. Combines **SEC EDGAR fundamentals** (XBRL filings), **equity market data** (prices, dividends, splits, valuation ratios), **cryptocurrency market data** (OHLCV, coin info), **news aggregation** (NewsAPI, Finnhub, GDELT), and **FRED macro economic indicators** (GDP, CPI, unemployment, rates) in a unified SQLite database. Designed for downstream use in sector/industry profiling, fundamental analysis, macro research, trading signal generation, and backtesting.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Pipeline Components](#pipeline-components)
  - [1. Pipeline Orchestrator (run_pipeline.sh)](#1-pipeline-orchestrator-run_pipelinesh)
  - [2. Enrichment Layer (enrich.py)](#2-enrichment-layer-enrichpy)
  - [3. SEC EDGAR Extraction (SEC.py)](#3-sec-edgar-extraction-secpy)
  - [4. Equity Market Data (Equity.py)](#4-equity-market-data-equitypy)
  - [5. Crypto Market Data (Crypto.py)](#5-crypto-market-data-cryptopy)
  - [6. News Aggregation (News.py)](#6-news-aggregation-newspy)
  - [7. FRED Macro Economic Data (Fred.py)](#7-fred-macro-economic-data-fredpy)
  - [8. Field Analysis Pipeline (tasks/)](#8-field-analysis-pipeline-tasks)
  - [9. Data Models (models.py)](#9-data-models-modelspy)
  - [10. Database Layer (database.py)](#10-database-layer-databasepy)
  - [11. Utilities (utils/)](#11-utilities-utils)
- [Database Schema](#database-schema)
- [Data Entities](#data-entities)
- [Company Universe](#company-universe)
- [Configuration Files](#configuration-files)
- [Report Files](#report-files)
- [Usage Examples](#usage-examples)
  - [SQL Query Examples](#sql-query-examples)
  - [Python API Examples](#python-api-examples)
- [Design Invariants](#design-invariants)
- [Dependencies](#dependencies)
- [Known Issues](#known-issues)
- [Future Roadmap](#future-roadmap)

---

## Architecture Overview

```
   SEC EDGAR API        Yahoo Finance API    Binance/Coinbase   NewsAPI/Finnhub/GDELT  FRED API
        |                      |                    |                    |                |
        +----------+   +-------+       +------------+       +----------+     +----------+
        |          |   |               |                    |                |
   /submissions/ /api/xbrl/ yfinance  get_klines()   REST APIs        /fred/series/
   CIK*.json   companyfacts/ (prices, (OHLCV)        (articles)       observations
               CIK*.json   divs,splits)
        |          |   |               |                    |                |
        v          v   v               v                    v                v
   +---------+ +-------+ +--------+ +----------+  +-----------+  +-----------+
   |enrich.py| |SEC.py | |Equity  | | Crypto   |  |  News     |  |  Fred     |
   +---------+ +-------+ +--------+ +----------+  | Pipeline  |  | Pipeline  |
        |          |         |            |        +-----------+  +-----------+
        v          v         v            v              |              |
   company_  financial_ equity_     crypto_         news_         fred_series_
   metadata  facts      prices      prices         articles      meta
             ttm_metrics equity_divs crypto_info    article_      fred_
             pit_events  equity_info                topics        observations
        |          |         |            |              |              |
        +-----+----+---------+------------+--------------+--------------+
              |           |
              v           v
       data/financials.db    Excel exports
       (unified SQLite)      (*.xlsx snapshots)
              |
              v
       Downstream Consumers
  (sector profiling, trading signals,
   macro research, backtesting)
```

### Data Flow

1. **`run_pipeline.sh`** orchestrates the full pipeline — reads `input.txt` for the ticker list, then runs:
   - Step 1: Company enrichment (SIC → sector/industry)
   - Step 2: SEC EDGAR XBRL fundamentals
   - Step 3: Equity market data (optional, requires API key)
   - Step 4: Cryptocurrency market data (Binance/Coinbase)
   - Step 5: News aggregation (NewsAPI/Finnhub/GDELT)
   - Step 5.5: NLP sentiment enrichment (VADER)
   - Step 6: FRED macro economic indicators

2. **`enrich.py`** fetches company metadata (SIC codes, entity names) from the SEC submissions endpoint and maps SIC codes to sectors/industries. Outputs `config/company_metadata.json` and writes to SQLite.

3. **Field analysis pipeline** (`tasks/`) runs once to catalog, categorize, and prioritize all 4,148 XBRL fields across the company universe. Outputs go to `reports/`.

4. **`SEC.py`** (sources/sec_edgar/pipeline.py) fetches XBRL company facts, normalizes temporal data, enriches with sector/industry tags, and writes to both Excel and SQLite.

5. **`Equity.py`** (sources/equity/pipeline.py) fetches daily OHLCV prices, dividends, splits, and key valuation ratios from equity data providers. Currently supports Alpha Vantage. Writes to SQLite and Excel.

6. **`Crypto.py`** (sources/crypto/pipeline.py) fetches cryptocurrency OHLCV data and coin information from Binance (US) or Coinbase. Writes to SQLite and Excel.

7. **`News.py`** (sources/news/pipeline.py) aggregates macro-focused news articles from NewsAPI.org, Finnhub, and GDELT. Deduplicates by URL and stores with topic tags and sentiment scores.

8. **`Fred.py`** (sources/fred/pipeline.py) fetches economic indicator time series from the FRED API (GDP, CPI, unemployment, interest rates, etc.). Supports incremental updates.

9. **`database.py`** provides the SQLite database layer. Can be populated standalone from existing JSON reports or written to incrementally by the pipeline scripts.

---

## Quick Start

### Prerequisites

```bash
pip install requests pandas openpyxl beautifulsoup4 fake-useragent pydantic colorama yfinance python-dotenv
```

### Option A: Run the full pipeline (recommended)

```bash
# Edit input.txt to choose your tickers, then:
./run_pipeline.sh
```

This runs all pipeline steps (enrichment → SEC fundamentals → equity market data → crypto data → news → sentiment enrichment → FRED) for tickers in `input.txt` and writes to both Excel and SQLite.

### Option B: Run individual steps

```bash
# Step 1: Enrich company metadata
python sources/sec_edgar/enrich.py

# Step 2: Extract SEC fundamentals
python sources/sec_edgar/pipeline.py

# Step 3: Extract equity market data (optional, requires API key)
python sources/equity/pipeline.py

# Step 4: Extract crypto market data
python sources/crypto/pipeline.py

# Step 5: Fetch news articles (GDELT needs no key; NewsAPI/Finnhub need keys)
python sources/news/pipeline.py --provider gdelt --days 3

# Step 5.5: Enrich news articles with VADER sentiment
python sources/news/enrich_sentiment.py

# Step 6: Fetch FRED macro economic data (requires FRED_API_KEY)
python sources/fred/pipeline.py --series GDP UNRATE --days 365

# Step 7: Populate database from existing JSON reports
python database.py

# Step 8: Query the database
sqlite3 data/financials.db "SELECT ticker, sector, industry FROM companies ORDER BY sector;"
```

### Ticker Input

Tickers are controlled via `input.txt` (one per line, `#` for comments):

```
# Technology
AAPL
MSFT
NVDA

# Finance
JPM
GS
```

Override from the command line:

```bash
./run_pipeline.sh --tickers AAPL MSFT JPM
./run_pipeline.sh --input-file my_tickers.txt
./run_pipeline.sh --force                                    # Bypass cache, re-fetch all data
./run_pipeline.sh --news-provider gdelt --news-days 3        # Customize news step
./run_pipeline.sh --fred-series GDP UNRATE --fred-days 365   # Customize FRED step
```

---

## Project Structure

```
company_financials/
|
|-- run_pipeline.sh                    # Bash orchestrator (enrich → SEC → Equity → Crypto → News → FRED)
|-- database.py                        # SQLite database manager
|-- models.py                          # Pydantic data models for all entities
|-- input.txt                          # Ticker list for pipeline runs
|
|-- sources/
|   |-- __init__.py
|   |-- sec_edgar/                     # SEC EDGAR fundamentals pipeline
|   |   |-- pipeline.py                # Main XBRL extraction (SEC.py)
|   |   |-- enrich.py                  # Company enrichment (SIC → sector/industry)
|   |   |-- config/                    # CIK mappings, company metadata, SIC mappings
|   |   |-- data/                      # EDGAR Excel exports
|   |   |-- reports/                   # Field analysis outputs
|   |   |-- tasks/                     # Field analysis pipeline
|   |
|   |-- equity/                        # Equity market data pipeline
|   |   |-- __init__.py
|   |   |-- pipeline.py                # Multi-provider equity data extractor
|   |   |-- providers/                 # Data provider implementations
|   |   |   |-- base.py                # Base provider interface
|   |   |   |-- alpha_vantage.py       # Alpha Vantage provider
|   |   |-- data/                      # Equity Excel exports
|   |
|   |-- crypto/                        # Crypto market data pipeline
|   |   |-- __init__.py
|   |   |-- pipeline.py                # Multi-provider crypto data extractor
|   |   |-- providers/                 # Crypto exchange implementations
|   |   |   |-- base.py                # Base provider interface
|   |   |   |-- binance_provider.py    # Binance exchange
|   |   |   |-- coinbase_provider.py   # Coinbase exchange
|   |   |-- data/                      # Crypto Excel exports
|   |
|   |-- news/                          # News aggregation pipeline
|   |   |-- __init__.py
|   |   |-- pipeline.py                # Multi-provider news orchestrator
|   |   |-- enrich_sentiment.py        # VADER sentiment enrichment (post-ingest)
|   |   |-- providers/                 # News provider implementations
|   |       |-- __init__.py
|   |       |-- base.py                # NewsDataProvider ABC + exceptions
|   |       |-- newsapi_provider.py    # NewsAPI.org (100 req/day, 1mo lookback)
|   |       |-- finnhub_provider.py    # Finnhub (60 calls/min, sentiment)
|   |       |-- gdelt_provider.py      # GDELT (unlimited, no key needed)
|   |
|   |-- fred/                          # FRED macro economic data pipeline
|       |-- __init__.py
|       |-- pipeline.py                # FRED pipeline orchestrator
|       |-- provider.py                # Single FRED API provider
|
|-- config/
|   |-- cik.json                       # Ticker → CIK mapping (~9,700 entries)
|   |-- company_metadata.json          # Enriched company profiles
|   |-- sic_to_sector.json             # SIC code range → sector/industry mapping
|   |-- crypto_watchlist.json          # Default crypto symbols to fetch
|   |-- news_watchlist.json           # Macro-focused news search queries
|   |-- fred_series.json              # FRED series IDs to track (GDP, CPI, etc.)
|   |-- loggingConfig.json             # Logging configuration
|
|-- data/
|   |-- financials.db                  # SQLite database (unified storage)
|   |-- EDGAR_FINANCIALS_*.xlsx        # SEC data Excel exports
|   |-- EQUITY_DATA_*.xlsx             # Equity data Excel exports
|   |-- CRYPTO_DATA_*.xlsx             # Crypto data Excel exports
|
|-- reports/
|   |-- field_catalog.json             # 4,148 XBRL fields discovered
|   |-- field_catalog_metadata.json    # Catalog generation metadata
|   |-- field_categories.json          # Field classification
|   |-- field_priority.json            # Field importance rankings
|   |-- field_availability_report.json # Cross-company field coverage
|   |-- field_mapping.json             # Deprecated/synonym field mappings
|   |-- fiscal_year_metadata.json      # Company fiscal calendar data
|   |-- point_in_time_map.json         # Filing event timeline
|   |-- ttm_metrics.json               # Trailing Twelve Month calculations
|
|-- utils/
|   |-- __init__.py
|   |-- session.py                     # HTTP session with rate limiting
|   |-- excel_formatter.py             # Excel workbook formatting
|   |-- log.py                         # Color-coded pipeline logging
|   |-- input_parser.py                # Ticker file parser
|
|-- logs/
|   |-- pipeline.log                   # Verbose DEBUG-level pipeline log
|
|-- ENTITY_RELATIONSHIP.md             # Full entity-relationship schema reference
|-- README.md                          # This file
```

---

## Pipeline Components

### 1. Pipeline Orchestrator (`run_pipeline.sh`)

Bash script that runs the full pipeline end-to-end:
1. Company enrichment (SIC → sector/industry)
2. SEC EDGAR XBRL fundamentals
3. Equity market data (optional, graceful failure if no API key)
4. Cryptocurrency market data (Binance/Coinbase)
5. News aggregation (NewsAPI/Finnhub/GDELT) — non-fatal
5.5. NLP sentiment enrichment (VADER) — non-fatal
6. FRED macro economic indicators — non-fatal

Steps 1-4 use stock/crypto ticker sources. Steps 5-6 use their own config files and have separate CLI args namespaced with `--news-*` and `--fred-*` prefixes to avoid conflicts. Step 5.5 automatically scores unenriched articles after ingest.

**Features:**
- Color-coded terminal output with timestamps
- Smart arg routing: stock args, crypto args, news args, and FRED args are split and forwarded to their respective pipelines
- Exits immediately on core failures (`set -euo pipefail`)
- Graceful handling of equity/news/FRED failures (warns and continues)
- Displays ticker count from `input.txt` before starting

**Usage:**
```bash
./run_pipeline.sh                                            # Process tickers from input.txt
./run_pipeline.sh --tickers AAPL MSFT                        # Process specific tickers
./run_pipeline.sh --input-file my.txt                        # Process from custom file
./run_pipeline.sh --force                                    # Bypass cache, re-fetch all data
./run_pipeline.sh --news-provider gdelt --news-days 3        # Customize news step
./run_pipeline.sh --fred-series GDP UNRATE --fred-days 365   # Customize FRED step
```

---

### 2. Enrichment Layer (`enrich.py`)

Fetches company metadata from the SEC submissions endpoint and maps SIC codes to sectors and industries.

**What it does:**
- Reads `config/cik.json` for ticker-to-CIK mappings
- Calls `https://data.sec.gov/submissions/CIK{cik}.json` for each ticker
- Extracts `sic`, `sicDescription`, and `name` from the response
- Maps the 4-digit SIC code to a sector using `config/sic_to_sector.json`
- Merges fiscal year end month from `reports/fiscal_year_metadata.json`
- Validates each record through the `Company` Pydantic model
- Writes to both `config/company_metadata.json` and the SQLite `companies` table

**Usage:**
```bash
python sources/sec_edgar/enrich.py                          # Enrich tickers from input.txt
python sources/sec_edgar/enrich.py --tickers AAPL MSFT JPM  # Enrich specific tickers
python sources/sec_edgar/enrich.py --input-file my.txt      # Enrich from custom file
```

**Caching:** If `company_metadata.json` already contains a ticker with a SIC code, that ticker is skipped (uses cached data). Delete the file to force a full re-fetch.

**SIC-to-Sector Mapping (`config/sic_to_sector.json`):**

The mapping covers ~70 SIC code ranges. When multiple ranges overlap (e.g., SIC 3571 matches both `3500-3569 Industrial` and `3570-3579 Technology`), the narrowest (most specific) range wins. Key mappings:

| SIC Range | Sector | Industry Group |
|-----------|--------|----------------|
| 1000-1499 | Mining/Materials | Mining |
| 2830-2869 | Healthcare | Pharmaceuticals |
| 2900-2999 | Energy | Petroleum Refining |
| 3570-3579 | Technology | Computer Hardware |
| 3670-3679 | Technology | Semiconductors |
| 4800-4899 | Telecom | Communications |
| 4910-4941 | Utilities | Electric Services |
| 5000-5999 | Retail | Wholesale/Retail Trade |
| 6000-6299 | Finance | Banking, Brokers |
| 6320-6329 | Healthcare | Health Insurance |
| 6798-6798 | Finance | REITs |
| 7370-7379 | Technology | Computer & Data Processing |

---

### 3. SEC EDGAR Extraction (`SEC.py`)

The main extraction engine for fundamentals. Fetches XBRL company facts from SEC EDGAR, normalizes temporal data, enriches with sector/industry, and persists to Excel and SQLite.

**Class: `SEC`**

**Constructor workflow:**
1. Loads CIK mapping (`config/cik.json`)
2. Loads company enrichment metadata (`config/company_metadata.json`) — validated through Pydantic `Company` model
3. Loads field categories and priorities from `reports/`
4. For each ticker: fetches XBRL data, normalizes, enriches, collects records
5. Saves per-statement-type sheets to Excel (Balance Sheet, Income Statement, Cash Flow, etc.) plus a Ticker Summary sheet
6. Writes all `FinancialFact` records to SQLite `financial_facts` table

**Excel output:**

The full dataset (1M+ rows at scale) goes exclusively to SQLite. Excel gets per-statement-type sheets which stay within the 1,048,576 row limit, plus a summary sheet:

| Sheet | Description | Typical Size |
|-------|-------------|-------------|
| `Balance_Sheet` | Assets, liabilities (point-in-time) | ~150K rows |
| `Income_Statement` | Revenue, expenses, earnings (period) | ~385K rows |
| `Cash_Flow_Statement` | Operating, investing, financing flows | ~195K rows |
| `Balance_Sheet_-_Equity` | Stockholders' equity detail | ~83K rows |
| `Balance_Sheet_-_Assets` | Asset breakdown | ~147K rows |
| `Balance_Sheet_-_Liabilities` | Liability breakdown | ~35K rows |
| `Other_Footnotes` | Supplementary disclosures | ~89K rows |
| `Document_&_Entity_Information` | Filing metadata (dei taxonomy) | ~7K rows |
| `Ticker_Summary` | One row per ticker with record counts | N rows |

**Key methods:**

| Method | Description |
|--------|-------------|
| `fetch_sec_filing(ticker)` | Fetches XBRL company facts from SEC API |
| `clean_facts(json_data, ticker)` | Normalizes and enriches raw XBRL data into structured records |
| `get_field_metadata(field_name)` | Returns `(statement_type, temporal_nature, priority_score)` from analysis system |
| `normalize_temporal_data(obj, temporal_nature)` | Returns `(period_start, period_end)` based on field type |
| `get_company_enrichment(ticker)` | Returns `(sector, industry)` from enrichment data |
| `save_aggregated_data()` | Writes per-statement Excel sheets + ticker summary |
| `save_to_database()` | Writes all collected facts to SQLite |

**Caching:** Tickers with recent data (within 30 days) are skipped unless `--force` is passed.

**Usage:**
```bash
python sources/sec_edgar/pipeline.py                              # Extract for tickers in input.txt
python sources/sec_edgar/pipeline.py --tickers AAPL MSFT JPM      # Extract for specific tickers
python sources/sec_edgar/pipeline.py --input-file my_tickers.txt  # Extract from custom file
python sources/sec_edgar/pipeline.py --force                      # Bypass cache, re-fetch all
```

**Output record fields:**

Each `FinancialFact` row contains:

| Field | Type | Description |
|-------|------|-------------|
| `Ticker` | str | Stock ticker symbol |
| `CIK` | str | SEC Central Index Key |
| `EntityName` | str | Company legal name |
| `Sector` | str | Market sector from enrichment |
| `Industry` | str | Industry classification from SIC |
| `Field` | str | XBRL field name (e.g., `NetIncomeLoss`) |
| `FieldLabel` | str | Human-readable field name |
| `StatementType` | str | Balance Sheet / Income Statement / Cash Flow Statement / Other |
| `TemporalType` | str | Point-in-Time / Period |
| `PeriodStart` | date/null | Start of reporting period (null for Point-in-Time) |
| `PeriodEnd` | date | End of reporting period |
| `Value` | numeric | The reported financial value |
| `Unit` | str | USD / shares / USD/shares / pure |
| `FilingDate` | date | When filing was submitted to SEC |
| `DataAvailableDate` | date | When data became publicly known (= FilingDate) |
| `FiscalYear` | int | Fiscal year number |
| `FiscalPeriod` | str | Q1 / Q2 / Q3 / Q4 / FY |
| `Form` | str | 10-K / 10-Q / 10-K/A / 10-Q/A / 20-F / 40-F |
| `IsAmended` | bool | True if filing is an amendment |
| `FieldPriority` | float | Importance score (0-180) |
| `Taxonomy` | str | us-gaap / dei / ifrs-full / srt |
| `AccountNumber` | str | SEC accession number |
| `Frame` | str/null | Reporting frame identifier |

---

### 4. Equity Market Data (`Equity.py`)

Fetches daily OHLCV prices, dividends, splits, and key valuation ratios from equity data providers. Currently supports Alpha Vantage. Mirrors the SEC pipeline architecture for consistency.

**Class: `Equity`**

**Constructor workflow:**
1. Loads ticker list from CLI args, `--input-file`, or `input.txt`
2. Initializes data provider (Alpha Vantage)
3. Queries DB for latest price dates to enable incremental updates
4. For each ticker: fetches history, dividends, splits, and info snapshot
5. Saves to SQLite (`equity_prices`, `equity_dividends`, `equity_splits`, `equity_info` tables)
6. Generates Excel with `Equity_Summary` and `Price_Stats` sheets

**Data fetched:**

| Dataset | Description | Typical Size (per ticker) |
|---------|-------------|---------------------------|
| **Prices** | Daily OHLCV (Open, High, Low, Close, Volume) | ~1,260 rows (5 years) |
| **Dividends** | Dividend payment events with amount | ~20 rows |
| **Splits** | Stock split events with ratio | ~0-5 rows |
| **Info** | Snapshot of valuation ratios and market data | 1 row |

**Info fields captured:**
- Market cap, trailing P/E, forward P/E, price-to-book
- Dividend yield, beta
- 52-week high/low, average volume
- Sector, industry (from provider, complements SEC enrichment)

**Caching:** Tickers with price data from today or yesterday (age ≤ 1 day) are skipped unless `--force` is passed.

**Usage:**
```bash
python sources/equity/pipeline.py                              # Fetch for tickers in input.txt
python sources/equity/pipeline.py --tickers AAPL MSFT JPM      # Fetch for specific tickers
python sources/equity/pipeline.py --input-file my_tickers.txt  # Fetch from custom file
python sources/equity/pipeline.py --force                      # Bypass cache, re-fetch all
python sources/equity/pipeline.py --provider alpha_vantage     # Specify provider
```

**Note:** Requires `ALPHA_VANTAGE_API_KEY` environment variable. If not set, the pipeline gracefully skips equity extraction and continues to crypto step.

**Excel output:**

| Sheet | Description | Typical Size |
|-------|-------------|-------------|
| `Equity_Summary` | Info snapshots with market cap, P/E, beta, etc. | 1 row per ticker |
| `Price_Stats` | Per-ticker aggregates: latest close, min/max, avg volume | 1 row per ticker |

**Key methods:**

| Method | Description |
|--------|-------------|
| `_init_provider(provider_name)` | Initializes the specified data provider |
| `_fetch_and_process(ticker)` | Fetches all market data for a ticker via provider |
| `save_to_database()` | Writes all collected data to SQLite |
| `save_to_excel()` | Generates summary and stats sheets |

---

### 5. Crypto Market Data (`Crypto.py`)

Fetches cryptocurrency OHLCV prices and coin information from Binance (US) or Coinbase. Mirrors the equity pipeline architecture.

**Class: `CryptoPipeline`**

**Constructor workflow:**
1. Initializes base directories (fixes initialization order bug)
2. Loads symbol list from CLI args or `config/crypto_watchlist.json`
3. Initializes crypto exchange provider (Binance US or Coinbase)
4. Queries DB for latest price timestamps to enable incremental updates
5. For each symbol: fetches historical OHLCV data and coin info
6. Saves to SQLite (`crypto_prices`, `crypto_info` tables)
7. Generates Excel with price data, coin info, and summary sheets

**Data fetched:**

| Dataset | Description | Typical Size (per symbol) |
|---------|-------------|---------------------------|
| **Prices** | OHLCV candlestick data (Open, High, Low, Close, Volume, Quote Volume, Trades) | ~365 rows (1 year, 1d interval) |
| **Info** | Coin metadata (name, base asset, quote asset, exchange) | 1 row |

**Supported intervals:** 1m, 5m, 15m, 1h, 4h, 1d, 1w (provider-dependent)

**Caching:** Symbols with data from the last hour (age ≤ 1 hour) are skipped unless `--force` is passed. Crypto moves fast, so 1-hour freshness is appropriate.

**Usage:**
```bash
python sources/crypto/pipeline.py                              # Default watchlist
python sources/crypto/pipeline.py --symbols BTCUSDT ETHUSDT    # Specific symbols
python sources/crypto/pipeline.py --provider binance           # Specify provider
python sources/crypto/pipeline.py --provider coinbase          # Use Coinbase
python sources/crypto/pipeline.py --interval 1h                # Custom interval
python sources/crypto/pipeline.py --days 365                   # Lookback period
python sources/crypto/pipeline.py --force                      # Bypass cache
```

**Default watchlist (`config/crypto_watchlist.json`):**
- BTCUSDT (Bitcoin)
- ETHUSDT (Ethereum)
- BNBUSDT (Binance Coin)
- SOLUSDT, ADAUSDT, DOGEUSDT, DOTUSDT, MATICUSDT, AVAXUSDT, LINKUSDT

**Providers:**

| Provider | Description | Rate Limits |
|----------|-------------|-------------|
| `binance` | Binance US exchange | 1200 requests/minute |
| `coinbase` | Coinbase exchange | 10 requests/second |

**Excel output:**

| Sheet | Description |
|-------|-------------|
| `Prices` | Full OHLCV candlestick data |
| `Coin Info` | Coin metadata |
| `Summary` | Pipeline run summary |

**Key methods:**

| Method | Description |
|--------|-------------|
| `_load_watchlist()` | Loads default symbols from config file |
| `_init_provider(provider_name)` | Initializes the specified exchange provider |
| `_fetch_and_process(symbol)` | Fetches all market data for a symbol |
| `save_to_database()` | Writes all collected data to SQLite |
| `save_to_excel()` | Generates price, info, and summary sheets |

---

### 6. News Aggregation (`News.py`)

Aggregates macro-focused news articles from multiple providers and stores them with topic tags and sentiment scores. Follows the same multi-provider pattern as Crypto.

**Class: `NewsPipeline`**

**Constructor workflow:**
1. Loads search queries from CLI args or `config/news_watchlist.json`
2. Initializes available providers (skips those without API keys)
3. Checks cache freshness per provider (6-hour window)
4. For each provider × query: fetches articles, deduplicates by URL
5. Saves to SQLite (`news_articles`, `news_article_topics` tables)

**Providers:**

| Provider | API Key Required | Rate Limit | Features |
|----------|-----------------|------------|----------|
| `gdelt` | No | Unlimited | Sentiment scores, free access |
| `newsapi` | Yes (`NEWSAPI_KEY`) | 100 req/day | 1 month lookback (free tier) |
| `finnhub` | Yes (`FINNHUB_KEY`) | 60 calls/min | Market-focused news |

**Caching:** Providers with data less than 6 hours old are skipped unless `--force` is passed.

**Usage:**
```bash
python sources/news/pipeline.py                                    # Default watchlist, all providers
python sources/news/pipeline.py --queries "inflation" "GDP growth" # Specific queries
python sources/news/pipeline.py --provider gdelt --days 3          # GDELT only (no key needed)
python sources/news/pipeline.py --provider all --days 7 --force    # All providers, force refresh
```

**Default watchlist (`config/news_watchlist.json`):**
- "federal reserve interest rates", "inflation CPI", "GDP economic growth"
- "unemployment jobs report", "treasury yields bonds", "stock market S&P 500"
- "oil prices energy", "trade deficit tariffs", "housing market real estate"
- "earnings season corporate profits"

**Notes:**
- NewsAPI free tier has a **1 month lookback** — the provider automatically clamps `from_date` and logs a warning
- GDELT uses `YYYYMMDDHHMMSS` date format — handled transparently by the provider
- Articles are deduplicated by URL (`INSERT OR IGNORE` on `UNIQUE(url)`)

#### Sentiment Enrichment (`enrich_sentiment.py`)

A post-ingest step that scores all unenriched articles with VADER sentiment analysis. Runs automatically as Step 5.5 in the pipeline, after news ingest.

- **Input**: `title + " " + description` concatenated
- **Output**: `sentiment` (compound score, -1 to +1), `sentiment_label` ("positive"/"negative"/"neutral"), `sentiment_source` ("vader")
- **Thresholds**: compound >= 0.05 = positive, <= -0.05 = negative, else neutral
- **GDELT articles**: Already scored at ingest (tone normalized to -1..+1, `sentiment_source = "gdelt_tone"`); skipped by enrichment unless `--force`

```bash
python sources/news/enrich_sentiment.py                  # Enrich all unenriched articles
python sources/news/enrich_sentiment.py --limit 1000     # Batch limit
python sources/news/enrich_sentiment.py --force           # Re-score all (including GDELT)
```

---

### 7. FRED Macro Economic Data (`Fred.py`)

Fetches economic indicator time series from the Federal Reserve Economic Data (FRED) API. Single provider (no ABC needed — FRED is the sole source).

**Class: `FredPipeline`**

**Constructor workflow:**
1. Loads series IDs from CLI args or `config/fred_series.json`
2. Initializes FRED provider with API key
3. Queries DB for latest observation dates (incremental updates)
4. For each series: fetches metadata + observations
5. Saves to SQLite (`fred_series_meta`, `fred_observations` tables)

**Data fetched:**

| Dataset | Description | Typical Size |
|---------|-------------|-------------|
| **Series Metadata** | Title, units, frequency, seasonal adjustment, notes | 1 row per series |
| **Observations** | Date + value time series | ~40-2,600 rows per series (depending on frequency) |

**Default series (`config/fred_series.json`):**

| Category | Series |
|----------|--------|
| Output | GDP, GDPC1 (Real GDP) |
| Inflation | CPIAUCSL, CPILFESL (Core CPI), PCEPI |
| Labor | UNRATE, PAYEMS (Nonfarm Payrolls), ICSA (Jobless Claims) |
| Rates | FEDFUNDS, DGS10, DGS2, T10Y2Y (Yield Curve) |
| Other | DEXUSEU (USD/EUR), VIXCLS (VIX), HOUST (Housing Starts), UMCSENT (Consumer Sentiment), M2SL (Money Supply) |

**Caching:** Series with observations from the current day are skipped unless `--force` is passed. Cache freshness is 24 hours.

**Usage:**
```bash
python sources/fred/pipeline.py                              # Default series from config
python sources/fred/pipeline.py --series GDP UNRATE          # Specific series
python sources/fred/pipeline.py --days 3650                  # 10 years of history
python sources/fred/pipeline.py --force                      # Ignore cache
```

**Notes:**
- Requires `FRED_API_KEY` environment variable. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html
- FRED uses `"."` for missing values — the provider converts these to `None`
- Incremental: only fetches observations newer than `MAX(date)` per series

---

### 8. Field Analysis Pipeline (`tasks/`)

A 4-phase analysis system that catalogs, categorizes, and prioritizes all XBRL fields across the company universe. Run once to populate the `reports/` directory.

**Phase 1 — Field Catalog** (`task1_field_catalog.py`):
- Fetches XBRL data for 20 diverse tickers across 8 sectors
- Discovers 4,148 unique fields across `us-gaap`, `dei`, `ifrs-full`, and `srt` taxonomies
- Records which companies report each field

**Phase 2 — Field Categorization** (`task2_field_categorization.py`, `task2_fiscal_years.py`):
- Classifies each field by statement type (Balance Sheet, Income Statement, Cash Flow, etc.)
- Determines temporal nature (Point-in-Time vs Period)
- Tags accounting concepts (Asset, Liability, Revenue, Expense, etc.)
- Flags critical fields for fundamental analysis (727 fields)
- Identifies special handling requirements (per-share, ratio, fair value, etc.)
- Determines fiscal year end months for each company

**Phase 3 — Field Availability** (`task3_field_availability.py`, `task3_pit_mapping.py`):
- Calculates cross-company availability percentages
- Assigns availability tiers (universal, very_common, common, moderate, rare, very_rare)
- Identifies sector-specific fields
- Builds point-in-time event timeline (filing dates vs period end dates)

**Phase 4 — Standardization** (`task4_field_standardization.py`, `task4_ttm_calculator.py`):
- Identifies deprecated fields
- Finds synonymous field groups
- Creates priority rankings
- Calculates TTM (Trailing Twelve Month) metrics for Revenue and NetIncome

**Orchestrator:** `field_analysis_pipeline.py` runs all 4 phases sequentially.

---

### 9. Data Models (`models.py`)

Pydantic models that enforce type safety and provide a single source of truth for all entity schemas. Every entity from `ENTITY_RELATIONSHIP.md` has a corresponding model.

**Enums:**

| Enum | Values |
|------|--------|
| `Sector` | Technology, Finance, Retail, Healthcare, Energy, Mining/Materials, Industrial, Telecom, Utilities, Real Estate, Transportation, Unknown |
| `MarketCapTier` | mega, large, mid, small, micro |
| `TemporalType` | Point-in-Time, Period |
| `AvailabilityTier` | universal, very_common, common, moderate, rare, very_rare |

**Models:**

| Model | Primary Key | Description |
|-------|-------------|-------------|
| `Company` | `ticker` | Company with sector/industry enrichment |
| `FiscalYearMetadata` | `ticker` | Fiscal calendar for a company |
| `FinancialFact` | composite | A single financial data point from a filing |
| `FieldCatalogEntry` | `field_name` | An XBRL field discovered across the universe |
| `FieldCategory` | `field_name` | Classification metadata for a field |
| `FieldPriority` | `field_name` | Ranked importance of a field |
| `PointInTimeEvent` | composite | A filing event in the timeline |
| `TTMMetric` | composite | Trailing twelve month annualized metric |
| `EquityPrice` | composite | Daily OHLCV price record |
| `EquityDividend` | composite | Dividend payment event |
| `EquitySplit` | composite | Stock split event |
| `EquityInfo` | composite | Market data and valuation ratios snapshot |
| `NewsArticle` | `url` | A news article from a provider |
| `FredSeriesMeta` | `series_id` | Metadata for a FRED economic series |
| `FredObservation` | composite | A single FRED data point |

---

### 10. Database Layer (`database.py`)

SQLite database manager providing relational storage for all pipeline entities. Uses Python's built-in `sqlite3` module — zero infrastructure required.

**Database file:** `data/financials.db`

**Features:**
- WAL journal mode for concurrent read access
- Foreign key enforcement
- Upsert semantics (INSERT OR REPLACE / INSERT OR IGNORE) for idempotent writes
- Indexes on high-cardinality query paths
- JSON storage for list columns (queryable via SQLite `json_extract()`)
- Standalone population mode from existing JSON reports

**Usage:**

```bash
# Standalone: populate all tables from JSON reports
python database.py

# Verify
sqlite3 data/financials.db ".tables"
sqlite3 data/financials.db "SELECT COUNT(*) FROM financial_facts;"
```

**Programmatic:**

```python
from database import DatabaseManager

db = DatabaseManager()

# Query companies by sector
tech = db.get_sector_companies("Technology")

# Raw SQL
results = db.query("""
    SELECT c.ticker, c.sector, t.ttm_value
    FROM ttm_metrics t
    JOIN companies c ON t.ticker = c.ticker
    WHERE t.metric_name = 'Revenue_TTM'
    ORDER BY t.ttm_value DESC
""")

db.close()
```

**Equity market data methods:**

| Method | Description |
|--------|-------------|
| `upsert_equity_prices(rows)` | Insert price records (skips duplicates) |
| `upsert_equity_dividends(rows)` | Insert dividend records |
| `upsert_equity_splits(rows)` | Insert split records |
| `upsert_equity_info(rows)` | Insert info snapshots |
| `get_ticker_latest_price(ticker)` | Returns most recent price date for cache checks |

**Crypto market data methods:**

| Method | Description |
|--------|-------------|
| `upsert_crypto_prices(rows)` | Insert crypto price records (skips duplicates) |
| `upsert_crypto_info(info)` | Insert or update crypto coin info |
| `get_crypto_latest_price(symbol, interval)` | Returns most recent timestamp for cache checks |

**News data methods:**

| Method | Description |
|--------|-------------|
| `upsert_news_articles(articles)` | Insert articles + topics (skips duplicate URLs) |
| `get_news_latest_fetch(provider)` | Returns most recent fetched_at for cache checks |
| `get_unenriched_articles(limit, force)` | Returns articles missing sentiment scores |
| `update_article_sentiment(id, sentiment, label, source)` | Updates sentiment fields for an article |

**FRED economic data methods:**

| Method | Description |
|--------|-------------|
| `upsert_fred_series_meta(meta)` | Insert or replace series metadata |
| `upsert_fred_observations(obs)` | Insert observations (skips duplicates) |
| `get_fred_latest_observation(series_id)` | Returns most recent date for incremental fetch |

---

### 11. Utilities (`utils/`)

**`utils/log.py` — Color-coded pipeline logging**

Provides consistent, color-coded console output across all pipeline scripts using `colorama`.

| Function | Color | Purpose |
|----------|-------|---------|
| `log.header(msg)` | Cyan/Bold | Section headers with `===` borders |
| `log.step(msg)` | Blue/Bold | Pipeline step announcements |
| `log.info(msg)` | Dim timestamp | Informational messages |
| `log.ok(msg)` | Green/Bold | Success messages |
| `log.warn(msg)` | Yellow/Bold | Warnings |
| `log.err(msg)` | Red/Bold | Errors |
| `log.progress(i, n, ticker, msg)` | Magenta ticker | Progress lines like `[3/40] AAPL: ...` |
| `log.summary_table(title, rows)` | Cyan header | Formatted key-value summary tables |

Also provides `setup_verbose_logging(name)` which creates a Python logger with dual handlers:
- **Console**: INFO+ level
- **File**: DEBUG+ level to `logs/pipeline.log`

**`utils/input_parser.py` — Ticker file parser**

Reads ticker lists from text files. Supports `#` comments, blank lines, and inline comments.

```python
from utils.input_parser import parse_input_file, DEFAULT_INPUT_FILE
tickers = parse_input_file()  # Reads from input.txt
```

**`utils/session.py` — `RequestSession`**

HTTP session wrapper with:
- Rotating user agents via `fake-useragent`
- Built-in rate limiting (2-5 second random delay between requests)
- Connection error handling
- JSON logging configuration

**`utils/excel_formatter.py` — `ExcelFormatter`**

Excel workbook builder with:
- DataFrame-to-sheet conversion with auto-formatting
- Auto-sized columns (sampled from first 500 rows for performance)
- Styled Excel tables (TableStyleMedium9)
- Multi-sheet workbook support

---

## Database Schema

```
+------------------+       +------------------------+
|    companies     |       | fiscal_year_metadata   |
+------------------+       +------------------------+
| ticker      [PK] |<----->| ticker          [PK,FK]|
| cik              |       | fiscal_year_end_month  |
| entity_name      |       | confidence             |
| sector           |       | sample_size            |
| industry         |       | dominant_month_pct     |
| sic_code         |       | filing_forms_found     |
| fye_month        |       | recent_filing_date     |
| market_cap_tier  |       +------------------------+
+------------------+
     |  1:N
     +--------->+------------------------+
     |          |   financial_facts      |
     |          +------------------------+
     |          | id            [PK,AUTO]|
     |          | ticker            [FK] |
     |          | sector                 |
     |          | industry               |
     |          | field                  |
     |          | statement_type         |
     |          | temporal_type          |
     |          | period_start           |
     |          | period_end             |
     |          | value                  |
     |          | unit                   |
     |          | filing_date            |
     |          | fiscal_year            |
     |          | fiscal_period          |
     |          | form                   |
     |          | UNIQUE(ticker, field,  |
     |          |   period_end,          |
     |          |   fiscal_period, unit, |
     |          |   account_number)      |
     |          +------------------------+
     |
     +--------->+------------------------+
     |          |    equity_prices       |
     |          +------------------------+
     |          | id            [PK,AUTO]|
     |          | ticker            [FK] |
     |          | date                   |
     |          | open, high, low, close |
     |          | volume                 |
     |          | UNIQUE(ticker, date)   |
     |          +------------------------+
     |
     +--------->+------------------------+
     |          |   equity_dividends     |
     |          +------------------------+
     |          | id            [PK,AUTO]|
     |          | ticker            [FK] |
     |          | date                   |
     |          | amount                 |
     |          | UNIQUE(ticker, date)   |
     |          +------------------------+
     |
     +--------->+------------------------+
     |          |    equity_splits       |
     |          +------------------------+
     |          | id            [PK,AUTO]|
     |          | ticker            [FK] |
     |          | date                   |
     |          | ratio                  |
     |          | UNIQUE(ticker, date)   |
     |          +------------------------+
     |
     +--------->+------------------------+
     |          |     equity_info        |
     |          +------------------------+
     |          | id            [PK,AUTO]|
     |          | ticker            [FK] |
     |          | fetched_date           |
     |          | market_cap             |
     |          | trailing_pe, forward_pe|
     |          | price_to_book          |
     |          | dividend_yield, beta   |
     |          | fifty_two_week_high/low|
     |          | average_volume         |
     |          | sector, industry       |
     |          | UNIQUE(ticker,         |
     |          |   fetched_date)        |
     |          +------------------------+
     |
     +--------->+------------------------+
     |          | point_in_time_events   |
     |          +------------------------+
     |          | id            [PK,AUTO]|
     |          | ticker            [FK] |
     |          | filing_date            |
     |          | period_end             |
     |          | form                   |
     |          | fy                     |
     |          | fp                     |
     |          | accession              |
     |          +------------------------+
     |
     +--------->+------------------------+
                |    ttm_metrics         |
                +------------------------+
                | id            [PK,AUTO]|
                | ticker            [FK] |
                | metric_name            |
                | as_of_date             |
                | period_end             |
                | ttm_value              |
                | source_filing          |
                | UNIQUE(ticker,         |
                |   metric_name,         |
                |   as_of_date)          |
                +------------------------+

+------------------+
|  crypto_prices   |
+------------------+
| symbol           |
| timestamp        |
| date             |
| interval         |
| open, high, low  |
| close, volume    |
| quote_volume     |
| trades           |
| PRIMARY KEY(     |
|   symbol,        |
|   timestamp,     |
|   interval)      |
+------------------+

+------------------+
|   crypto_info    |
+------------------+
| symbol      [PK] |
| name             |
| base_asset       |
| quote_asset      |
| exchange         |
| last_updated     |
+------------------+

+------------------------+       +------------------------+
|   news_articles        |       | news_article_topics    |
+------------------------+       +------------------------+
| id           [PK,AUTO] |<------| id           [PK,AUTO] |
| provider               |       | article_id        [FK] |
| source_name            |       | topic                  |
| title                  |       | UNIQUE(article_id,     |
| description            |       |   topic)               |
| url           [UNIQUE] |       +------------------------+
| published_at           |
| fetched_at             |
| category               |
| sentiment              |
| sentiment_label        |
| sentiment_source       |
| image_url              |
+------------------------+

+------------------------+       +------------------------+
|  fred_series_meta      |       |  fred_observations     |
+------------------------+       +------------------------+
| series_id    [PK]      |<------| id           [PK,AUTO] |
| title                  |       | series_id         [FK] |
| units                  |       | date                   |
| frequency              |       | value                  |
| seasonal_adj           |       | UNIQUE(series_id,date) |
| last_updated           |       +------------------------+
| notes                  |
+------------------------+
```

**Row counts (as of latest pipeline run — 42 companies + 3 crypto symbols):**

| Table | Rows | Notes |
|-------|------|-------|
| `companies` | 42 | From enrichment |
| `fiscal_year_metadata` | 21 | From fiscal year analysis (original 21 tickers) |
| `field_catalog` | 4,148 | All XBRL fields discovered |
| `field_categories` | 4,148 | Classifications for each field |
| `field_priorities` | 4,148 | Priority rankings |
| `financial_facts` | 1,017,741 | Populated by SEC.py (42 tickers) |
| `point_in_time_events` | 1,305 | Filing event timeline |
| `ttm_metrics` | 2,269 | Revenue & NetIncome TTM |
| `equity_prices` | 0 | Daily OHLCV (requires API key) |
| `equity_dividends` | 0 | Dividend events (requires API key) |
| `equity_splits` | 0 | Split events (requires API key) |
| `equity_info` | 0 | Valuation ratios snapshot (requires API key) |
| `crypto_prices` | 1,095 | OHLCV candlesticks (3 symbols × 365 days) |
| `crypto_info` | 3 | Coin metadata (BTC, ETH, BNB) |
| `news_articles` | 337 | News articles with VADER sentiment (GDELT) |
| `news_article_topics` | 337 | Article → topic associations |
| `fred_series_meta` | 0 | FRED series metadata (populated by FRED pipeline) |
| `fred_observations` | 0 | FRED data points (populated by FRED pipeline) |

**Indexes:**

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_ff_ticker_fy_fp` | `(ticker, fiscal_year, fiscal_period)` | Company + period lookups |
| `idx_ff_ticker_field_pe` | `(ticker, field, period_end)` | Specific metric time series |
| `idx_ff_sector` | `(sector)` | Sector-wide screening |
| `idx_ff_filing_date` | `(filing_date)` | Point-in-time queries |
| `idx_pit_ticker_fd` | `(ticker, filing_date)` | Filing timeline lookups |
| `idx_ttm_ticker_metric` | `(ticker, metric_name, as_of_date)` | TTM value retrieval |
| `idx_ep_ticker_date` | `(ticker, date)` | Price time series |
| `idx_ed_ticker` | `(ticker)` | Dividend history |
| `idx_es_ticker` | `(ticker)` | Split history |
| `idx_ei_ticker` | `(ticker, fetched_date)` | Info snapshots |
| `idx_cp_symbol_date` | `(symbol, date)` | Crypto price time series |
| `idx_na_published` | `(published_at)` | News article date filtering |
| `idx_na_provider` | `(provider)` | News provider filtering |
| `idx_na_category` | `(category)` | News category filtering |
| `idx_nat_topic` | `(topic)` | News topic lookups |
| `idx_fo_series_date` | `(series_id, date)` | FRED series time series |
| `idx_fo_date` | `(date)` | FRED cross-series date queries |

---

## Data Entities

For the full entity-relationship schema with attributes, relationships, cardinalities, and query patterns, see [`ENTITY_RELATIONSHIP.md`](ENTITY_RELATIONSHIP.md).

Key entities:

| Entity | Description | Source |
|--------|-------------|--------|
| **Company** | Ticker, CIK, sector, industry, SIC code, FYE month | `config/company_metadata.json` |
| **FinancialFact** | A single financial data point from an SEC filing | `SEC.py` output |
| **FieldCatalog** | 4,148 XBRL fields with taxonomy, label, description | `reports/field_catalog.json` |
| **FieldCategory** | Statement type, temporal nature, accounting concept per field | `reports/field_categories.json` |
| **FieldPriority** | Importance ranking and availability tier per field | `reports/field_priority.json` |
| **PointInTimeEvent** | Filing event timeline (prevents look-ahead bias) | `reports/point_in_time_map.json` |
| **TTMMetric** | Trailing twelve month Revenue and NetIncome | `reports/ttm_metrics.json` |
| **FiscalYearMetadata** | Fiscal calendar per company | `reports/fiscal_year_metadata.json` |
| **EquityPrice** | Daily OHLCV price record | Equity provider → SQLite |
| **EquityDividend** | Dividend payment event | Equity provider → SQLite |
| **EquitySplit** | Stock split event | Equity provider → SQLite |
| **EquityInfo** | Market cap, P/E, beta, valuation ratios | Equity provider → SQLite |
| **CryptoPrice** | Cryptocurrency OHLCV candlestick | Crypto exchange → SQLite |
| **CryptoInfo** | Coin metadata (name, base/quote asset) | Crypto exchange → SQLite |
| **NewsArticle** | News article with provider, sentiment (VADER/GDELT), topics | News providers → SQLite → VADER enrichment |
| **FredSeriesMeta** | FRED series metadata (title, units, frequency) | FRED API → SQLite |
| **FredObservation** | Single data point from a FRED series | FRED API → SQLite |

---

## Company Universe

42 companies across 10 sectors:

| Sector | Tickers | SIC Examples |
|--------|---------|--------------|
| **Technology** (6) | PLTR, MSFT, AAPL, NVDA, GOOG, CRM | 7372 (Software), 3571 (Computers), 3674 (Semiconductors), 7370 (Data Processing) |
| **Finance** (9) | JPM, BAC, WFC, GS, MS, AMT, PLD, SPG, O | 6021 (Banks), 6211 (Brokers), 6798 (REITs) |
| **Retail** (6) | WMT, AMZN, COST, HD, DIS, DKS | 5331 (Variety Stores), 5961 (Mail-Order), 5211 (Building Materials), 5940 (Sporting Goods) |
| **Healthcare** (4) | JNJ, UNH, PFE, ABT | 2834 (Pharmaceuticals), 6324 (Health Insurance) |
| **Energy** (3) | XOM, CVX, COP | 2911 (Petroleum Refining) |
| **Mining/Materials** (4) | GOLD, VALE, FCX, SLB | 1040 (Gold Ores), 1000 (Metal Mining), 1389 (Oil Field Services) |
| **Industrial** (2) | CAT, GE | 3531 (Construction Machinery), 3600 (Electrical Equipment) |
| **Telecom** (2) | VZ, T | 4813 (Telephone Communications) |
| **Utilities** (3) | NEE, DUK, SO | 4911 (Electric Services), 4931 (Combined Services) |
| **Transportation** (2) | HON, LMT | 3724 (Aircraft Engines), 3760 (Guided Missiles) |

**Cryptocurrency Universe:**

- **BTCUSDT** - Bitcoin
- **ETHUSDT** - Ethereum
- **BNBUSDT** - Binance Coin
- *(configurable via `config/crypto_watchlist.json`)*

---

## Configuration Files

### `config/cik.json`

Complete ticker-to-CIK mapping (~9,700 entries). Used to resolve any ticker to its SEC identifier.

```json
{"AAPL": "0000320193", "MSFT": "0000789019", "JPM": "0000019617", ...}
```

### `config/company_metadata.json`

Enriched company profiles for the pipeline tickers. Generated by `enrich.py`.

```json
{
  "AAPL": {
    "ticker": "AAPL",
    "cik": "0000320193",
    "entity_name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Electronic Computers",
    "sic_code": "3571",
    "fye_month": "September",
    "market_cap_tier": "large"
  }
}
```

### `config/sic_to_sector.json`

SIC code range-to-sector mapping. Contains ~70 ranges covering all major industries. When multiple ranges overlap for a given SIC code, the narrowest (most specific) range takes precedence.

### `config/crypto_watchlist.json`

Default cryptocurrency symbols to fetch. Includes symbol, name, and category (large_cap, mid_cap).

```json
{
  "symbols": [
    {"symbol": "BTCUSDT", "name": "Bitcoin", "category": "large_cap"},
    {"symbol": "ETHUSDT", "name": "Ethereum", "category": "large_cap"}
  ]
}
```

### `config/news_watchlist.json`

Macro-focused news search queries with category tags. Used by the news pipeline when no `--queries` argument is given.

```json
{
  "queries": [
    {"query": "federal reserve interest rates", "category": "monetary_policy"},
    {"query": "inflation CPI", "category": "inflation"},
    {"query": "GDP economic growth", "category": "output"}
  ]
}
```

### `config/fred_series.json`

FRED economic data series to track. Used by the FRED pipeline when no `--series` argument is given.

```json
{
  "series": [
    {"id": "GDP", "category": "output", "description": "Gross Domestic Product"},
    {"id": "UNRATE", "category": "labor", "description": "Unemployment Rate"},
    {"id": "FEDFUNDS", "category": "rates", "description": "Federal Funds Effective Rate"}
  ]
}
```

### `config/loggingConfig.json`

Standard Python `logging.config.dictConfig` format used by `utils/session.py`.

---

## Report Files

All generated by the field analysis pipeline (`tasks/`). These are reference data — generated once, updated infrequently.

| File | Size | Description |
|------|------|-------------|
| `field_catalog.json` | ~1.9 MB | 4,148 fields with taxonomy, label, description, company usage |
| `field_categories.json` | ~2.3 MB | Statement type, temporal nature, accounting concept per field |
| `field_priority.json` | ~694 KB | Priority scores and availability tiers |
| `field_availability_report.json` | ~2.9 MB | Cross-company coverage statistics and sector distribution |
| `field_mapping.json` | varies | Deprecated fields, synonym groups, consolidation rules |
| `fiscal_year_metadata.json` | small | FYE month, confidence, sample size per company |
| `point_in_time_map.json` | varies | Filing event timeline per ticker |
| `ttm_metrics.json` | varies | Revenue_TTM and NetIncome_TTM per ticker per filing date |

### Field availability tiers

| Tier | Coverage | Count | Use Case |
|------|----------|-------|----------|
| `universal` | 80%+ of companies | 46 | Safe for cross-sector screening |
| `very_common` | 60-80% | 101 | Safe for broad comparisons |
| `common` | 40-60% | 109 | Sector-level analysis |
| `moderate` | 20-40% | 247 | Industry-specific analysis |
| `rare` | 10-20% | 930 | Company-specific deep dives |
| `very_rare` | <10% | 2,715 | Footnotes, one-off disclosures |

---

## Usage Examples

### SQL Query Examples

**Latest price for each ticker:**
```sql
SELECT ticker, date, close, volume
FROM equity_prices
WHERE (ticker, date) IN (
    SELECT ticker, MAX(date)
    FROM equity_prices
    GROUP BY ticker
)
ORDER BY ticker;
```

**Latest crypto prices:**
```sql
SELECT symbol, date, close, volume
FROM crypto_prices
WHERE interval = '1d'
  AND (symbol, timestamp) IN (
    SELECT symbol, MAX(timestamp)
    FROM crypto_prices
    WHERE interval = '1d'
    GROUP BY symbol
)
ORDER BY symbol;
```

**Ticker with price > 100 and P/E < 20:**
```sql
SELECT ep.ticker, ep.close, ei.trailing_pe, ei.market_cap, c.sector
FROM equity_prices ep
JOIN equity_info ei ON ep.ticker = ei.ticker
JOIN companies c ON ep.ticker = c.ticker
WHERE ep.date = (SELECT MAX(date) FROM equity_prices WHERE ticker = ep.ticker)
  AND ep.close > 100
  AND ei.trailing_pe < 20
  AND ei.fetched_date = (SELECT MAX(fetched_date) FROM equity_info WHERE ticker = ei.ticker)
ORDER BY ei.market_cap DESC;
```

**Bitcoin price above $50k:**
```sql
SELECT date, close, volume
FROM crypto_prices
WHERE symbol = 'BTCUSDT'
  AND interval = '1d'
  AND close > 50000
ORDER BY date DESC
LIMIT 10;
```

**Recent news articles by category:**
```sql
SELECT provider, title, published_at, category, sentiment, sentiment_label, sentiment_source
FROM news_articles
WHERE published_at >= date('now', '-7 days')
ORDER BY published_at DESC
LIMIT 20;
```

**Sentiment distribution by category:**
```sql
SELECT category,
       COUNT(*) AS total,
       SUM(CASE WHEN sentiment_label = 'positive' THEN 1 ELSE 0 END) AS positive,
       SUM(CASE WHEN sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative,
       SUM(CASE WHEN sentiment_label = 'neutral' THEN 1 ELSE 0 END) AS neutral,
       ROUND(AVG(sentiment), 3) AS avg_sentiment
FROM news_articles
GROUP BY category
ORDER BY total DESC;
```

**FRED: latest GDP and unemployment:**
```sql
SELECT m.series_id, m.title, o.date, o.value, m.units
FROM fred_observations o
JOIN fred_series_meta m ON o.series_id = m.series_id
WHERE o.series_id IN ('GDP', 'UNRATE')
  AND o.date = (
    SELECT MAX(o2.date) FROM fred_observations o2
    WHERE o2.series_id = o.series_id
  );
```

**FRED: yield curve history (10Y-2Y spread):**
```sql
SELECT date, value AS spread
FROM fred_observations
WHERE series_id = 'T10Y2Y'
  AND value IS NOT NULL
ORDER BY date DESC
LIMIT 30;
```

**Companies by sector:**
```sql
SELECT sector, GROUP_CONCAT(ticker) as tickers, COUNT(*) as n
FROM companies
GROUP BY sector
ORDER BY n DESC;
```

**Latest TTM revenue ranked within each sector:**
```sql
SELECT c.sector, c.ticker, t.ttm_value, t.as_of_date
FROM ttm_metrics t
JOIN companies c ON t.ticker = c.ticker
WHERE t.metric_name = 'Revenue_TTM'
  AND t.as_of_date = (
    SELECT MAX(t2.as_of_date)
    FROM ttm_metrics t2
    WHERE t2.ticker = t.ticker AND t2.metric_name = t.metric_name
  )
ORDER BY c.sector, t.ttm_value DESC;
```

### Python API Examples

```python
from database import DatabaseManager

# Open database
db = DatabaseManager()

# Get all technology companies
tech = db.get_sector_companies("Technology")
for c in tech:
    print(f"{c['ticker']}: {c['entity_name']} ({c['industry']})")

# Get latest price for a ticker
latest = db.get_ticker_latest_price("AAPL")
print(f"AAPL latest price date: {latest}")

# Get latest crypto price
latest_ts = db.get_crypto_latest_price("BTCUSDT", "1d")
print(f"BTC latest timestamp: {latest_ts}")

# Custom query with parameters
results = db.query(
    "SELECT * FROM ttm_metrics WHERE ticker = ? AND metric_name = ?",
    ("AAPL", "Revenue_TTM")
)

# Use the SEC extractor
from sources.sec_edgar.pipeline import SEC
sec = SEC(tickers=["AAPL", "MSFT"])

# Use the Equity extractor
from sources.equity.pipeline import Equity
equity = Equity(tickers=["AAPL", "MSFT"], force=False, provider_name="alpha_vantage")

# Use the Crypto extractor
from sources.crypto.pipeline import CryptoPipeline
crypto = CryptoPipeline(symbols=["BTCUSDT", "ETHUSDT"], provider_name="binance")

# Use the News extractor (GDELT needs no API key)
from sources.news.pipeline import NewsPipeline
news = NewsPipeline(queries=["inflation CPI"], provider_name="gdelt", days=3)

# Use the FRED extractor
from sources.fred.pipeline import FredPipeline
fred = FredPipeline(series_ids=["GDP", "UNRATE"], days=365)

# Query news and FRED data
latest_news = db.query("SELECT title, published_at FROM news_articles ORDER BY published_at DESC LIMIT 5")
gdp = db.query("SELECT date, value FROM fred_observations WHERE series_id = 'GDP' ORDER BY date DESC LIMIT 4")

db.close()
```

---

## Design Invariants

These rules are critical for any downstream system consuming this data:

1. **Never use `period_end` as the availability date.** Always use `filing_date` / `data_available_date` / `as_of_date` to determine when information was publicly known.

2. **Filing lag is 20-60 days.** Between `period_end` and `filing_date`, the data does NOT exist from the market's perspective.

3. **Fiscal years are NOT calendar years.** AAPL FY2024 ends in September. NVDA FY2025 ends in January. Always join through `fiscal_year_metadata` to get actual dates.

4. **Point-in-Time fields have no `period_start`.** Do not aggregate them over time. Use the latest snapshot value.

5. **Period fields require aggregation.** To get annual figures, sum quarterly values or use `ttm_metrics` directly.

6. **Only universal/very_common fields are safe for cross-company screens.** Using rare fields will produce sparse, unreliable comparisons.

7. **Amended filings (`is_amended = true`) supersede original filings** for the same period. Use the most recent `filing_date` for a given `(ticker, field, period_end, fiscal_period)`.

8. **IFRS and US-GAAP fields are NOT directly comparable.** GOLD and VALE use IFRS. Check `field_mapping` for cross-taxonomy equivalences before comparing.

9. **The `frame` field can be null.** Do not rely on it as a primary key component.

10. **TTMMetric currently covers Revenue and NetIncome only.** For other metrics, compute TTM manually from `financial_facts` using the point-in-time event timeline.

11. **Crypto timestamps are in milliseconds.** Convert to seconds for datetime operations: `datetime.fromtimestamp(ts / 1000)`.

12. **Crypto intervals are exchange-specific.** Binance supports 1m, 5m, 15m, 1h, 4h, 1d, 1w. Coinbase may have different intervals.

13. **NewsAPI free tier has a 1-month lookback.** Requests for older articles are automatically clamped. GDELT has no lookback limit.

14. **FRED missing values are `None`, not `0`.** FRED uses `"."` for missing observations — the provider converts these to `None`. Do not treat null FRED values as zero.

15. **FRED series have different frequencies.** GDP is quarterly, UNRATE is monthly, DGS10 is daily. Always check `fred_series_meta.frequency` before aggregating or comparing series.

16. **News articles are deduplicated by URL.** The same story from different providers will only appear once. The first provider to insert it wins.

17. **All sentiment scores are on a -1 to +1 scale.** GDELT tone (~-100 to +100) is normalized by dividing by 100 and clamping. VADER compound scores are natively -1 to +1. Check `sentiment_source` to distinguish between `"gdelt_tone"` and `"vader"` scoring methods.

---

## Dependencies

### Python Packages

| Package | Purpose |
|---------|---------|
| `pydantic` | Data validation and model definitions |
| `requests` | HTTP requests to SEC EDGAR API |
| `pandas` | DataFrame operations and data manipulation |
| `openpyxl` | Excel file creation and formatting |
| `beautifulsoup4` | HTML parsing |
| `fake-useragent` | User agent rotation for SEC rate limits |
| `colorama` | Cross-platform terminal color output |
| `yfinance` | Equity market data (optional, not currently used) |
| `python-dotenv` | Load API keys from `.env` file |
| `vaderSentiment` | NLP sentiment analysis for news articles |

### Standard Library

`sqlite3`, `json`, `csv`, `os`, `sys`, `re`, `datetime`, `pathlib`, `collections`, `argparse`, `logging`, `time`, `random`

### Install

```bash
pip install pydantic requests pandas openpyxl beautifulsoup4 fake-useragent colorama yfinance python-dotenv vaderSentiment
```

---

## Known Issues

- **Equity data requires API key**: Alpha Vantage API key must be set via `ALPHA_VANTAGE_API_KEY` environment variable. Pipeline gracefully skips equity extraction if not set.
- **Crypto initialization order bug**: Fixed in latest version (moved `base_dir` initialization before watchlist loading).
- **IFRS cross-mapping not implemented**: `field_mapping.json` has placeholder structure for `gaap_ifrs_map` but no actual mappings. GOLD and VALE fields cannot be compared to US-GAAP companies.
- **SIC mapping may miss edge cases**: Some SIC codes fall outside the defined ranges in `sic_to_sector.json` and will default to "Unknown".
- **Fiscal year metadata only covers original 21 tickers**: The 19 newly added tickers need fiscal year analysis re-run.
- **Rate limiting on crypto exchanges**: Binance and Coinbase have rate limits. Use cache (`--force` flag) to avoid hitting limits.
- **NewsAPI free tier limitations**: 100 requests/day, 1 month lookback. Provider auto-clamps dates. GDELT is unlimited and needs no key.
- **Finnhub client-side filtering**: Finnhub general news endpoint doesn't support free-text search, so the provider fetches general news and filters client-side by query terms. Results may be less precise than NewsAPI.
- **FRED API key required**: FRED pipeline requires `FRED_API_KEY` environment variable. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html

---

## Future Roadmap

### Near Term
- [x] ~~Add `requirements.txt` or `pyproject.toml` for dependency management~~
- [x] ~~Incremental data loading — only fetch new filings not already in the DB~~
- [x] ~~Integrate equity market data pipeline~~
- [x] ~~Integrate cryptocurrency market data pipeline~~
- [x] ~~News aggregation pipeline (NewsAPI, Finnhub, GDELT)~~
- [x] ~~FRED macro economic indicator pipeline~~
- [ ] Database backup/sync to cloud storage
- [ ] Re-run field analysis pipeline with full company universe to update reports and fiscal year metadata
- [ ] Add more equity data providers (Polygon.io, Tiingo, IEX Cloud)
- [ ] Add more crypto exchanges (Kraken, Gemini, KuCoin)
- [ ] Add more news providers (Reuters, Bloomberg RSS, Reddit sentiment)
- [x] ~~NLP sentiment analysis on news articles (beyond GDELT tone scores)~~

### Medium Term — Analytics & Signals
- [ ] **Macro layer** — Sector-level aggregate tables (total revenue, median margins, sector growth rates)
- [ ] **Signal layer** — Pre-computed derived metrics (YoY growth, net margin, ROA, debt/equity, sector rank)
- [ ] **Valuation metrics** — Combine fundamentals + prices for P/E, P/B, EV/EBITDA, PEG ratio calculations
- [ ] **Technical indicators** — RSI, MACD, moving averages, Bollinger Bands on price data
- [ ] **Price-to-fundamentals joins** — Link filing dates to price movements for event studies
- [ ] **Crypto technical analysis** — On-chain metrics, volatility indicators, correlation analysis
- [ ] Calendar quarter normalization for cross-company temporal alignment
- [ ] IFRS-to-GAAP field mapping for GOLD and VALE

### Medium Term — Visualization Dashboard
- [ ] **Streamlit dashboard** for interactive data exploration
- [ ] **Sector overview page** — Heatmaps of sector performance, revenue/income comparisons
- [ ] **Company deep-dive page** — Time series charts for key financial metrics, filing timeline, TTM trends
- [ ] **Crypto dashboard** — Real-time price charts, volume analysis, exchange comparisons
- [ ] **Field explorer** — Browse the 4,148 XBRL fields with filtering
- [ ] **Query builder** — SQL query interface against the SQLite database

### Long Term
- [ ] Automated field categorization using ML
- [ ] Support for additional SEC forms (8-K, DEF 14A, S-1)
- [ ] Real-time filing monitoring via SEC EDGAR RSS
- [ ] Real-time crypto price streaming (WebSocket connections)
- [ ] REST API layer for programmatic access
- [ ] Alerting system — notify on new filings, significant metric changes, or price movements
- [ ] Cross-asset correlation analysis (equities vs crypto, fundamentals vs prices)

---

## Related Documentation

- [`ENTITY_RELATIONSHIP.md`](ENTITY_RELATIONSHIP.md) — Full entity-relationship schema with attributes, relationships, cardinalities, query patterns, and invariants for autonomous trading systems
- [`tasks_md/`](tasks_md/) — Detailed summaries from each analysis phase

---

## Test Run Results (DKS - Dick's Sporting Goods)

```
=== Database Summary ===
companies                  42 rows
financial_facts       1017741 rows
equity_prices               0 rows
crypto_prices            1095 rows
crypto_info                 3 rows
news_articles             337 rows
news_article_topics       337 rows
fred_series_meta            0 rows
fred_observations           0 rows

=== Sample Crypto Data ===
BTCUSDT    2026-02-15 19:00:00 $ 68,700.00
ETHUSDT    2026-02-15 19:00:00 $  1,995.00
BNBUSDT    2026-02-15 19:00:00 $    625.38

=== News Sentiment Distribution ===
neutral     204 articles  (avg  0.000)
negative     90 articles  (avg -0.374)
positive     43 articles  (avg  0.407)

=== DKS Company Data ===
Ticker: DKS
Name: DICK'S SPORTING GOODS, INC.
Sector: Retail
Industry: Retail-Miscellaneous Shopping Goods Stores
SIC: 5940
```

**Pipeline Status:**
- ✅ Step 1: Company enrichment — Success
- ✅ Step 2: SEC EDGAR fundamentals — Success (19,377 records)
- ⚠️ Step 3: Equity data — Skipped (requires API key)
- ✅ Step 4: Crypto data — Success (1,095 records, 3 symbols)
- ✅ Step 5: News aggregation — Success (337 articles via GDELT)
- ✅ Step 5.5: Sentiment enrichment — Success (337 articles scored with VADER)
- ⏳ Step 6: FRED macro data — Awaiting first run (requires FRED_API_KEY)
