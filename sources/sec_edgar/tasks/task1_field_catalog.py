import json
import os
import sys
from pathlib import Path
from collections import defaultdict

# Add modules from base repo
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from utils.session import RequestSession

def build_expanded_field_catalog():
    """
    Expanded Field Catalog: 20 companies across major sectors
    
    Sectors covered:
    - Technology: PLTR, MSFT, AAPL, NVDA
    - Finance: JPM, BAC, WFC
    - Retail: WMT, AMZN, COST
    - Healthcare: JNJ, UNH, PFE
    - Energy: XOM, CVX
    - Mining/Materials: GOLD, VALE, FCX
    - Industrial: CAT, GE
    - Telecom: VZ
    """
    # Configuration
    reqsesh = RequestSession()
    url_xbrl = "https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = str(Path(base_dir).parent.parent.parent)
    jpath = os.path.join(root_dir, "config/cik.json")
    
    with open(jpath, 'r') as f:
        cik_map = json.load(f)

    # Diverse ticker set across sectors
    tickers = [
        # Technology
        'PLTR', 'MSFT', 'AAPL', 'NVDA',
        # Finance
        'JPM', 'BAC', 'WFC',
        # Retail
        'WMT', 'AMZN', 'COST',
        # Healthcare
        'JNJ', 'UNH', 'PFE',
        # Energy
        'XOM', 'CVX',
        # Mining/Materials
        'GOLD', 'VALE', 'FCX',
        # Industrial
        'CAT', 'GE',
        # Telecom
        'VZ'
    ]
    
    print(f"Building expanded field catalog for {len(tickers)} tickers across sectors:\n")
    print(f"Technology: PLTR, MSFT, AAPL, NVDA")
    print(f"Finance: JPM, BAC, WFC")
    print(f"Retail: WMT, AMZN, COST")
    print(f"Healthcare: JNJ, UNH, PFE")
    print(f"Energy: XOM, CVX")
    print(f"Mining/Materials: GOLD, VALE, FCX")
    print(f"Industrial: CAT, GE")
    print(f"Telecom: VZ")
    print(f"\n{'='*70}\n")

    # Field catalog structure
    field_catalog = {}
    successful_tickers = []
    failed_tickers = []
    
    for i, ticker in enumerate(tickers, 1):
        if ticker not in cik_map:
            print(f"[{i}/{len(tickers)}] {ticker}: NOT FOUND in CIK map")
            failed_tickers.append(ticker)
            continue
            
        cik = cik_map[ticker]
        cik_padded = cik.zfill(10)
        
        print(f"[{i}/{len(tickers)}] Fetching {ticker} (CIK: {cik_padded})...")
        url = url_xbrl.replace('##########', cik_padded)
        
        try:
            res = reqsesh.get(url)
            if res.status_code != 200:
                print(f"  ✗ Failed: HTTP {res.status_code}")
                failed_tickers.append(ticker)
                continue
                
            data = res.json()
            
            facts = data.get("facts", {})
            if not facts:
                print(f"  ✗ No facts found")
                failed_tickers.append(ticker)
                continue

            field_count = 0
            # Process each taxonomy
            for taxonomy, fields_dict in facts.items():
                for field_name, field_data in fields_dict.items():
                    field_count += 1
                    
                    # Initialize field in catalog if not exists
                    if field_name not in field_catalog:
                        field_catalog[field_name] = {
                            "taxonomy": taxonomy,
                            "label": field_data.get("label", ""),
                            "description": field_data.get("description", ""),
                            "count": 0,
                            "companies_using": []
                        }
                    
                    # Add this company to the list
                    if ticker not in field_catalog[field_name]["companies_using"]:
                        field_catalog[field_name]["companies_using"].append(ticker)
                        field_catalog[field_name]["count"] += 1
            
            successful_tickers.append(ticker)
            print(f"  ✓ Success: {field_count} fields processed")
                    
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed_tickers.append(ticker)

    # Save the catalog
    output_path = os.path.join(root_dir, "reports/field_catalog.json")
    print(f"\n{'='*70}")
    print(f"EXPANDED FIELD CATALOG SUMMARY")
    print(f"{'='*70}")
    print(f"Successful companies: {len(successful_tickers)}/{len(tickers)}")
    if failed_tickers:
        print(f"Failed companies: {', '.join(failed_tickers)}")
    print(f"\nTotal unique fields: {len(field_catalog)}")
    
    # Count fields by availability
    availability_breakdown = defaultdict(int)
    for field_data in field_catalog.values():
        count = field_data["count"]
        availability_breakdown[count] += 1
    
    print(f"\nField Availability Distribution:")
    for count in sorted(availability_breakdown.keys(), reverse=True):
        num_fields = availability_breakdown[count]
        pct = (num_fields / len(field_catalog)) * 100
        if count >= len(successful_tickers) * 0.8:  # 80%+ companies
            print(f"  {count:2d} companies ({count/len(successful_tickers)*100:5.1f}%): {num_fields:4d} fields ({pct:5.1f}%) ← Universal")
        elif count >= len(successful_tickers) * 0.5:  # 50%+ companies
            print(f"  {count:2d} companies ({count/len(successful_tickers)*100:5.1f}%): {num_fields:4d} fields ({pct:5.1f}%) ← Common")
        elif count <= 3:
            print(f"  {count:2d} companies ({count/len(successful_tickers)*100:5.1f}%): {num_fields:4d} fields ({pct:5.1f}%) ← Rare")
    
    # Get taxonomy breakdown
    taxonomy_counts = defaultdict(int)
    for field_data in field_catalog.values():
        taxonomy_counts[field_data["taxonomy"]] += 1
    
    print(f"\nFields by Taxonomy:")
    for taxonomy, count in sorted(taxonomy_counts.items(), key=lambda x: -x[1]):
        print(f"  {taxonomy}: {count} fields")
    
    print(f"\nSaving catalog to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(field_catalog, f, indent=2)
    
    print(f"✓ Complete!")
    
    # Also update the simple list
    unique_fields_path = os.path.join(root_dir, "reports/output.txt")
    sorted_fields = sorted(field_catalog.keys())
    with open(unique_fields_path, 'w') as f:
        for field in sorted_fields:
            f.write(f"{field}\n")
    print(f"✓ Also updated {unique_fields_path}")
    
    # Save metadata about this run
    metadata = {
        "tickers_analyzed": successful_tickers,
        "failed_tickers": failed_tickers,
        "total_fields": len(field_catalog),
        "total_companies": len(successful_tickers)
    }
    metadata_path = os.path.join(root_dir, "reports/field_catalog_metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Metadata saved to {metadata_path}")

if __name__ == "__main__":
    build_expanded_field_catalog()
