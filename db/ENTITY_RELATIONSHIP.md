# Entity-Relationship Schema

This document describes the data entities, their attributes, and relationships within the SEC EDGAR financial data system. It is designed for LLM ingestion to support autonomous portfolio management, trading signal generation, and backtesting.

---

## Entities

### 1. Company

The central entity representing a publicly traded company.

```
Company
├── ticker         : str  [PK]    -- Stock ticker symbol (e.g., "AAPL", "PLTR")
├── cik            : str  [UNIQUE] -- SEC Central Index Key, zero-padded to 10 digits (e.g., "0000320193")
├── entity_name    : str           -- Legal entity name from SEC filings
├── sector         : str           -- Market sector (Technology, Finance, Retail, Healthcare, Energy, Mining/Materials, Industrial, Telecom)
└── fye_month      : str           -- Fiscal year end month (e.g., "December", "September")
```

**Source**: `config/cik.json` (ticker->CIK mapping), `reports/fiscal_year_metadata.json` (FYE data)

---

### 2. FiscalYearMetadata

Metadata about each company's fiscal calendar, critical for temporal alignment across companies with different fiscal year ends.

```
FiscalYearMetadata
├── ticker                 : str   [FK -> Company.ticker]
├── fiscal_year_end_month  : str   -- Dominant FYE month (e.g., "December", "June", "September")
├── confidence             : str   -- "High" | "Medium" | "Low"
├── sample_size            : int   -- Number of annual filings analyzed
├── dominant_month_pct     : float -- Percentage of filings ending in the dominant month
├── filing_forms_found     : list[str] -- Form types observed (e.g., ["10-K"], ["20-F"], ["40-F"])
└── recent_filing_date     : str   -- Most recent fiscal year end date (YYYY-MM-DD)
```

**Source**: `reports/fiscal_year_metadata.json`

**Key constraint**: Different companies end their fiscal years in different months. NVDA fiscal year "2025" ends January 2025. AAPL fiscal year "2024" ends September 2024. MSFT fiscal year "2024" ends June 2024. You MUST use this entity to correctly align cross-company comparisons.

---

### 3. FieldCatalog

Master catalog of all XBRL financial data fields discovered across the analyzed company universe.

```
FieldCatalog
├── field_name      : str       [PK] -- XBRL concept name (e.g., "AccountsPayableCurrent", "NetIncomeLoss")
├── taxonomy        : str            -- XBRL taxonomy source ("us-gaap" | "dei" | "ifrs-full" | "srt" | "invest")
├── label           : str            -- Human-readable name (e.g., "Accounts Payable, Current")
├── description     : str            -- Full accounting definition from XBRL
├── count           : int            -- Number of companies reporting this field (out of 21)
└── companies_using : list[str]      -- Tickers of companies that report this field
```

**Source**: `reports/field_catalog.json`

**Scale**: 4,148 unique fields. Only 118 (2.8%) are reported by 80%+ of companies. 45.3% are company-specific (reported by only 1 company).

---

### 4. FieldCategory

Classification metadata for each field, determining how it should be processed and which financial statement it belongs to.

```
FieldCategory
├── field_name        : str       [PK, FK -> FieldCatalog.field_name]
├── label             : str       -- Human-readable field name
├── taxonomy          : str       -- XBRL taxonomy
├── statement_type    : str       -- "Balance Sheet" | "Balance Sheet - Assets" | "Balance Sheet - Liabilities" | "Balance Sheet - Equity" | "Income Statement" | "Cash Flow Statement" | "Document & Entity Info" | "Other/Footnotes"
├── temporal_nature   : str       -- "Point-in-Time" | "Period"
├── accounting_concept: list[str] -- Semantic tags (e.g., ["Asset"], ["Revenue"], ["Tax", "Expense"])
├── is_critical       : bool      -- True if field is important for fundamental analysis (727 fields flagged)
├── special_handling  : list[str] -- Processing flags ("Standard" | "Ratio/Rate" | "Fair Value" | "Per-Share Metric" | "Accumulated/Cumulative" | "Deferred" | "Foreign Currency" | "Discontinued Operations")
└── companies_using   : list[str] -- Tickers reporting this field
```

**Source**: `reports/field_categories.json`

**Critical distinction**:
- `temporal_nature = "Point-in-Time"`: Balance sheet items. Represents a snapshot value at `period_end`. No `period_start`. (22% of fields)
- `temporal_nature = "Period"`: Income statement and cash flow items. Represents a cumulative value between `period_start` and `period_end`. Requires aggregation for TTM calculations. (78% of fields)

