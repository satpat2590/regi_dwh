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


def save_json(spath: str, data: Dict) -> None:
    """
    Save the data in some JSON file specified by spath

    :param spath: The path to the json file in which the data will be stored
    :param data: The json data to store into a file
    """
    print(f"\n[OMNI] - {datetime.datetime.now()} - Saving data in {spath}...\n")
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

    def __init__(self):
        self.start = datetime.datetime.now()

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
        jpath = os.path.join(self.base_dir, "config/cik.json")
        with open(jpath, 'r') as f:
            self.cik_map = json.load(f)

        # Load field intelligence from task analysis system
        self.field_categories = self._load_field_categories()
        self.field_priority = self._load_field_priority()
        
        print(f"Loaded {len(self.field_categories)} field categories")
        print(f"Loaded {len(self.field_priority)} field priorities")

        # Tickers to process
        self.tickers = ['PLTR', 'AAPL', 'JPM']
        print(f"\nProcessing the following tickers: {self.tickers}\n")
        
        # Store all ticker data
        self.all_ticker_data = []
        
        for ticker in self.tickers:
            gaap_record = self.fetch_sec_filing(ticker)
            if gaap_record:
                gaap_record_cleaned = gaap_record.json() 
                self.clean_facts(gaap_record_cleaned, ticker)
            print("\n")

        # Save aggregated output
        self.save_aggregated_data()
        self.ef.save(
            f"EDGAR_FINANCIALS_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", 
            self.data_dir
        )
        
        print(f"\n✓ Processing complete in {datetime.datetime.now() - self.start}")

    def _load_field_categories(self) -> Dict:
        """Load field categorization from task analysis system"""
        try:
            path = os.path.join(self.reports_dir, "field_categories.json")
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("Warning: field_categories.json not found. Using basic categorization.")
            return {}

    def _load_field_priority(self) -> Dict:
        """Load field priority rankings from task analysis system"""
        try:
            path = os.path.join(self.reports_dir, "field_priority.json")
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("Warning: field_priority.json not found. Using default priorities.")
            return {}

    def get_field_metadata(self, field_name: str) -> Tuple[str, str, float]:
        """
        Get field metadata from the analysis system.
        
        Returns:
            (statement_type, temporal_nature, priority_score)
        """
        if field_name in self.field_categories:
            cat = self.field_categories[field_name]
            statement_type = cat.get("statement_type", "Other")
            temporal_nature = cat.get("temporal_nature", "Unknown")
        else:
            # Fallback to basic categorization
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
        
        # Period indicators
        if any(x in field_lower for x in ['revenue', 'income', 'expense', 'flow', 'during']):
            return "Period"
        # Point-in-time indicators
        elif any(x in field_lower for x in ['asset', 'liability', 'equity', 'balance', 'outstanding']):
            return "Point-in-Time"
        else:
            return "Period"  # Default to period

    def normalize_temporal_data(self, obj: Dict, temporal_nature: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Normalize temporal data based on field type.
        
        For Point-in-Time fields: period_start = None, period_end = end date
        For Period fields: period_start = start date (if available), period_end = end date
        
        Returns:
            (period_start, period_end)
        """
        end_date = obj.get("end")
        start_date = obj.get("start")  # Not always available in SEC data
        
        if temporal_nature == "Point-in-Time":
            # Balance sheet items - snapshot at a point in time
            return None, end_date
        else:
            # Period metrics - income statement, cash flow
            # If start date not available, infer from fiscal period
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
                # Annual period - go back 12 months
                start_dt = end_dt - datetime.timedelta(days=365)
            elif fiscal_period in ['Q1', 'Q2', 'Q3', 'Q4']:
                # Quarterly period - go back 3 months
                start_dt = end_dt - datetime.timedelta(days=90)
            else:
                # Unknown period
                return None
            
            return start_dt.strftime('%Y-%m-%d')
        except:
            return None

    def clean_facts(self, json_data: Dict, ticker: str) -> None:
        """
        Extract and normalize company facts with temporal and statement categorization.
        
        :param json_data: JSON data from SEC XBRL API
        :param ticker: Stock ticker symbol
        """
        cik = json_data.get("cik")
        if not cik:
            print(f"No CIK for {ticker}")
            return

        entity = json_data.get("entityName")
        if not entity:
            print(f"No entityName for {ticker}")
            return 

        facts = json_data.get("facts")
        if not facts:
            print(f"No facts for {entity}")
            return 

        print(f"Processing {ticker} ({entity})...")
        
        cfacts = []
        for taxonomy, fields in facts.items():
            for field_name, field_data in fields.items():
                # Get field metadata from analysis system
                statement_type, temporal_nature, priority_score = self.get_field_metadata(field_name)
                
                # Get field label and description
                field_label = field_data.get("label", "")
                field_description = field_data.get("description", "")
                
                # Process units
                units = field_data.get("units", {})
                for unit_type, unit_list in units.items():
                    for obj in unit_list:
                        # Normalize temporal data
                        period_start, period_end = self.normalize_temporal_data(obj, temporal_nature)
                        
                        # Extract filing information
                        filing_date = obj.get("filed")
                        form = obj.get("form", "")
                        is_amended = "/A" in form if form else False
                        
                        # Create normalized record
                        row = {
                            'Ticker': ticker,
                            'CIK': cik,
                            'EntityName': entity,
                            'Field': field_name,
                            'FieldLabel': field_label,
                            'StatementType': statement_type,
                            'TemporalType': temporal_nature,
                            'PeriodStart': period_start,
                            'PeriodEnd': period_end,
                            'Value': obj.get("val"),
                            'Unit': unit_type,
                            'FilingDate': filing_date,
                            'DataAvailableDate': filing_date,  # For backtesting - when data became known
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
        
        # Store and display
        self.all_ticker_data.extend(cfacts)
        print(f"  ✓ Processed {len(cfacts)} records")

    def save_aggregated_data(self):
        """Save aggregated data with statement-type separation"""
        if not self.all_ticker_data:
            print("No data to save")
            return
        
        df = pd.DataFrame(self.all_ticker_data)
        
        # Save complete dataset
        self.ef.add_to_sheet(df, sheet_name="ALL_DATA")
        
        # Save by statement type
        for stmt_type in df['StatementType'].unique():
            if stmt_type == "Other":
                continue
            
            stmt_df = df[df['StatementType'] == stmt_type].copy()
            # Sanitize sheet name - remove invalid Excel characters
            sheet_name = stmt_type.replace(" ", "_").replace("/", "_").replace("\\", "_")
            sheet_name = re.sub(r'[:\*\?\[\]]', '', sheet_name)[:31]  # Excel limit
            self.ef.add_to_sheet(stmt_df, sheet_name=sheet_name)
            print(f"  Added sheet: {sheet_name} ({len(stmt_df)} records)")
        
        # Save by temporal type
        for temp_type in df['TemporalType'].unique():
            temp_df = df[df['TemporalType'] == temp_type].copy()
            sheet_name = f"Temporal_{temp_type}"[:31]
            self.ef.add_to_sheet(temp_df, sheet_name=sheet_name)

    def fetch_sec_filing(self, ticker: str) -> Optional[requests.Response]:
        """
        Fetch SEC filing data for a ticker.
        
        :param ticker: Stock ticker symbol
        :return: Response object or None
        """
        if ticker not in self.cik_map:
            print(f"Ticker {ticker} not found in CIK map")
            return None
        
        cik = self.cik_map[ticker]
        return self.extract_data(cik)

    def extract_data(self, cik: str) -> Optional[requests.Response]:
        """
        Extract data from SEC XBRL API.
        
        :param cik: Central Index Key (CIK)
        :return: Response object or None
        """
        cik_padded = cik.zfill(10)
        url = self.url_xbrl.replace('##########', cik_padded)
        
        print(f"  Fetching: {url}")
        res = self.reqsesh.get(url)
        
        if res.status_code != 200:
            print(f"  Failed: HTTP {res.status_code}")
            return None
        
        return res


if __name__ == "__main__":
    sec = SEC()