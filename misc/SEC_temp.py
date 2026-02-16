import json, csv, os, sys, re
import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent, FakeUserAgent
import requests
import pandas as pd
import numpy as np
from typing import Dict, List

# Add modules from base repo
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

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
        This class will be used to scrape information from the SEC website for publically traded companies
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
        jpath = os.path.join(self.base_dir, "config/cik.json")
        self.cik_map = None
        with open(jpath, 'r') as f:
            self.cik_map = json.load(f)

        self.tickers = ['PLTR', 'BABA', 'VALE', 'WMT', 'SMCI']
        self.tickers = ['PLTR', 'AXTI', 'GOLD']
        print(f"Printing out the following tickers: {self.tickers}")

        # Store all ticker data for pivoting
        self.all_ticker_data = []

        for ticker in self.tickers:
            gaap_record = self.fetch_sec_filing(ticker)
            if gaap_record:
                gaap_record_cleaned = gaap_record.json()
                #print(ticker, "\n", json.dumps(gaap_record_cleaned, indent=4))
                #save_json(os.path.join(os.path.dirname(__file__), f"data\\{ticker}.json"), gaap_record_cleaned)
                self.clean_facts(gaap_record_cleaned, ticker)
            print("\n\n")

        # After processing all tickers, create pivoted views
        self.create_pivoted_views()

        self.ef.save(f"EDGAR_FINANCIALS_{datetime.datetime.now().strftime('%Y%m%d')}_{datetime.datetime.now().strftime('%H%M%S')}.xlsx", os.path.join(os.path.dirname(__file__), "data"))


    def categorize_field_type(self, field_name: str) -> str:
        """
        Categorize a field into Balance Sheet, Income Statement, or Cash Flow based on common GAAP naming patterns.

        :param field_name: The GAAP field name
        :return: Statement type ('Balance Sheet', 'Income Statement', 'Cash Flow', or 'Other')
        """
        field_lower = field_name.lower()

        # Balance Sheet items (Assets, Liabilities, Equity)
        balance_sheet_keywords = [
            'assets', 'liabilities', 'equity', 'stockholders', 'shareholders',
            'cash', 'inventory', 'receivable', 'payable', 'debt', 'capital',
            'retained', 'goodwill', 'intangible', 'property', 'plant', 'equipment',
            'investment', 'deferred', 'accumulated', 'current', 'noncurrent'
        ]

        # Income Statement items (Revenue, Expenses, Income)
        income_statement_keywords = [
            'revenue', 'sales', 'income', 'earnings', 'profit', 'loss',
            'expense', 'cost', 'margin', 'ebitda', 'ebit', 'operating',
            'gross', 'net', 'tax', 'interest', 'depreciation', 'amortization'
        ]

        # Cash Flow items
        cash_flow_keywords = [
            'cashflow', 'cash flow', 'operating activities', 'investing activities',
            'financing activities', 'free cash flow'
        ]

        # Check keywords
        for keyword in balance_sheet_keywords:
            if keyword in field_lower:
                return 'Balance Sheet'

        for keyword in income_statement_keywords:
            if keyword in field_lower:
                return 'Income Statement'

        for keyword in cash_flow_keywords:
            if keyword in field_lower:
                return 'Cash Flow'

        return 'Other'

    def normalize_fiscal_quarter(self, fy: int, fp: str, end_date: str) -> str:
        """
        Normalize fiscal quarter to calendar format based on fiscal year end date.

        :param fy: Fiscal year
        :param fp: Fiscal period (Q1, Q2, Q3, Q4, FY)
        :param end_date: End date of the reporting period
        :return: Normalized quarter string (e.g., '2023-Q1')
        """
        if not fy or not fp or not end_date:
            return None

        # Parse the end date
        try:
            end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
        except:
            return None

        # For full year filings, use FY designation
        if fp == 'FY':
            return f"{fy}-FY"

        # For quarterly filings, create normalized quarter label
        # Use the actual calendar year and quarter from the end date
        calendar_year = end_dt.year
        calendar_month = end_dt.month

        # Determine calendar quarter
        if calendar_month in [1, 2, 3]:
            calendar_quarter = 'Q1'
        elif calendar_month in [4, 5, 6]:
            calendar_quarter = 'Q2'
        elif calendar_month in [7, 8, 9]:
            calendar_quarter = 'Q3'
        else:
            calendar_quarter = 'Q4'

        return f"{calendar_year}-{calendar_quarter}"

    def create_pivoted_views(self):
        """
        Create pivoted views where rows are tickers and columns are quarters,
        separated by statement type.
        """
        if not self.all_ticker_data:
            print("No data to pivot")
            return

        # Combine all ticker data
        combined_df = pd.DataFrame(self.all_ticker_data)

        if combined_df.empty:
            print("Combined dataframe is empty")
            return

        print(f"\nCreating pivoted views with {len(combined_df)} total records...")

        # Get unique statement types
        statement_types = combined_df['StatementType'].unique()

        for stmt_type in statement_types:
            if stmt_type == 'Other':
                continue

            print(f"\nProcessing {stmt_type}...")

            # Filter by statement type
            stmt_df = combined_df[combined_df['StatementType'] == stmt_type].copy()

            # Get unique fields for this statement type
            unique_fields = stmt_df['Field'].unique()

            for field in unique_fields[:20]:  # Limit to first 20 fields to avoid huge files
                field_df = stmt_df[stmt_df['Field'] == field].copy()

                # Remove duplicates - keep most recent filing per ticker-quarter combo
                field_df = field_df.sort_values('FilingDate', ascending=False)
                field_df = field_df.drop_duplicates(subset=['Ticker', 'NormalizedQuarter'], keep='first')

                # Pivot: rows = tickers, columns = quarters
                try:
                    pivot_df = field_df.pivot(index='Ticker', columns='NormalizedQuarter', values='Value')

                    # Sort columns chronologically
                    pivot_df = pivot_df.reindex(sorted(pivot_df.columns), axis=1)

                    # Add to Excel
                    sheet_name = f"{stmt_type[:10]}_{field[:15]}"  # Truncate for Excel sheet name limits
                    sheet_name = re.sub(r'[^\w\s-]', '', sheet_name)  # Remove invalid characters

                    print(f"  Adding sheet: {sheet_name}")
                    self.ef.add_to_sheet(pivot_df.reset_index(), sheet_name=sheet_name)
                except Exception as e:
                    print(f"  Error pivoting field {field}: {e}")

    def clean_facts(self, json, ticker: str) -> pd.DataFrame:
        """
        Given a suite of company facts data from SEC, clean it up and categorize by statement type

        :param json: JSON data which pertains to the facts being brought on for the particular ticker (company)
        :param ticker: The stock ticker symbol
        """
        cik = json.get("cik", None)
        if not cik:
            print(f"\nThere is no CIK for the company you passed in.")
            return None

        entity = json.get("entityName", None)
        if not entity:
            print(f"\nThere is no entityName for the data you passed in")
            return None

        facts = json.get("facts", None)
        if not facts:
            print(f"\nThere are no facts for the given entity: {entity}\n")
            return None

        cfacts = []
        for _, value in facts.items():
            for field, data in value.items():
                # Categorize the field type
                statement_type = self.categorize_field_type(field)

                for metafield, attr in data.items():
                    if "units" == metafield:
                        for _, unit_list in attr.items():
                            for obj in unit_list:
                                fy = obj.get("fy", None)
                                fp = obj.get("fp", None)
                                end_date = obj.get("end", None)

                                # Normalize fiscal quarter
                                normalized_quarter = self.normalize_fiscal_quarter(fy, fp, end_date)

                                # Create data row
                                row = {
                                    'Ticker': ticker,
                                    'CIK': cik,
                                    'EntityName': entity,
                                    'Field': field,
                                    'StatementType': statement_type,
                                    'Timestamp': end_date,
                                    'Value': obj.get("val", None),
                                    'AccountNumber': obj.get("accn", None),
                                    'FiscalYear': fy,
                                    'FiscalPeriod': fp,
                                    'NormalizedQuarter': normalized_quarter,
                                    'Form': obj.get("form", None),
                                    'FilingDate': obj.get("filed", None),
                                    'Frame': obj.get("frame", None)
                                }
                                cfacts.append(row)

        # Store raw data for this ticker
        self.all_ticker_data.extend(cfacts)

        # Also save raw data per entity for reference
        fdata = pd.DataFrame(cfacts)
        print(f"Processed {len(fdata)} records for {ticker}")

        self.ef.add_to_sheet(fdata, sheet_name=f"{ticker}_RAW")

    def fetch_sec_filing(self, ticker: str) -> bytes:
        """
        Fetch filings for a list of companies and save the aggregated data.
        
        :param cik_list: List of 10-digit CIK strings.
        """
        cik = self.cik_map[ticker]
        filings_data = self.extract_data(cik)
        print(filings_data, "\n\n")
        if filings_data:
            return filings_data
        else:
            print(f"No data found for ticker: {ticker}")


    def fetch_accounts_payable(self, cik: str) -> bytes:
        """
        Fetch filings for a list of companies and save the aggregated data.

        :param cik_list: List of 10-digit CIK strings.
        """
        filings_data = self.extract_data(cik)
        if filings_data:
            return filings_data
        else:
            print(f"\n[SEC] - No accounts payable data found...")
            return b""

    def extract_data(self, cik: str) -> bytes:
        print(f"\n[REGI] - Extracting data for the following CIK (Central Index Key): {cik}\n")
        url = self.url_xbrl.replace('##########', cik)

        print(url)
        res = self.reqsesh.get(url)

        return res

    


if __name__=="__main__":
    sec = SEC()