---

### 5. FieldPriority

Ranked importance of each field for trading and fundamental analysis.

```
FieldPriority
├── field_name     : str   [PK, FK -> FieldCatalog.field_name]
├── priority_score : float -- Composite score (higher = more important). Range: ~0.0 to 180.0
├── availability   : float -- Percentage of companies reporting this field (0.0 to 100.0)
├── is_critical    : bool  -- True if field is essential for fundamental analysis
└── tier           : str   -- "universal" | "common" | "moderate" | "rare" | "very_rare"
```

**Source**: `reports/field_priority.json`

**Top-priority fields** (priority_score = 180.0, availability = 100%):
- `LiabilitiesAndStockholdersEquity`
- `NetIncomeLoss`
- `WeightedAverageNumberOfSharesOutstandingBasic`

**Tier definitions**:
- `universal`: Reported by 80%+ of companies (46 fields)
- `very_common`: Reported by 60-80% (101 fields)
- `common`: Reported by 40-60% (109 fields)
- `moderate`: Reported by 20-40% (247 fields)
- `rare`: Reported by 10-20% (930 fields)
- `very_rare`: Reported by <10% (2,715 fields)

---

### 6. FieldMapping

Standardization rules for handling synonymous, deprecated, and variant XBRL field names.

```
FieldMapping
├── deprecated_fields[]
│   ├── field_name : str -- Deprecated XBRL concept name
│   └── label      : str -- Human-readable name including deprecation date
├── synonym_groups[] (planned)
│   ├── canonical_name : str       -- Preferred field name
│   └── variants       : list[str] -- Alternative field names that map to the canonical name
└── gaap_ifrs_map[] (planned)
    ├── us_gaap_field : str -- US-GAAP field name
    └── ifrs_field    : str -- Equivalent IFRS field name
```

**Source**: `reports/field_mapping.json`

**Note**: GOLD and VALE use IFRS taxonomy (502 unique fields). All other companies use US-GAAP (3,613 fields). Cross-taxonomy mapping is required for universal comparison.

---

### 7. FinancialFact

The core data record: a single financial data point extracted from an SEC filing. This is the primary entity for analysis and trading.

```
FinancialFact
├── ticker           : str            [FK -> Company.ticker]
├── cik              : str            [FK -> Company.cik]
├── entity_name      : str
├── field            : str            [FK -> FieldCatalog.field_name]
├── field_label      : str            -- Human-readable field name
├── statement_type   : str            -- From FieldCategory.statement_type
├── temporal_type    : str            -- "Point-in-Time" | "Period"
├── period_start     : date | null    -- Start of reporting period (null for Point-in-Time fields)
├── period_end       : date           -- End of reporting period (or snapshot date for Point-in-Time)
├── value            : numeric        -- The reported financial value
├── unit             : str            -- "USD" | "shares" | "USD/shares" | "pure" | etc.
├── filing_date      : date           -- When the filing was submitted to SEC
├── data_available_date : date        -- When data became publicly available (= filing_date; used for backtesting)
├── fiscal_year      : int            -- Fiscal year number (e.g., 2024)
├── fiscal_period    : str            -- "Q1" | "Q2" | "Q3" | "Q4" | "FY"
├── form             : str            -- SEC form type ("10-K" | "10-Q" | "10-K/A" | "10-Q/A" | "20-F" | "40-F")
├── is_amended       : bool           -- True if form contains "/A" (amended filing)
├── field_priority   : float          -- Priority score from FieldPriority entity
├── taxonomy         : str            -- XBRL taxonomy ("us-gaap" | "dei" | "ifrs-full" | "srt")
├── account_number   : str            -- SEC accession number (unique filing identifier)
└── frame            : str | null     -- Reporting frame identifier (e.g., "CY2023Q4I")
```

**Source**: `SEC.py` output -> `data/EDGAR_FINANCIALS_*.xlsx`, `reports/output_company_financials.json`

**Composite key**: `(ticker, field, period_end, fiscal_period, unit, account_number)`

---

### 8. PointInTimeEvent

A filing event in the historical timeline. Maps fiscal periods to their actual public disclosure dates. This entity prevents look-ahead bias in backtesting.

