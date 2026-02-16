# SEC EDGAR Financial Data Pipeline

A comprehensive system for extracting, normalizing, enriching, and storing public company financial data from the SEC EDGAR database. Designed for downstream use in sector/industry profiling, fundamental analysis, trading signal generation, and backtesting.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Pipeline Components](#pipeline-components)
  - [1. Pipeline Orchestrator (run_pipeline.sh)](#1-pipeline-orchestrator-run_pipelinesh)
  - [2. Enrichment Layer (enrich.py)](#2-enrichment-layer-enrichpy)
  - [3. Data Extraction (SEC.py)](#3-data-extraction-secpy)
  - [4. Field Analysis Pipeline (tasks/)](#4-field-analysis-pipeline-tasks)
  - [5. Data Models (models.py)](#5-data-models-modelspy)
  - [6. Database Layer (database.py)](#6-database-layer-databasepy)
  - [7. Utilities (utils/)](#7-utilities-utils)
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
- [Known Issues & Bugs](#known-issues--bugs)
- [Future Roadmap](#future-roadmap)

---

## Architecture Overview

```
                    SEC EDGAR API
                         |
          +--------------+--------------+
          |                             |
   /submissions/CIK*.json      /api/xbrl/companyfacts/CIK*.json
   (entity info, SIC code)     (financial facts, XBRL data)
          |                             |
          v                             v
     +-----------+              +-----------+
     | enrich.py |              |  SEC.py   |
     +-----------+              +-----------+
          |                        |     |
          v                        v     v
  config/company_metadata.json   Excel  SQLite
  (sector, industry, SIC)       sheets  database
          |                        |     |
          +--------+-------+-------+-----+
                   |       |
                   v       v
            data/financials.db    data/EDGAR_FINANCIALS_*.xlsx
                   |
                   v
          Downstream Consumers
    (sector profiling, trading signals,
     backtesting, valuation models)
```

### Data Flow

1. **`run_pipeline.sh`** orchestrates the full pipeline — reads `input.txt` for the ticker list, then runs enrichment followed by SEC extraction. Supports CLI passthrough for `--tickers` and `--input-file`.

2. **`enrich.py`** fetches company metadata (SIC codes, entity names) from the SEC submissions endpoint and maps SIC codes to sectors/industries. Outputs `config/company_metadata.json` and writes to SQLite.

3. **Field analysis pipeline** (`tasks/`) runs once to catalog, categorize, and prioritize all 4,148 XBRL fields across the company universe. Outputs go to `reports/`.

4. **`SEC.py`** fetches XBRL company facts, normalizes temporal data, enriches with sector/industry tags, and writes to both Excel and SQLite.

5. **`database.py`** provides the SQLite database layer. Can be populated standalone from existing JSON reports or written to incrementally by the pipeline scripts.

---

## Quick Start

### Prerequisites

```bash
pip install requests pandas openpyxl beautifulsoup4 fake-useragent pydantic colorama
```

### Option A: Run the full pipeline (recommended)

```bash
# Edit input.txt to choose your tickers, then:
./run_pipeline.sh
```

This runs enrichment + SEC extraction for all tickers in `input.txt` and writes to both Excel and SQLite.

### Option B: Run individual steps

```bash
# Step 1: Enrich company metadata
python enrich.py

# Step 2: Populate database from existing JSON reports
python database.py

# Step 3: Extract financial data
python SEC.py

# Step 4: Query the database
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
```

---

## Project Structure

```
company_financials/
|
|-- run_pipeline.sh                    # Bash orchestrator (enrich -> SEC)
|-- SEC.py                             # Main data extraction and normalization
|-- enrich.py                          # Company enrichment (SIC -> sector/industry)
|-- database.py                        # SQLite database manager
|-- models.py                          # Pydantic data models for all entities
|-- equity.py                          # Volume analysis utilities (yfinance)
|-- input.txt                          # Ticker list for pipeline runs
|
|-- config/
|   |-- cik.json                       # Ticker -> CIK mapping (~9,700 entries)
|   |-- company_metadata.json          # Enriched company profiles (40 companies)
|   |-- sic_to_sector.json             # SIC code range -> sector/industry mapping
|   |-- loggingConfig.json             # Logging configuration
|
|-- data/
|   |-- financials.db                  # SQLite database (all entities)
|   |-- EDGAR_FINANCIALS_*.xlsx        # Excel exports (per-run snapshots)
|
|-- reports/
|   |-- field_catalog.json             # 4,148 XBRL fields discovered
|   |-- field_catalog_metadata.json    # Catalog generation metadata
|   |-- field_categories.json          # Field classification (statement type, temporal)
|   |-- field_priority.json            # Field importance rankings
|   |-- field_availability_report.json # Cross-company field coverage
|   |-- field_mapping.json             # Deprecated/synonym field mappings
|   |-- fiscal_year_metadata.json      # Company fiscal calendar data
|   |-- point_in_time_map.json         # Filing event timeline
|   |-- ttm_metrics.json              # Trailing Twelve Month calculations
|   |-- output_company_financials.json # Aggregated company output
|
|-- tasks/
|   |-- field_analysis_pipeline.py     # Orchestrator for all 4 analysis phases
|   |-- task1_field_catalog.py         # Phase 1: Build field catalog
|   |-- task2_field_categorization.py  # Phase 2: Categorize fields
|   |-- task2_fiscal_years.py          # Phase 2b: Determine fiscal year ends
|   |-- task3_field_availability.py    # Phase 3: Analyze field coverage
|   |-- task3_pit_mapping.py           # Phase 3b: Point-in-time event mapping
|   |-- task4_field_standardization.py # Phase 4: Standardization rules
|   |-- task4_ttm_calculator.py        # Phase 4b: TTM metric calculation
|
|-- tasks_md/                          # Analysis documentation and summaries
|
|-- utils/
|   |-- __init__.py
|   |-- session.py                     # HTTP session with rate limiting
|   |-- excel_formatter.py             # Excel workbook formatting
|   |-- log.py                         # Color-coded pipeline logging (colorama)
|   |-- input_parser.py               # Ticker file parser (input.txt)
|
|-- logs/
|   |-- pipeline.log                   # Verbose DEBUG-level pipeline log
|   |-- app.log                        # Application log output
|
|-- ENTITY_RELATIONSHIP.md             # Full entity-relationship schema reference
|-- README.md                          # This file
```

---

## Pipeline Components

### 1. Pipeline Orchestrator (`run_pipeline.sh`)

Bash script that runs the full pipeline end-to-end: enrichment first, then SEC extraction. Both steps read from the same ticker source (defaulting to `input.txt`).

**Features:**
- Color-coded terminal output with timestamps
- Forwards all CLI arguments to both `enrich.py` and `SEC.py`
- Exits immediately on failure (`set -euo pipefail`)
- Displays ticker count from `input.txt` before starting

**Usage:**
```bash
./run_pipeline.sh                        # Process tickers from input.txt
./run_pipeline.sh --tickers AAPL MSFT    # Process specific tickers
./run_pipeline.sh --input-file my.txt    # Process from custom file
./run_pipeline.sh --all                  # Process all ~9,700 tickers in cik.json (very slow)
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
python enrich.py                          # Enrich tickers from input.txt
python enrich.py --tickers AAPL MSFT JPM  # Enrich specific tickers
python enrich.py --input-file my.txt      # Enrich from custom file
python enrich.py --all                    # Enrich every ticker in cik.json (slow)
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

### 3. Data Extraction (`SEC.py`)

The main extraction engine. Fetches XBRL company facts from SEC EDGAR, normalizes temporal data, enriches with sector/industry, and persists to Excel and SQLite.

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
| `Ticker_Summary` | One row per ticker with record counts | 40 rows |

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

**Usage:**
```bash
python SEC.py                              # Extract for tickers in input.txt
python SEC.py --tickers AAPL MSFT JPM      # Extract for specific tickers
python SEC.py --input-file my_tickers.txt  # Extract from custom file
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

### 4. Field Analysis Pipeline (`tasks/`)

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

### 5. Data Models (`models.py`)

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

---

### 6. Database Layer (`database.py`)

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

---

### 7. Utilities (`utils/`)

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
     |  1:N                  +-------------------+
     |                       |  field_catalog    |
     |                       +-------------------+
     |                       | field_name   [PK] |
     |                       | taxonomy          |
     |                       | label             |
     |                       | description       |
     |                       | count             |
     |                       | companies_using   |
     |                       +-------------------+
     |                            |  1:1
     |                       +-------------------+
     |                       | field_categories  |
     |                       +-------------------+
     |                       | field_name   [PK] |
     |                       | statement_type    |
     |                       | temporal_nature   |
     |                       | accounting_concept|
     |                       | is_critical       |
     |                       | special_handling  |
     |                       +-------------------+
     |                            |  1:1
     |                       +-------------------+
     |                       | field_priorities  |
     |                       +-------------------+
     |                       | field_name   [PK] |
     |                       | priority_score    |
     |                       | availability      |
     |                       | is_critical       |
     |                       | tier              |
     |                       +-------------------+
     |
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
```

**Row counts (as of latest pipeline run — 40 tickers):**

| Table | Rows | Notes |
|-------|------|-------|
| `companies` | 40 | From enrichment |
| `fiscal_year_metadata` | 21 | From fiscal year analysis (original 21 tickers) |
| `field_catalog` | 4,148 | All XBRL fields discovered |
| `field_categories` | 4,148 | Classifications for each field |
| `field_priorities` | 4,148 | Priority rankings |
| `financial_facts` | 1,113,467 | Populated by SEC.py (40 tickers) |
| `point_in_time_events` | 1,305 | Filing event timeline |
| `ttm_metrics` | 2,269 | Revenue & NetIncome TTM |

**Indexes:**

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_ff_ticker_fy_fp` | `(ticker, fiscal_year, fiscal_period)` | Company + period lookups |
| `idx_ff_ticker_field_pe` | `(ticker, field, period_end)` | Specific metric time series |
| `idx_ff_sector` | `(sector)` | Sector-wide screening |
| `idx_ff_filing_date` | `(filing_date)` | Point-in-time queries |
| `idx_pit_ticker_fd` | `(ticker, filing_date)` | Filing timeline lookups |
| `idx_ttm_ticker_metric` | `(ticker, metric_name, as_of_date)` | TTM value retrieval |

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

---

## Company Universe

40 companies across 10 sectors:

| Sector | Tickers | SIC Examples |
|--------|---------|--------------|
| **Technology** (6) | PLTR, MSFT, AAPL, NVDA, GOOG, CRM | 7372 (Software), 3571 (Computers), 3674 (Semiconductors), 7370 (Data Processing) |
| **Finance** (9) | JPM, BAC, WFC, GS, MS, AMT, PLD, SPG, O | 6021 (Banks), 6211 (Brokers), 6798 (REITs) |
| **Retail** (5) | WMT, AMZN, COST, HD, DIS | 5331 (Variety Stores), 5961 (Mail-Order), 5211 (Building Materials), 7990 (Amusement) |
| **Healthcare** (4) | JNJ, UNH, PFE, ABT | 2834 (Pharmaceuticals), 6324 (Health Insurance) |
| **Energy** (3) | XOM, CVX, COP | 2911 (Petroleum Refining) |
| **Mining/Materials** (4) | GOLD, VALE, FCX, SLB | 1040 (Gold Ores), 1000 (Metal Mining), 1389 (Oil Field Services) |
| **Industrial** (2) | CAT, GE | 3531 (Construction Machinery), 3600 (Electrical Equipment) |
| **Telecom** (2) | VZ, T | 4813 (Telephone Communications) |
| **Utilities** (3) | NEE, DUK, SO | 4911 (Electric Services), 4931 (Combined Services) |
| **Transportation** (2) | HON, LMT | 3724 (Aircraft Engines), 3760 (Guided Missiles) |

**Record distribution by sector:**

| Sector | Companies | Financial Facts |
|--------|-----------|-----------------|
| Finance | 9 | 279,937 |
| Technology | 6 | 122,183 |
| Retail | 5 | 97,133 |
| Healthcare | 4 | 95,795 |
| Utilities | 3 | 77,282 |
| Energy | 3 | 73,933 |
| Mining/Materials | 4 | 72,265 |
| Industrial | 2 | 69,712 |
| Telecom | 2 | 51,701 |
| Transportation | 2 | 45,068 |
| **Total** | **40** | **1,113,467** |

**Taxonomy notes:** GOLD and VALE use IFRS (502 unique fields). All others use US-GAAP (3,613 fields). Cross-taxonomy mapping is required for direct field-level comparison.

---

## Configuration Files

### `config/cik.json`

Complete ticker-to-CIK mapping (~9,700 entries). Used to resolve any ticker to its SEC identifier.

```json
{"AAPL": "0000320193", "MSFT": "0000789019", "JPM": "0000019617", ...}
```

### `config/company_metadata.json`

Enriched company profiles for the 40 pipeline tickers. Generated by `enrich.py`.

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

**Universal critical fields for cross-company screening:**
```sql
SELECT fp.field_name, fc.label, fp.tier, fp.priority_score, fc.temporal_nature
FROM field_priorities fp
JOIN field_categories fc ON fp.field_name = fc.field_name
WHERE fp.tier = 'universal' AND fp.is_critical = 1
ORDER BY fp.priority_score DESC;
```

**Point-in-time safe query — latest known financials for AAPL:**
```sql
SELECT ff.field, ff.field_label, ff.value, ff.unit, ff.fiscal_period, ff.filing_date
FROM financial_facts ff
WHERE ff.ticker = 'AAPL'
  AND ff.filing_date = (
    SELECT MAX(ff2.filing_date) FROM financial_facts ff2
    WHERE ff2.ticker = 'AAPL' AND ff2.fiscal_period = 'FY'
  )
  AND ff.fiscal_period = 'FY'
  AND ff.field_priority > 100
ORDER BY ff.statement_type, ff.field;
```

**Sector aggregate — total revenue by sector:**
```sql
SELECT c.sector,
       COUNT(DISTINCT c.ticker) as companies,
       SUM(t.ttm_value) as total_revenue_ttm,
       AVG(t.ttm_value) as avg_revenue_ttm
FROM ttm_metrics t
JOIN companies c ON t.ticker = c.ticker
WHERE t.metric_name = 'Revenue_TTM'
  AND t.as_of_date = (
    SELECT MAX(t2.as_of_date)
    FROM ttm_metrics t2
    WHERE t2.ticker = t.ticker AND t2.metric_name = t.metric_name
  )
GROUP BY c.sector
ORDER BY total_revenue_ttm DESC;
```

### Python API Examples

```python
from database import DatabaseManager
from models import Company

# Open database
db = DatabaseManager()

# Get all technology companies
tech = db.get_sector_companies("Technology")
for c in tech:
    print(f"{c['ticker']}: {c['entity_name']} ({c['industry']})")

# Custom query with parameters
results = db.query(
    "SELECT * FROM ttm_metrics WHERE ticker = ? AND metric_name = ?",
    ("AAPL", "Revenue_TTM")
)

# Use the SEC extractor
from SEC import SEC
sec = SEC(tickers=["AAPL", "MSFT"])  # Processes specified tickers and writes to DB

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
| `yfinance` | Market data (used in `equity.py`) |

### Standard Library

`sqlite3`, `json`, `csv`, `os`, `sys`, `re`, `datetime`, `pathlib`, `collections`, `argparse`, `logging`, `time`, `random`

### Install

```bash
pip install pydantic requests pandas openpyxl beautifulsoup4 fake-useragent colorama yfinance
```

---

## Known Issues & Bugs

- [x] ~~**`SEC.py` ticker list is hardcoded in `__init__`**~~ — Now accepts `--tickers` CLI arg, `--input-file`, or reads from `input.txt`
- [x] ~~**No CLI for `SEC.py` or `enrich.py`**~~ — Both scripts now support `--tickers`, `--input-file`, and `enrich.py` also supports `--all`
- [x] ~~**Excel blows up on large datasets**~~ — Fixed: full dataset (1M+ rows) goes to SQLite only; Excel gets per-statement sheets within row limits
- [ ] **`equity.py` is standalone** — Volume analysis script is not integrated into the main pipeline. Ticker is hardcoded to `AAPL`.
- [ ] **No incremental updates** — `SEC.py` re-fetches all data on every run. Should detect which periods are already in the DB and only fetch new filings.
- [ ] **`ExcelFormatter` table name collision** — The `displayName` property deduplication can fail if two sheets produce the same sanitized name.
- [ ] **`_infer_period_start` uses approximate days** — Uses 365/90 day offsets instead of proper calendar month arithmetic. Can be off by a few days.
- [ ] **IFRS cross-mapping not implemented** — `field_mapping.json` has placeholder structure for `gaap_ifrs_map` but no actual mappings. GOLD and VALE fields cannot be compared to US-GAAP companies.
- [ ] **No `requirements.txt`** — Dependencies are not formally tracked in a requirements file.
- [ ] **SIC mapping may miss edge cases** — Some SIC codes fall outside the defined ranges in `sic_to_sector.json` and will default to "Unknown".
- [ ] **HON and LMT classified as Transportation** — SIC 3724 (Aircraft Engines) and 3760 (Guided Missiles) map to Transportation via broad SIC ranges, but these are arguably better classified as Industrial/Aerospace & Defense. Needs more granular SIC ranges.
- [ ] **DIS classified as Retail** — SIC 7990 (Amusement & Recreation) maps to Retail. Could warrant a dedicated Media/Entertainment sector.
- [ ] **Fiscal year metadata only covers original 21 tickers** — The 19 newly added tickers (GOOG, CRM, GS, MS, HD, ABT, COP, SLB, HON, LMT, T, DIS, NEE, DUK, SO, AMT, PLD, SPG, O) need fiscal year analysis re-run.

---

## Future Roadmap

### Near Term
- [ ] Add `requirements.txt` or `pyproject.toml` for dependency management
- [ ] Incremental data loading — only fetch new filings not already in the DB
- [ ] Database backup/sync to Google Drive (rclone or API)
- [ ] Re-run field analysis pipeline with full 40-ticker universe to update reports and fiscal year metadata

### Medium Term — News & Sentiment Data Layer
- [ ] **News data ingestion** — Pull financial news from public APIs (e.g., NewsAPI, Finnhub, Alpha Vantage news, SEC RSS feeds) for macro and micro trend analysis
- [ ] **Macro trend analysis** — Aggregate news sentiment by sector/industry to identify sector-level momentum shifts, regulatory headwinds, and economic cycle signals
- [ ] **Micro trend analysis** — Company-specific news tracking for earnings surprises, M&A activity, analyst upgrades/downgrades, insider trading signals, and event-driven trading catalysts
- [ ] **Sentiment scoring** — NLP-based sentiment classification (positive/negative/neutral) with source credibility weighting
- [ ] **News-to-financials linking** — Correlate news events with filing dates and financial metric changes to identify leading indicators
- [ ] **News storage** — New `news_articles` and `sentiment_scores` tables in SQLite with full-text search support

### Medium Term — Visualization Dashboard
- [ ] **Streamlit dashboard** (or similar: Dash, Panel, Gradio) for interactive data exploration
- [ ] **Sector overview page** — Heatmaps of sector performance, revenue/income comparisons, field coverage matrices
- [ ] **Company deep-dive page** — Time series charts for key financial metrics, filing timeline, TTM trends, peer comparison
- [ ] **Field explorer** — Browse the 4,148 XBRL fields with filtering by statement type, availability tier, and priority score
- [ ] **News feed view** — Real-time news stream with sentiment indicators, filterable by sector/ticker
- [ ] **Query builder** — SQL query interface against the SQLite database with result visualization
- [ ] **Export controls** — Download filtered views as CSV, Excel, or JSON

### Medium Term — Analytics & Signals
- [ ] **Macro layer** — Sector-level aggregate tables (total revenue, median margins, sector growth rates)
- [ ] **Signal layer** — Pre-computed derived metrics (YoY growth, net margin, ROA, debt/equity, sector rank)
- [ ] Calendar quarter normalization for cross-company temporal alignment
- [ ] IFRS-to-GAAP field mapping for GOLD and VALE
- [ ] Market data integration (price, volume, market cap) from yfinance

### Long Term
- [ ] Automated field categorization using ML
- [ ] Support for additional SEC forms (8-K, DEF 14A, S-1)
- [ ] Real-time filing monitoring via SEC EDGAR full-text search RSS
- [ ] REST API layer for programmatic access
- [ ] Alerting system — notify on new filings, significant metric changes, or news sentiment shifts

---

## Related Documentation

- [`ENTITY_RELATIONSHIP.md`](ENTITY_RELATIONSHIP.md) — Full entity-relationship schema with attributes, relationships, cardinalities, query patterns, and invariants for autonomous trading systems
- [`tasks_md/`](tasks_md/) — Detailed summaries from each analysis phase
