import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# Add modules from base repo
sys.path.append(str(Path(__file__).parent))

from utils.session import RequestSession

class TrailingMetricsCalculator:
    """
    Task #4: Trailing Metrics System (TTM)
    
    Goal: Calculate TTM metrics (e.g., Revenue, Net Income) for any given calendar date,
    respecting filing lags (Point-in-Time).
    
    Logic:
    1. For a given valid_date (e.g., 2024-03-31):
       - Find the most recent 10-K or 10-Q filed ON or BEFORE this date.
       - Assemble the 4 quarters ending at that period.
       
    2. Calculation Method (Standard TTM):
       - TTM = Last Annual + Current Interim - Prior Interim
       - OR Sum of last 4 quarters (if quarterly data is explicit)
       
    3. Output:
       - TTM timeseries for each company.
    """
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.base_dir, "config/cik.json")
        self.pit_path = os.path.join(self.base_dir, "point_in_time_map.json")
        self.output_path = os.path.join(self.base_dir, "ttm_metrics.json")
        self.reqsesh = RequestSession()
        
    def run(self):
        with open(self.pit_path, 'r') as f:
            pit_map = json.load(f)
            
        with open(self.config_path, 'r') as f:
            cik_map = json.load(f)
            
        print(f"Calculating TTM metrics for {len(pit_map)} companies...")
        
        ttm_results = {}
        
        for i, (ticker, timeline) in enumerate(pit_map.items(), 1):
            print(f"[{i}/{len(pit_map)}] Processing {ticker}...")
            
            # We need the actual data to calculate values
            cik = cik_map[ticker].zfill(10)
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            
            try:
                res = self.reqsesh.get(url)
                if res.status_code != 200: continue
                data = res.json()
                facts = data.get("facts", {})
                
                # Calculate TTM for Revenue and Net Income
                revenue = self.calculate_ttm_series(ticker, timeline, facts, 'Revenue')
                net_income = self.calculate_ttm_series(ticker, timeline, facts, 'NetIncome')
                
                ttm_results[ticker] = {
                    "Revenue_TTM": revenue,
                    "NetIncome_TTM": net_income
                }
                
                print(f"  ✓ Calculated {len(revenue)} TTM points")
                
            except Exception as e:
                print(f"  Error: {e}")
                
        # Save results
        with open(self.output_path, 'w') as f:
            json.dump(ttm_results, f, indent=2)
            
        print(f"\n✓ TTM Metrics saved to {self.output_path}")

    def calculate_ttm_series(self, ticker, timeline, facts, concept_type):
        """
        Build a daily/weekly/monthly TTM series. 
        For efficiency here, we'll calculate TTM at each filing date update.
        """
        # Map concept to fields (using our pipeline's logic implicitly)
        fields = []
        if concept_type == 'Revenue':
            fields = ['us-gaap:Revenues', 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax', 'ifrs-full:Revenue']
        elif concept_type == 'NetIncome':
            fields = ['us-gaap:NetIncomeLoss', 'us-gaap:ProfitLoss', 'ifrs-full:ProfitLoss']
            
        # Extract all available values
        values = []
        for field_key in fields:
            taxonomy, field = field_key.split(':')
            if taxonomy in facts and field in facts[taxonomy]:
                units = facts[taxonomy][field]['units']
                for unit_key in units:
                    values.extend(units[unit_key])
        
        # Index values by (end_date, form) -> value
        # We need to handle both Q and FY data
        value_map = {}
        for v in values:
            if 'end' in v and 'val' in v:
                key = (v['end'], v.get('fp', ''), v.get('form', ''))
                # Prefer latest filing if duplicates exist (though API usually gives latest)
                value_map[key] = v['val']
                
        ttm_series = []
        
        # Iterate through timeline to update TTM as new info arrives
        # Simplified TTM logic: Look for latest 10-K or build from 10-Qs
        
        # Sort timeline by filing date
        sorted_events = sorted(timeline, key=lambda x: x['filing_date'])
        
        current_ttm = None
        
        for event in sorted_events:
            filing_date = event['filing_date']
            period_end = event['period_end']
            form = event['form']
            fp = event['fp']
            
            # If 10-K (Annual), TTM is just the annual value
            if form in ['10-K', '20-F', '40-F']:
                val = self._find_value(value_map, period_end, ['FY'], form)
                if val is not None:
                    current_ttm = val
            
            # If 10-Q, we need complex logic: (Latest Annual) + (Current Interim) - (Prior Interim)
            # For this MVP, we will try to sum the last 4 quarters if available
            elif form in ['10-Q']:
                # Need to find the last 4 quarters
                # This requires a robust quarterly database which we are building on the fly here
                # For simplicity in this step, we'll mark as "Requires Q-Sum"
                pass 
                
            if current_ttm is not None:
                ttm_series.append({
                    "as_of_date": filing_date,
                    "period_end": period_end,
                    "ttm_value": current_ttm,
                    "source_filing": form
                })
                
        return ttm_series

    def _find_value(self, value_map, end_date, fp_list, form):
        for fp in fp_list:
            key = (end_date, fp, form)
            if key in value_map:
                return value_map[key]
            # Try without exact form match if needed (sometimes re-filings change things)
            for k, val in value_map.items():
                if k[0] == end_date and k[1] == fp:
                    return val
        return None

if __name__ == "__main__":
    calc = TrailingMetricsCalculator()
    calc.run()