```
PointInTimeEvent
├── ticker      : str  [FK -> Company.ticker]
├── filing_date : date -- When the filing was submitted to SEC EDGAR (the "known as of" date)
├── period_end  : date -- The fiscal period end date reported in the filing
├── form        : str  -- "10-K" | "10-Q" | "10-K/A" | "20-F" | "40-F"
├── fy          : int  -- Fiscal year
├── fp          : str  -- "Q1" | "Q2" | "Q3" | "Q4" | "FY"
└── accession   : str  -- SEC accession number (unique filing identifier)
```

**Source**: `reports/point_in_time_map.json`

**Critical rule for trading systems**: On any calendar date D, a trading system may ONLY use FinancialFact records where `data_available_date <= D`. The lag between `period_end` and `filing_date` is typically 20-60 days. During this lag, the system must use the PREVIOUS period's data.

**Example**: PLTR FY2023 ended 2023-12-31 but was filed 2024-02-20. A strategy running on 2024-01-15 must use Q3 2023 data (filed 2023-11-02), NOT FY2023 data.

---

### 9. TTMMetric

Trailing Twelve Month annualized metrics, anchored to filing dates for point-in-time correctness. Ready for direct use in valuation ratios.

```
TTMMetric
├── ticker         : str   [FK -> Company.ticker]
├── metric_name    : str   -- "Revenue_TTM" | "NetIncome_TTM"
├── as_of_date     : date  -- The date this TTM value became available (= filing_date)
├── period_end     : date  -- The fiscal period end date of the source filing
├── ttm_value      : numeric -- Annualized trailing twelve month value
└── source_filing  : str   -- Form type used as source ("10-K" | "10-Q" | "20-F" | "40-F")
```

**Source**: `reports/ttm_metrics.json`

**Usage for valuation**: Combine with market price data to compute:
- `P/S ratio = Market Cap / Revenue_TTM`
- `P/E ratio = Market Cap / NetIncome_TTM`

**Temporal rule**: The `as_of_date` field (NOT `period_end`) determines when this metric is usable by a trading system.

---

### 10. FieldAvailabilityReport

Aggregate statistics on field coverage across the company universe.

```
FieldAvailabilityReport
├── summary
│   ├── total_companies_analyzed : int  -- 21
│   ├── total_unique_fields      : int  -- 4,148
│   ├── availability_tiers       : dict -- Counts per tier (universal: 46, very_common: 101, ...)
│   └── sector_specific_fields   : int  -- 78
└── field_analysis
    └── [field_name]
        ├── availability_count      : int       -- Number of companies reporting
        ├── availability_percentage : float     -- Percentage coverage
        ├── availability_tier       : str       -- Tier classification
        └── companies_using         : list[str] -- Which companies report this field
```

**Source**: `reports/field_availability_report.json`

---

## Relationships

```
Company (1) ──────────── (1) FiscalYearMetadata
   │
   │ (1) ─────────────── (*) FinancialFact
   │
   │ (1) ─────────────── (*) PointInTimeEvent
   │
   │ (1) ─────────────── (*) TTMMetric
   │
   └──── uses fields from ──── FieldCatalog

FieldCatalog (1) ─────── (1) FieldCategory
      │
      │ (1) ──────────── (1) FieldPriority
      │
      │ (1) ──────────── (*) FinancialFact
      │
      └──── referenced by ── FieldAvailabilityReport

FieldMapping ──────────── normalizes ──── FieldCatalog (deprecated -> current)

PointInTimeEvent ──────── constrains ──── FinancialFact (enforces temporal access rules)

TTMMetric ─────────────── derived from ── FinancialFact (aggregated annual values)
```

---

## Relationship Detail

| Parent Entity | Child Entity | Cardinality | Join Key | Description |
|---|---|---|---|---|
| Company | FiscalYearMetadata | 1:1 | `ticker` | Each company has one fiscal calendar |
| Company | FinancialFact | 1:N | `ticker` | Each company has thousands of financial facts |
| Company | PointInTimeEvent | 1:N | `ticker` | Each company has a timeline of filing events |
| Company | TTMMetric | 1:N | `ticker` | Each company has TTM values per filing date |
| FieldCatalog | FieldCategory | 1:1 | `field_name` | Each field has one classification |
| FieldCatalog | FieldPriority | 1:1 | `field_name` | Each field has one priority ranking |
| FieldCatalog | FinancialFact | 1:N | `field_name` = `field` | Each field appears in many facts |

---

