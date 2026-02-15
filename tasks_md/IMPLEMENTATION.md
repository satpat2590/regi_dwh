Equity Trading System Roadmap
From EDGAR Fundamentals to Automated Trading

## Phase 1: Field Discovery & Understanding

### Task #1: Field Discovery & Understanding Pipeline
Consolidated analysis pipeline to catalog, categorize, and standardize XBRL fields.

**Actions**:
- **Field Cataloging**: Fetch XBRL fields from 20+ diverse companies across major sectors (Tech, Finance, Retail, etc.) using `field_analysis_pipeline.py`.
- **Categorization**: Classify fields by statement type (Balance Sheet, Income Statement, etc.), temporal nature (Point-in-Time vs Period), and accounting concepts.
- **Availability Analysis**: Determine which fields are universal (90%+ coverage) vs sector-specific. Identifies critical fields for fundamental analysis.
- **Standardization**: Create mapping rules for synonymous fields and handle deprecations.

**Output Artifacts**: 
- `field_catalog.json`: Master list of all unique fields
- `field_categories.json`: Metadata and classification for each field
- `field_availability_report.json`: Coverage statistics and sector analysis
- `field_mapping.json`: Standardization and consolidation rules
- `field_priority.json`: Ranked list of fields for preferred usage

### Task #2: Catalog Fiscal Year Ends
Extract and store fiscal year end metadata for each company.

**Logic & Implementation Strategy**:
- **Data Source**: SEC Company Facts (XBRL)
- **Method**: Deducing FYE from 10-K filing dates (since explicit `CurrentFiscalYearEndDate` is inconsistent in facts)
- **Algorithm**:
  1. Iterate through a universal field (e.g., `us-gaap:Assets` or `us-gaap:Revenues`)
  2. Filter facts where `form` equals "10-K"
  3. Extract the `end` date (period end) from these filings
  4. Group by month to handle 52/53 week floating dates (e.g., late Sep vs early Oct)
  5. Identify the dominant month as the Fiscal Year End
  6. Detect any historical changes in FYE (if a company shifted from Dec to Jun, for example)
- **Edge Cases**:
  - 52/53 week years (dates shift slightly each year)
  - Short fiscal years due to transitions
  - Missing 10-K data points

**Actions**:
- Create `task2_fiscal_years.py`
- Extract fiscal year end month for all target companies
- Store results in `fiscal_year_metadata.json` mapping Ticker -> FYE Month

**Output**: fiscal_year_metadata.json

### Task #3: Implement Point-in-Time Calendar Mapping (Option B)
Build a "known as of" framework to prevent look-ahead bias.

**Actions**:
- Track when data became publicly available (filing date)
- Create point-in-time data structure: on any calendar date, know exactly what information was public
- Store filing dates alongside period dates
- Ensure proper temporal alignment to prevent data leakage in backtests

**Foundation**: This serves as the base for the normalization system

### Task #4: Implement Trailing Metrics System (Option C)
Compute trailing twelve month (TTM) and trailing four quarter figures.

**Actions**:
- Calculate TTM metrics anchored to calendar dates
- Ensure every company gets TTM figures (e.g., revenue, earnings) as of specific calendar dates (e.g., March 31st)
- Handle companies with different fiscal quarter ends
- Make these metrics derived from the point-in-time foundation (Task #3)
- Enable clean cross-sectional comparison across companies

**Derived From**: Task #3 (Point-in-Time Mapping)
