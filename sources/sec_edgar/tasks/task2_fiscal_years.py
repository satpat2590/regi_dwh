import json
import os
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

# Add modules from base repo
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from utils.session import RequestSession

class FiscalYearCataloger:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = str(Path(self.base_dir).parent.parent.parent)
        self.config_path = os.path.join(self.root_dir, "config/cik.json")
        self.output_path = os.path.join(self.root_dir, "reports/fiscal_year_metadata.json")
        self.reqsesh = RequestSession()
        
    def run(self):
        with open(self.config_path, 'r') as f:
            cik_map = json.load(f)
            
        # Target diverse ticker set
        tickers = [
            'PLTR', 'MSFT', 'AAPL', 'NVDA',  # Tech
            'JPM', 'BAC', 'WFC',             # Finance
            'WMT', 'AMZN', 'COST',           # Retail
            'JNJ', 'UNH', 'PFE',             # Healthcare
            'XOM', 'CVX',                    # Energy
            'GOLD', 'VALE', 'FCX',           # Mining
            'CAT', 'GE',                     # Industrial
            'VZ'                             # Telecom
        ]
        
        fye_metadata = {}
        
        print(f"Cataloging Fiscal Year Ends for {len(tickers)} companies...")
        
        for i, ticker in enumerate(tickers, 1):
            if ticker not in cik_map:
                print(f"[{i}/{len(tickers)}] {ticker}: Skipping (Not in CIK map)")
                continue
                
            cik = cik_map[ticker]
            cik_padded = cik.zfill(10)
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
            
            try:
                print(f"[{i}/{len(tickers)}] Processing {ticker}...")
                res = self.reqsesh.get(url)
                if res.status_code != 200:
                    print(f"  Failed to fetch: {res.status_code}")
                    continue
                    
                data = res.json()
                facts = data.get("facts", {})
                
                fye_info = self.determine_fye(ticker, facts)
                if fye_info:
                    fye_metadata[ticker] = fye_info
                    print(f"  ✓ FYE: {fye_info['fiscal_year_end_month']} (Confidence: {fye_info['confidence']})")
                else:
                    print(f"  ✗ Could not determine FYE")
                    
            except Exception as e:
                print(f"  Error: {e}")
        
        # Save results
        with open(self.output_path, 'w') as f:
            json.dump(fye_metadata, f, indent=2)
            
        print(f"\nSaved FYE metadata to {self.output_path}")
        
    def determine_fye(self, ticker, facts):
        """
        Deduce FYE from 10-K/20-F/40-F filing dates.
        Strategy: Look at the 'end' date of 'Assets' reported in annual filings.
        """
        candidate_dates = []
        
        # Priority fields to check (Universal fields)
        fields_to_check = [
            'us-gaap:Assets', 
            'ifrs-full:Assets', 
            'us-gaap:StockholdersEquity',
            'ifrs-full:Equity',
            'us-gaap:LiabilitiesAndStockholdersEquity'
        ]
        
        found_facts = []
        
        # find the first available field
        for field_key in fields_to_check:
            taxonomy, field = field_key.split(':')
            if taxonomy in facts and field in facts[taxonomy]:
                found_facts = facts[taxonomy][field]['units'].get('USD', [])
                if not found_facts and 'shares' in facts[taxonomy][field]['units']: 
                     # Fallback to shares if USD not found (unlikely for Assets but possible for Equity if defined weirdly)
                     found_facts = facts[taxonomy][field]['units']['shares']
                
                if found_facts:
                    break
        
        if not found_facts:
            # Try searching any field in facts if persistent failure
            # But usually Assets is there.
            return None

        annual_forms = ['10-K', '10-K/A', '20-F', '20-F/A', '40-F', '40-F/A']
        
        for fact in found_facts:
            if fact.get('form') in annual_forms:
                try:
                    end_date_str = fact.get('end')
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                    candidate_dates.append(end_date)
                except:
                    continue
                    
        if not candidate_dates:
            return {"fiscal_year_end_month": "Unknown", "confidence": "None", "notes": "No annual filings found in key fields"}
            
        # Analyze dates
        month_counts = Counter()
        details = []
        
        for d in candidate_dates:
            # Bucket by month (name)
            month_name = d.strftime("%B")
            month_counts[month_name] += 1
            details.append(d.strftime("%Y-%m-%d"))
            
        most_common_month = month_counts.most_common(1)[0]
        month_name = most_common_month[0]
        count = most_common_month[1]
        total = len(candidate_dates)
        
        confidence = "High" if count / total > 0.8 else "Medium"
        if total < 3: confidence = "Low"
        
        # Check for 52/53 week variance (dates aren't all same day of month)
        # e.g. dates ending 28, 29, 30.
        
        return {
            "fiscal_year_end_month": month_name,
            "confidence": confidence,
            "sample_size": total,
            "dominant_month_pct": round(count/total * 100, 1),
            "filing_forms_found": list(set(f.get('form') for f in found_facts if f.get('form') in annual_forms)),
            "recent_filing_date": max(candidate_dates).strftime("%Y-%m-%d") if candidate_dates else None
        }

if __name__ == "__main__":
    cataloger = FiscalYearCataloger()
    cataloger.run()