## Query Patterns for Autonomous Trading

### 1. Get latest known financials for a company (point-in-time safe)

```
Given: ticker, current_date
1. Filter PointInTimeEvent WHERE ticker = T AND filing_date <= current_date
2. Take the most recent PointInTimeEvent by filing_date
3. Use that event's period_end and fy/fp to filter FinancialFact records
4. Return all FinancialFact WHERE ticker = T AND fiscal_year = fy AND fiscal_period = fp
```

### 2. Get TTM valuation ratios

```
Given: ticker, current_date, market_cap
1. Filter TTMMetric WHERE ticker = T AND as_of_date <= current_date
2. Take most recent Revenue_TTM and NetIncome_TTM by as_of_date
3. P/S = market_cap / Revenue_TTM
4. P/E = market_cap / NetIncome_TTM
```

### 3. Cross-company comparison (sector screen)

```
Given: sector, metric_field, current_date
1. Get all Company WHERE sector = S
2. For each company, get latest TTMMetric WHERE as_of_date <= current_date
3. Rank companies by ttm_value
4. Note: Different FYE months mean "latest" data may have different staleness
```

### 4. Find universally available fields for screening

```
1. Filter FieldPriority WHERE tier = "universal" AND is_critical = true
2. These fields can be used for cross-company comparisons with confidence
3. Fields with tier = "rare" or "very_rare" should not be used for broad screens
```

### 5. Determine which financial statement a field belongs to

```
Given: field_name
1. Lookup FieldCategory WHERE field_name = F
2. Read statement_type to know if it's Balance Sheet, Income Statement, or Cash Flow
3. Read temporal_nature to know if it's a snapshot (Point-in-Time) or cumulative (Period)
4. If temporal_nature = "Period", it needs TTM aggregation for annualized comparison
5. If temporal_nature = "Point-in-Time", use the latest available value directly
```

---

## File Manifest

| Entity | Source File | Format |
|---|---|---|
| Company | `config/cik.json` | JSON: `{ticker: cik}` |
| FiscalYearMetadata | `reports/fiscal_year_metadata.json` | JSON: `{ticker: {metadata}}` |
| FieldCatalog | `reports/field_catalog.json` | JSON: `{field_name: {metadata}}` |
| FieldCategory | `reports/field_categories.json` | JSON: `{field_name: {classification}}` |
| FieldPriority | `reports/field_priority.json` | JSON: `{field_name: {ranking}}` |
| FieldMapping | `reports/field_mapping.json` | JSON: `{deprecated_fields: [...]}` |
| FieldAvailabilityReport | `reports/field_availability_report.json` | JSON: `{summary, field_analysis}` |
| FinancialFact | `data/EDGAR_FINANCIALS_*.xlsx` | Excel: multi-sheet workbook |
| PointInTimeEvent | `reports/point_in_time_map.json` | JSON: `{ticker: [{events}]}` |
| TTMMetric | `reports/ttm_metrics.json` | JSON: `{ticker: {metric: [{values}]}}` |

---

## Invariants for Autonomous Systems

1. **Never use `period_end` as the availability date.** Always use `filing_date` / `data_available_date` / `as_of_date` to determine when information was publicly known.
2. **Filing lag is 20-60 days.** Between `period_end` and `filing_date`, the data does NOT exist from the market's perspective.
3. **Fiscal years are NOT calendar years.** AAPL FY2024 ends in September. NVDA FY2025 ends in January. Always join through `FiscalYearMetadata` to get the actual dates.
4. **Point-in-Time fields have no `period_start`.** Do not attempt to compute duration or aggregate them over time. Use the latest snapshot value.
5. **Period fields require aggregation.** To get annual figures, sum quarterly values or use TTMMetric directly.
6. **Only universal/very_common fields are safe for cross-company screens.** Using rare fields will produce sparse, unreliable comparisons.
7. **Amended filings (`is_amended = true`) supersede original filings** for the same period. Use the most recent `filing_date` for a given `(ticker, field, period_end, fiscal_period)`.
8. **IFRS and US-GAAP fields are NOT directly comparable.** GOLD and VALE use IFRS. Check `FieldMapping` for cross-taxonomy equivalences before comparing.
9. **The `frame` field can be null.** Do not rely on it as a primary key component.
10. **TTMMetric currently covers Revenue and NetIncome only.** For other metrics, compute TTM manually from FinancialFact records using the Point-in-Time event timeline.
