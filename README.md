# SEC Filing Scraper

This repository collects and processes public company financial data from the SEC EDGAR database using the SEC XBRL API.

## Project Overview

This project provides a comprehensive toolkit for extracting, normalizing, and analyzing financial data from SEC filings. The core module (`SEC.py`) integrates with field analysis pipelines to intelligently categorize financial metrics and handle temporal data correctly.

---

## Module: `SEC.py`

### Location
The `SEC.py` file is designed to be used as a reusable module. It is located in the root directory and can be imported into other scripts:

```python
from SEC import SEC
```

### Class: `SEC`

The main class for extracting and processing SEC financial data with advanced temporal normalization and field categorization.

#### Features

1. **Intelligent Field Categorization**
   - Automatically categorizes fields by statement type (Balance Sheet, Income Statement, Cash Flow Statement)
   - Distinguishes between point-in-time vs period metrics
   - Integrates with field analysis pipeline for enhanced categorization

2. **Temporal Normalization**
   - Correctly handles point-in-time data (balance sheet items)
   - Properly tracks period data (income statement, cash flow)
   - Infers period start dates when not explicitly provided
   - Tracks filing dates for backtesting accuracy

3. **Multi-Company Support**
   - Processes multiple tickers in a single run
   - Uses CIK (Central Index Key) mapping for company identification
   - Aggregates data across all processed companies

4. **Comprehensive Data Export**
   - Exports to Excel with multiple sheets organized by:
     - All data combined
     - Statement type (Balance Sheet, Income Statement, etc.)
     - Temporal type (Point-in-Time, Period)
   - Includes field priority scores for filtering

5. **Field Intelligence Integration**
   - Loads field categories from `reports/field_categories.json`
   - Loads field priorities from `reports/field_priority.json`
   - Falls back to basic categorization if analysis files unavailable

---

### Constructor: `__init__()`

Initializes the SEC data extractor and processes configured tickers.

**Configuration:**
- `url_template`: SEC submissions API endpoint
- `url_xbrl`: SEC XBRL company facts API endpoint
- `base_dir`: Project root directory
- `data_dir`: Output directory for Excel files
- `reports_dir`: Directory containing field analysis reports
- `tickers`: List of stock tickers to process (default: `['PLTR', 'AAPL', 'JPM']`)

**Dependencies:**
- `utils/session.py`: RequestSession class for HTTP requests
- `utils/excel_formatter.py`: ExcelFormatter class for Excel output
- `config/cik.json`: Ticker-to-CIK mapping

**Workflow:**
1. Loads CIK mapping from configuration
2. Loads field categories and priorities from reports
3. Processes each ticker sequentially
4. Saves aggregated data to Excel
5. Reports processing time

---

### Key Methods

#### `fetch_sec_filing(ticker: str) -> Optional[requests.Response]`
Fetches SEC filing data for a given ticker symbol.

**Parameters:**
- `ticker` (str): Stock ticker symbol (e.g., 'AAPL', 'PLTR')

**Returns:**
- `requests.Response` object if successful, `None` otherwise

**Example:**
```python
sec = SEC()
response = sec.fetch_sec_filing('AAPL')
```

---

#### `clean_facts(json_data: Dict, ticker: str) -> None`
Extracts and normalizes company facts with temporal and statement categorization.

**Parameters:**
- `json_data` (Dict): JSON data from SEC XBRL API
- `ticker` (str): Stock ticker symbol

**Processing:**
- Iterates through all taxonomies and fields
- Retrieves field metadata (statement type, temporal nature, priority)
- Normalizes temporal data based on field type
- Creates normalized records with comprehensive metadata

**Output Fields:**
- `Ticker`: Stock ticker symbol
- `CIK`: Central Index Key
- `EntityName`: Company legal name
- `Field`: XBRL field name (e.g., 'AccountsPayableCurrent')
- `FieldLabel`: Human-readable field label
- `StatementType`: Balance Sheet | Income Statement | Cash Flow Statement | Other
- `TemporalType`: Point-in-Time | Period
- `PeriodStart`: Start date for period metrics (null for point-in-time)
- `PeriodEnd`: End date (or snapshot date for point-in-time)
- `Value`: Numeric value
- `Unit`: Unit type (USD, shares, etc.)
- `FilingDate`: Date the filing was submitted to SEC
- `DataAvailableDate`: When data became publicly available (for backtesting)
- `FiscalYear`: Fiscal year
- `FiscalPeriod`: Fiscal period (Q1, Q2, Q3, Q4, FY)
- `Form`: SEC form type (10-K, 10-Q, etc.)
- `IsAmended`: Boolean indicating if filing is amended
- `FieldPriority`: Priority score from field analysis
- `Taxonomy`: XBRL taxonomy (us-gaap, dei, etc.)
- `AccountNumber`: SEC accession number
- `Frame`: Reporting frame identifier

---

#### `get_field_metadata(field_name: str) -> Tuple[str, str, float]`
Retrieves field metadata from the analysis system.

**Parameters:**
- `field_name` (str): XBRL field name

**Returns:**
- Tuple of `(statement_type, temporal_nature, priority_score)`

**Fallback Logic:**
- If field not in analysis files, uses basic categorization
- Basic categorization uses keyword matching on field names

---

