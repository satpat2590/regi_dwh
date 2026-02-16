"""
SEC EDGAR Financial Data Extractor

Fetches XBRL company facts from SEC EDGAR, normalizes temporal data,
enriches with sector/industry tags, and persists to Excel and SQLite.

Usage:
    python SEC.py                              # Extract for tickers in input.txt
    python SEC.py --tickers AAPL MSFT JPM      # Extract for specific tickers
    python SEC.py --input-file my_tickers.txt  # Extract from custom file
"""

import argparse
import json, csv, os, sys, re
import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent, FakeUserAgent
import requests
import pandas as pd
from typing import Dict, Optional, Tuple
from pathlib import Path

# Add modules from base repo
sys.path.append(str(Path(__file__).parent))

from utils.session import RequestSession
from utils.excel_formatter import ExcelFormatter
from utils.input_parser import parse_input_file, DEFAULT_INPUT_FILE
from utils import log
from models import Company, FinancialFact
from database import DatabaseManager

logger = log.setup_verbose_logging("sec")


def save_json(spath: str, data: Dict) -> None:
    """Save the data in some JSON file specified by spath."""
    log.info(f"Saving JSON: {spath}")
    with open(spath, 'w+') as f:
        json.dump(data, f, indent=4)


class SEC():
    """
    Enhanced SEC data extractor with temporal normalization and field categorization.

    Features:
    - Integrates with field analysis pipeline for intelligent categorization
    - Distinguishes point-in-time vs period metrics
    - Tracks filing dates for point-in-time correctness
    - Supports multiple statement types (Balance Sheet, Income Statement, Cash Flow)
    """

    def __init__(self, tickers: list[str] = None):
        self.start = datetime.datetime.now()

        log.header("SEC EXTRACTION: Fetching XBRL Company Facts")

        # Configuration
        self.reqsesh = RequestSession()
        self.ef = ExcelFormatter()
        self.url_template = "https://data.sec.gov/submissions/CIK##########.json"
        self.url_xbrl_acc_payable = "https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/AccountsPayableCurrent.json"
        self.url_xbrl = "https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json"
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.base_dir, "data")
        self.reports_dir = os.path.join(self.base_dir, "reports")

        # Load CIK mapping
        log.step("Loading configuration...")
        jpath = os.path.join(self.base_dir, "config/cik.json")
        with open(jpath, 'r') as f:
            self.cik_map = json.load(f)
        logger.debug(f"Loaded {len(self.cik_map)} CIK mappings")

        # Load company enrichment metadata (sector, industry, SIC)
        self.company_metadata = self._load_company_metadata()

        # Load field intelligence from task analysis system
        self.field_categories = self._load_field_categories()
        self.field_priority = self._load_field_priority()

        log.summary_table("Loaded Resources", [
            ("Company profiles", str(len(self.company_metadata))),
            ("Field categories", str(len(self.field_categories))),
            ("Field priorities", str(len(self.field_priority))),
            ("CIK mappings", str(len(self.cik_map))),
        ])

        # Tickers to process
        self.tickers = tickers if tickers else ['PLTR', 'AAPL', 'JPM']
        log.step(f"Processing {len(self.tickers)} tickers: {', '.join(self.tickers)}")

        # Store all ticker data
        self.all_ticker_data = []

        for i, ticker in enumerate(self.tickers, 1):
            gaap_record = self.fetch_sec_filing(ticker, i, len(self.tickers))
            if gaap_record:
                gaap_record_cleaned = gaap_record.json()
                self.clean_facts(gaap_record_cleaned, ticker, i, len(self.tickers))

        # Save aggregated output
        log.step("Saving outputs...")
        self.save_aggregated_data()

        xlsx_name = f"EDGAR_FINANCIALS_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        self.ef.save(xlsx_name, self.data_dir)
        log.info(f"Excel: {os.path.join(self.data_dir, xlsx_name)}")

        # Write to SQLite database
        self.save_to_database()

        elapsed = datetime.datetime.now() - self.start
        log.summary_table("Extraction Summary", [
            ("Tickers processed", str(len(self.tickers))),
            ("Total records", str(len(self.all_ticker_data))),
            ("Elapsed", str(elapsed)),
        ])
        log.ok("SEC extraction complete")

    def _load_company_metadata(self) -> Dict:
        """Load enriched company metadata (sector, industry, SIC code)"""
        try:
            path = os.path.join(self.base_dir, "config/company_metadata.json")
            with open(path, 'r') as f:
                raw = json.load(f)
            validated = {}
            for ticker, data in raw.items():
                validated[ticker] = Company(**data)
            logger.debug(f"Loaded company metadata for {len(validated)} tickers")
            return validated
        except FileNotFoundError:
            log.warn("config/company_metadata.json not found. Run enrich.py first.")
            return {}

    def get_company_enrichment(self, ticker: str) -> Tuple[str, str]:
        """Return (sector, industry) for a ticker from enrichment data."""
        if ticker in self.company_metadata:
            c = self.company_metadata[ticker]
            return c.sector.value, c.industry
        return "", ""

    def _load_field_categories(self) -> Dict:
        """Load field categorization from task analysis system"""
        try:
            path = os.path.join(self.reports_dir, "field_categories.json")
            with open(path, 'r') as f:
                data = json.load(f)
            logger.debug(f"Loaded {len(data)} field categories")
            return data
        except FileNotFoundError:
            log.warn("field_categories.json not found. Using basic categorization.")
            return {}

    def _load_field_priority(self) -> Dict:
        """Load field priority rankings from task analysis system"""
        try:
            path = os.path.join(self.reports_dir, "field_priority.json")
            with open(path, 'r') as f:
                data = json.load(f)
            logger.debug(f"Loaded {len(data)} field priorities")
            return data
        except FileNotFoundError:
            log.warn("field_priority.json not found. Using default priorities.")
            return {}

    def get_field_metadata(self, field_name: str) -> Tuple[str, str, float]:
        """Get field metadata from the analysis system."""
        if field_name in self.field_categories:
            cat = self.field_categories[field_name]
            statement_type = cat.get("statement_type", "Other")
            temporal_nature = cat.get("temporal_nature", "Unknown")
        else:
            statement_type = self._basic_categorize_statement(field_name)
            temporal_nature = self._basic_categorize_temporal(field_name)

        priority_score = 0.0
        if field_name in self.field_priority:
            priority_score = self.field_priority[field_name].get("priority_score", 0.0)

        return statement_type, temporal_nature, priority_score

    def _basic_categorize_statement(self, field_name: str) -> str:
        """Basic statement categorization fallback"""
        field_lower = field_name.lower()

        if any(x in field_lower for x in ['cash flow', 'operating activities', 'investing activities', 'financing activities']):
            return "Cash Flow Statement"
        elif any(x in field_lower for x in ['revenue', 'income', 'expense', 'profit', 'loss', 'earnings']):
            return "Income Statement"
        elif any(x in field_lower for x in ['asset', 'liability', 'equity', 'stock', 'debt', 'payable', 'receivable']):
            return "Balance Sheet"
        elif 'entity' in field_lower or 'document' in field_lower:
            return "Document & Entity Information"
        else:
            return "Other"

    def _basic_categorize_temporal(self, field_name: str) -> str:
        """Basic temporal categorization fallback"""
        field_lower = field_name.lower()

        if any(x in field_lower for x in ['revenue', 'income', 'expense', 'flow', 'during']):
            return "Period"
        elif any(x in field_lower for x in ['asset', 'liability', 'equity', 'balance', 'outstanding']):
            return "Point-in-Time"
        else:
            return "Period"

    def normalize_temporal_data(self, obj: Dict, temporal_nature: str) -> Tuple[Optional[str], Optional[str]]:
        """Normalize temporal data based on field type."""
        end_date = obj.get("end")
        start_date = obj.get("start")

        if temporal_nature == "Point-in-Time":
            return None, end_date
        else:
            if not start_date and end_date:
                start_date = self._infer_period_start(end_date, obj.get("fp"))
            return start_date, end_date

    def _infer_period_start(self, end_date: str, fiscal_period: str) -> Optional[str]:
        """Infer period start date from end date and fiscal period"""
        if not end_date:
            return None

        try:
            end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')

            if fiscal_period == 'FY':
                start_dt = end_dt - datetime.timedelta(days=365)
            elif fiscal_period in ['Q1', 'Q2', 'Q3', 'Q4']:
                start_dt = end_dt - datetime.timedelta(days=90)
            else:
                return None

            return start_dt.strftime('%Y-%m-%d')
        except:
            return None

    def clean_facts(self, json_data: Dict, ticker: str, idx: int = 0, total: int = 0) -> None:
        """Extract and normalize company facts with temporal and statement categorization."""
        cik = json_data.get("cik")
        if not cik:
            log.err(f"No CIK for {ticker}")
            return

        entity = json_data.get("entityName")
        if not entity:
            log.err(f"No entityName for {ticker}")
            return

        facts = json_data.get("facts")
        if not facts:
            log.err(f"No facts for {entity}")
            return

        sector, industry = self.get_company_enrichment(ticker)
        logger.debug(f"{ticker}: enrichment -> {sector} / {industry}")

        # Count taxonomies and fields for verbose logging
        taxonomy_counts = {}
        cfacts = []
        for taxonomy, fields in facts.items():
            taxonomy_counts[taxonomy] = len(fields)
            for field_name, field_data in fields.items():
                statement_type, temporal_nature, priority_score = self.get_field_metadata(field_name)

                field_label = field_data.get("label", "")
                field_description = field_data.get("description", "")

                units = field_data.get("units", {})
                for unit_type, unit_list in units.items():
                    for obj in unit_list:
                        period_start, period_end = self.normalize_temporal_data(obj, temporal_nature)

                        filing_date = obj.get("filed")
                        form = obj.get("form", "")
                        is_amended = "/A" in form if form else False

                        row = {
                            'Ticker': ticker,
                            'CIK': cik,
                            'EntityName': entity,
                            'Sector': sector,
                            'Industry': industry,
                            'Field': field_name,
                            'FieldLabel': field_label,
                            'StatementType': statement_type,
                            'TemporalType': temporal_nature,
                            'PeriodStart': period_start,
                            'PeriodEnd': period_end,
                            'Value': obj.get("val"),
                            'Unit': unit_type,
                            'FilingDate': filing_date,
                            'DataAvailableDate': filing_date,
                            'FiscalYear': obj.get("fy"),
                            'FiscalPeriod': obj.get("fp"),
                            'Form': form,
                            'IsAmended': is_amended,
                            'FieldPriority': priority_score,
                            'Taxonomy': taxonomy,
                            'AccountNumber': obj.get("accn"),
                            'Frame': obj.get("frame")
                        }
                        cfacts.append(row)

        self.all_ticker_data.extend(cfacts)

        # Verbose per-taxonomy breakdown
        tax_detail = ", ".join(f"{k}: {v} fields" for k, v in taxonomy_counts.items())
        log.progress(
            idx, total, ticker,
            f"{log.C.OK}{len(cfacts):,} records{log.C.RESET} | "
            f"{log.C.SECTOR}{sector}{log.C.RESET} | {tax_detail}"
        )
        logger.info(f"{ticker} ({entity}): {len(cfacts)} records, taxonomies: {tax_detail}")

    def save_aggregated_data(self):
        """Save aggregated data with statement-type separation.

        The full ALL_DATA set goes only to SQLite (via save_to_database).
        Excel gets per-statement and per-ticker sheets which are more
        practical sizes and won't OOM openpyxl.
        """
        EXCEL_MAX_ROWS = 1_048_576 - 1  # minus header row

        if not self.all_ticker_data:
            log.warn("No data to save")
            return

        df = pd.DataFrame(self.all_ticker_data)

        # Skip ALL_DATA sheet for Excel — full dataset goes to SQLite only
        log.info(f"Total records: {len(df):,} (full dataset -> SQLite only)")

        # Per-statement-type sheets
        for stmt_type in df['StatementType'].unique():
            if stmt_type == "Other":
                continue

            stmt_df = df[df['StatementType'] == stmt_type].copy()
            sheet_name = stmt_type.replace(" ", "_").replace("/", "_").replace("\\", "_")
            sheet_name = re.sub(r'[:\*\?\[\]]', '', sheet_name)[:31]
            if len(stmt_df) > EXCEL_MAX_ROWS:
                log.warn(f"{sheet_name}: {len(stmt_df):,} rows exceeds Excel limit, skipping")
                continue
            self.ef.add_to_sheet(stmt_df, sheet_name=sheet_name)
            log.info(f"Sheet: {sheet_name} ({len(stmt_df):,} records)")

        # Per-ticker summary sheet (one row per ticker with record counts)
        summary = df.groupby(['Ticker', 'Sector', 'Industry', 'EntityName']).agg(
            Records=('Value', 'size'),
            Fields=('Field', 'nunique'),
            MinYear=('FiscalYear', 'min'),
            MaxYear=('FiscalYear', 'max'),
        ).reset_index()
        self.ef.add_to_sheet(summary, sheet_name="Ticker_Summary")
        log.info(f"Sheet: Ticker_Summary ({len(summary):,} tickers)")

    def save_to_database(self):
        """Write all collected financial facts to the SQLite database."""
        if not self.all_ticker_data:
            log.warn("No data to write to database")
            return

        db = DatabaseManager()
        n = db.upsert_financial_facts(self.all_ticker_data)
        db.close()
        log.ok(f"Database: {n:,} records written to {db.db_path}")

    def fetch_sec_filing(self, ticker: str, idx: int = 0, total: int = 0) -> Optional[requests.Response]:
        """Fetch SEC filing data for a ticker."""
        if ticker not in self.cik_map:
            log.progress(idx, total, ticker, f"{log.C.ERR}NOT in CIK map, skipping")
            logger.warning(f"{ticker} not found in CIK map")
            return None

        cik = self.cik_map[ticker]
        return self.extract_data(cik, ticker)

    def extract_data(self, cik: str, ticker: str = "") -> Optional[requests.Response]:
        """Extract data from SEC XBRL API."""
        cik_padded = cik.zfill(10)
        url = self.url_xbrl.replace('##########', cik_padded)

        logger.debug(f"Fetching XBRL: {url}")
        res = self.reqsesh.get(url)

        if res is None or res.status_code != 200:
            status = res.status_code if res else "No response"
            log.err(f"{ticker}: XBRL fetch failed (HTTP {status})")
            return None

        return res


def main():
    parser = argparse.ArgumentParser(description="Extract SEC EDGAR financial data")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to process")
    parser.add_argument("--input-file", type=str, help="Path to file with ticker list (default: input.txt)")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.input_file:
        tickers = parse_input_file(args.input_file)
    elif os.path.exists(DEFAULT_INPUT_FILE):
        tickers = parse_input_file()
        log.info(f"Reading tickers from {DEFAULT_INPUT_FILE}")
    else:
        tickers = None  # Will use default in SEC.__init__

    sec = SEC(tickers=tickers)


if __name__ == "__main__":
    main()
