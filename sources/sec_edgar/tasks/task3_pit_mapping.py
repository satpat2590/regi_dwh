import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# Add modules from base repo
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from utils.session import RequestSession

class PointInTimeMapper:
    """
    Task #3: Point-in-Time Calendar Mapping
    
    Goal: Prevent look-ahead bias by tracking EXACTLY when data became known.
    
    Logic:
    1. For every data point, capturing TWO dates:
       - Period End Date (when the fiscal period ended)
       - Filing Date (when the 10-Q/10-K was filed with SEC)
    
    2. Handling Amendments:
       - If a 10-K/A is filed later, the "known value" changes ONLY after that new filing date.
       
    3. Output:
       - A timeline of available data for each company.
    """
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = str(Path(self.base_dir).parent.parent.parent)
        self.config_path = os.path.join(self.root_dir, "config/cik.json")
        self.fye_path = os.path.join(self.root_dir, "reports/fiscal_year_metadata.json")
        self.output_path = os.path.join(self.root_dir, "reports/point_in_time_map.json")
        self.reqsesh = RequestSession()
        
    def run(self):
        with open(self.fye_path, 'r') as f:
            fye_metadata = json.load(f)
            
        tickers = list(fye_metadata.keys())
        pit_data = {}
        
        print(f"Building Point-in-Time Map for {len(tickers)} companies...")
        
        for i, ticker in enumerate(tickers, 1):
            print(f"[{i}/{len(tickers)}] Processing {ticker}...")
            
            # Fetch full facts
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{self.get_cik(ticker)}.json"
            try:
                res = self.reqsesh.get(url)
                if res.status_code != 200:
                    print(f"  Failed to fetch: {res.status_code}")
                    continue
                data = res.json()
                facts = data.get("facts", {})
                
                # Build timeline for this company
                company_timeline = self.build_company_timeline(ticker, facts)
                pit_data[ticker] = company_timeline
                
                print(f"  ✓ Processed {len(company_timeline)} filing events")
                
            except Exception as e:
                print(f"  Error: {e}")
                
        # Save results
        with open(self.output_path, 'w') as f:
            json.dump(pit_data, f, indent=2)
            
        print(f"\n✓ Point-in-Time mapping saved to {self.output_path}")
        
    def get_cik(self, ticker):
        with open(self.config_path, 'r') as f:
            cik_map = json.load(f)
        return cik_map[ticker].zfill(10)

    def build_company_timeline(self, ticker, facts):
        """
        Scan all critical facts to identify filing events.
        We only care about when a filing happened and what period it covered.
        """
        filing_events = []
        
        # We need to scan enough fields to ensure we capture every filing
        # Checking Assets and NetIncome usually covers 10-K and 10-Q
        scan_fields = [
            'us-gaap:Assets', 
            'us-gaap:StockholdersEquity',
            'us-gaap:NetIncomeLoss',
            'ifrs-full:Assets',
            'ifrs-full:Equity'
        ]
        
        seen_accessions = set()
        
        for field_key in scan_fields:
            taxonomy, field = field_key.split(':')
            if taxonomy not in facts or field not in facts[taxonomy]:
                continue
                
            units = facts[taxonomy][field]['units']
            # flattened facts list (USD and shares)
            all_facts = []
            for unit_key in units:
                all_facts.extend(units[unit_key])
                
            for fact in all_facts:
                acc = fact.get('accn')
                if acc in seen_accessions:
                    continue
                
                if 'filed' not in fact:
                    continue
                    
                seen_accessions.add(acc)
                
                event = {
                    "filing_date": fact.get('filed'),
                    "period_end": fact.get('end'),
                    "form": fact.get('form'),
                    "fy": fact.get('fy'),
                    "fp": fact.get('fp'),
                    "accession": acc
                }
                filing_events.append(event)
        
        # Sort by filing date
        filing_events.sort(key=lambda x: x['filing_date'])
        
        return filing_events

if __name__ == "__main__":
    mapper = PointInTimeMapper()
    mapper.run()