#### `normalize_temporal_data(obj: Dict, temporal_nature: str) -> Tuple[Optional[str], Optional[str]]`
Normalizes temporal data based on field type.

**Parameters:**
- `obj` (Dict): Data object from SEC API
- `temporal_nature` (str): "Point-in-Time" or "Period"

**Returns:**
- Tuple of `(period_start, period_end)`

**Logic:**
- **Point-in-Time fields**: `period_start = None`, `period_end = end date`
- **Period fields**: `period_start = start date`, `period_end = end date`
- Infers period start if not provided using fiscal period

---

#### `save_aggregated_data()`
Saves aggregated data with statement-type and temporal-type separation.

**Output Sheets:**
- `ALL_DATA`: Complete dataset
- Individual sheets per statement type (Balance_Sheet, Income_Statement, etc.)
- Individual sheets per temporal type (Temporal_Point-in-Time, Temporal_Period)

---

### Usage Examples

#### Basic Usage (Standalone Script)
```python
# Run as standalone script
if __name__ == "__main__":
    sec = SEC()
    # Automatically processes configured tickers and saves to Excel
```

#### Import as Module
```python
from SEC import SEC

# Create instance and process default tickers
sec = SEC()

# Access processed data
print(f"Total records: {len(sec.all_ticker_data)}")

# Access individual ticker data
for record in sec.all_ticker_data:
    if record['Ticker'] == 'AAPL':
        print(f"{record['Field']}: {record['Value']}")
```

#### Custom Ticker Processing
```python
from SEC import SEC

# Modify tickers before initialization
sec = SEC()
sec.tickers = ['MSFT', 'GOOGL', 'AMZN']  # Note: Must update before __init__ runs

# Or modify the source code to set custom tickers
```

---

### Configuration Files

#### `config/cik.json`
Maps stock tickers to CIK numbers:
```json
{
    "AAPL": "0000320193",
    "PLTR": "0001321655",
    "JPM": "0000019617"
}
```

#### `reports/field_categories.json`
Contains field categorization from task analysis:
```json
{
    "AccountsPayableCurrent": {
        "statement_type": "Balance Sheet",
        "temporal_nature": "Point-in-Time"
    }
}
```

#### `reports/field_priority.json`
Contains field priority rankings:
```json
{
    "Revenue": {
        "priority_score": 0.95
    }
}
```

---

### Dependencies

#### Python Packages
- `requests`: HTTP requests to SEC API
- `pandas`: Data manipulation and DataFrame operations
- `beautifulsoup4`: HTML parsing (if needed)
- `fake-useragent`: User agent rotation

#### Custom Modules (in `utils/`)
- `utils.session.RequestSession`: Enhanced HTTP session with retry logic
- `utils.excel_formatter.ExcelFormatter`: Excel file creation and formatting

---

### Output

#### Excel File
- **Location**: `data/EDGAR_FINANCIALS_YYYYMMDD_HHMMSS.xlsx`
- **Format**: Multi-sheet workbook with formatted data
- **Sheets**: Organized by statement type and temporal type

---

### Module Organization Recommendation

To use `SEC.py` as a reusable module across multiple scripts, consider the following structure:

```
company_financials/
├── SEC.py                    # Main SEC class (keep in root or move to lib/)
├── lib/                      # Optional: Move SEC.py here for cleaner organization
│   ├── __init__.py
│   └── sec_extractor.py      # Renamed SEC.py
├── utils/                    # Utility modules (already exists)
│   ├── __init__.py
│   ├── session.py
│   └── excel_formatter.py
├── config/                   # Configuration files
│   └── cik.json
├── reports/                  # Field analysis outputs
│   ├── field_categories.json
│   └── field_priority.json
├── tasks/                    # Analysis scripts that import SEC
│   ├── task1_field_catalog.py
│   └── task2_field_categorization.py
└── data/                     # Output directory
```

#### Import Pattern
```python
# If SEC.py stays in root
from SEC import SEC

# If moved to lib/sec_extractor.py
from lib.sec_extractor import SEC

# Or with utils
from utils.session import RequestSession
from utils.excel_formatter import ExcelFormatter
```

---

### Best Practices

1. **CIK Mapping**: Always update `config/cik.json` before processing new tickers
2. **Field Analysis**: Run field categorization tasks first to populate `reports/` directory
3. **Data Validation**: Check `FilingDate` and `DataAvailableDate` for backtesting accuracy
4. **Temporal Handling**: Use `TemporalType` to filter point-in-time vs period metrics
5. **Priority Filtering**: Use `FieldPriority` to focus on most important fields

---

### Future Enhancements

- [ ] Support for custom ticker lists via command-line arguments
- [ ] Incremental updates (only fetch new filings)
- [ ] Database storage option (SQLite/PostgreSQL)
- [ ] API rate limiting and retry logic improvements
- [ ] Support for additional SEC forms (8-K, DEF 14A, etc.)
- [ ] Automated field categorization using ML

---

## Related Files

- **Field Analysis Tasks**: `tasks/task1_field_catalog.py`, `tasks/task2_field_categorization.py`
- **Utility Modules**: `utils/session.py`, `utils/excel_formatter.py`
- **Configuration**: `config/cik.json`
- **Output Reports**: `reports/field_categories.json`, `reports/field_priority.json`