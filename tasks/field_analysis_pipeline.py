import json
import os
import sys
import re
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher

# Add modules from base repo
sys.path.append(str(Path(__file__).parent.parent))

from utils.session import RequestSession

class FieldAnalysisPipeline:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.dirname(self.base_dir)
        self.config_path = os.path.join(self.root_dir, "config/cik.json")
        self.output_files = {
            "catalog": os.path.join(self.root_dir, "reports/field_catalog.json"),
            "categories": os.path.join(self.root_dir, "reports/field_categories.json"),
            "availability": os.path.join(self.root_dir, "reports/field_availability_report.json"),
            "mapping": os.path.join(self.root_dir, "reports/field_mapping.json"),
            "priority": os.path.join(self.root_dir, "reports/field_priority.json"),
            "metadata": os.path.join(self.root_dir, "reports/field_catalog_metadata.json"),
            "output_txt": os.path.join(self.root_dir, "reports/output.txt")
        }
        
    def run(self):
        print("="*80)
        print("STARTING FIELD ANALYSIS PIPELINE")
        print("="*80)
        
        # Step 1: Cataloging
        print("\n--- Phase 1: Field Cataloging ---")
        field_catalog, metadata = self.build_catalog()
        
        # Step 2: Categorization
        print("\n--- Phase 2: Field Categorization ---")
        field_categories = self.categorize_fields(field_catalog)
        
        # Step 3: Availability Analysis
        print("\n--- Phase 3: Availability Analysis ---")
        availability_report = self.analyze_availability(field_catalog, field_categories, metadata)
        
        # Step 4: Standardization
        print("\n--- Phase 4: Standardization Rules ---")
        self.create_standardization_rules(field_catalog, field_categories, availability_report)
        
        print("\n" + "="*80)
        print("PIPELINE COMPLETE")
        print("="*80)
        print("Generated files:")
        for name, path in self.output_files.items():
            print(f"  • {path}")

    def build_catalog(self):
        """Phase 1: Build field catalog from diverse company set"""
        reqsesh = RequestSession()
        url_xbrl = "https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json"
        
        with open(self.config_path, 'r') as f:
            cik_map = json.load(f)

        # Diverse ticker set across sectors
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
        
        field_catalog = {}
        successful_tickers = []
        failed_tickers = []
        
        print(f"Fetching data for {len(tickers)} companies...")
        
        for i, ticker in enumerate(tickers, 1):
            if ticker not in cik_map:
                print(f"[{i}/{len(tickers)}] {ticker}: NOT FOUND in CIK map")
                failed_tickers.append(ticker)
                continue
                
            cik = cik_map[ticker]
            cik_padded = cik.zfill(10)
            url = url_xbrl.replace('##########', cik_padded)
            
            try:
                # Mock progress for existing files if we want to skip re-fetching
                # But for this pipeline, we'll implement the actual fetch logic
                res = reqsesh.get(url)
                if res.status_code != 200:
                    print(f"  [{i}/{len(tickers)}] {ticker}: Failed (HTTP {res.status_code})")
                    failed_tickers.append(ticker)
                    continue
                    
                data = res.json()
                facts = data.get("facts", {})
                
                if not facts:
                    print(f"  [{i}/{len(tickers)}] {ticker}: No facts found")
                    failed_tickers.append(ticker)
                    continue

                field_count = 0
                for taxonomy, fields_dict in facts.items():
                    for field_name, field_data in fields_dict.items():
                        field_count += 1
                        
                        if field_name not in field_catalog:
                            field_catalog[field_name] = {
                                "taxonomy": taxonomy,
                                "label": field_data.get("label", ""),
                                "description": field_data.get("description", ""),
                                "count": 0,
                                "companies_using": []
                            }
                        
                        if ticker not in field_catalog[field_name]["companies_using"]:
                            field_catalog[field_name]["companies_using"].append(ticker)
                            field_catalog[field_name]["count"] += 1
                
                successful_tickers.append(ticker)
                # Simple progress indicator
                print(f"  [{i}/{len(tickers)}] {ticker}: Success ({field_count} fields)")
                        
            except Exception as e:
                print(f"  [{i}/{len(tickers)}] {ticker}: Error ({str(e)})")
                failed_tickers.append(ticker)

        # Save catalog
        with open(self.output_files["catalog"], 'w') as f:
            json.dump(field_catalog, f, indent=2)
            
        # Save simple list
        with open(self.output_files["output_txt"], 'w') as f:
            for field in sorted(field_catalog.keys()):
                f.write(f"{field}\n")
                
        # Save metadata
        metadata = {
            "tickers_analyzed": successful_tickers,
            "failed_tickers": failed_tickers,
            "total_fields": len(field_catalog),
            "total_companies": len(successful_tickers)
        }
        with open(self.output_files["metadata"], 'w') as f:
            json.dump(metadata, f, indent=2)
            
        print(f"✓ Catalog built: {len(field_catalog)} unique fields from {len(successful_tickers)} companies")
        return field_catalog, metadata

    def categorize_fields(self, field_catalog):
        """Phase 2: Categorize fields"""
        field_categories = {}
        
        for field_name, field_info in field_catalog.items():
            label = (field_info.get("label") or "").lower()
            description = (field_info.get("description") or "").lower()
            
            category = {
                "field_name": field_name,
                "label": field_info.get("label", ""),
                "taxonomy": field_info.get("taxonomy", ""),
                "statement_type": self._categorize_statement_type(field_name, label, description),
                "temporal_nature": self._categorize_temporal_nature(field_name, label, description),
                "accounting_concept": self._categorize_accounting_concept(field_name, label, description),
                "is_critical": self._is_critical_field(field_name),
                "special_handling": self._identify_special_handling(field_name, label, description),
                "companies_using": field_info.get("companies_using", []),
                "count": field_info.get("count", 0)
            }
            field_categories[field_name] = category
        
        with open(self.output_files["categories"], 'w') as f:
            json.dump(field_categories, f, indent=2)
            
        print(f"✓ Categorized {len(field_categories)} fields")
        return field_categories

    def analyze_availability(self, field_catalog, field_categories, metadata):
        """Phase 3: Analyze availability"""
        total_companies = metadata["total_companies"]
        
        # Load sector mapping from enrichment data
        company_metadata_path = os.path.join(os.path.dirname(self.base_dir), "config", "company_metadata.json")
        ticker_to_sector = {}
        try:
            with open(company_metadata_path, 'r') as f:
                company_metadata = json.load(f)
            for ticker, meta in company_metadata.items():
                ticker_to_sector[ticker] = meta.get("sector", "Unknown")
        except FileNotFoundError:
            print("Warning: config/company_metadata.json not found. Run enrich.py first. Using empty sector map.")
        
        availability_tiers = {k: [] for k in ["universal", "very_common", "common", "moderate", "rare", "very_rare"]}
        field_analysis = {}
        
        for field_name, field_info in field_catalog.items():
            count = field_info["count"]
            availability_pct = (count / total_companies) * 100
            
            # Determine tier
            if availability_pct >= 90: tier = "universal"
            elif availability_pct >= 70: tier = "very_common"
            elif availability_pct >= 50: tier = "common"
            elif availability_pct >= 30: tier = "moderate"
            elif availability_pct >= 10: tier = "rare"
            else: tier = "very_rare"
            
            availability_tiers[tier].append(field_name)
            
            # Sector analysis
            sector_dist = defaultdict(int)
            for ticker in field_info["companies_using"]:
                sector_dist[ticker_to_sector.get(ticker, "Unknown")] += 1
            
            is_sector_specific = False
            dominant_sector = None
            if sector_dist:
                max_sector = max(sector_dist.items(), key=lambda x: x[1])
                dominant_sector = max_sector[0]
                if max_sector[1] / count > 0.8 and count >= 3:
                    is_sector_specific = True
            
            category_info = field_categories.get(field_name, {})
            
            field_analysis[field_name] = {
                "availability_count": count,
                "availability_percentage": round(availability_pct, 1),
                "availability_tier": tier,
                "companies_using": field_info["companies_using"],
                "sector_distribution": dict(sector_dist),
                "is_sector_specific": is_sector_specific,
                "dominant_sector": dominant_sector if is_sector_specific else None,
                "statement_type": category_info.get("statement_type", "Unknown"),
                "temporal_nature": category_info.get("temporal_nature", "Unknown"),
                "is_critical": category_info.get("is_critical", False),
                "accounting_concept": category_info.get("accounting_concept", []),
                "taxonomy": field_info.get("taxonomy", ""),
                "label": field_info.get("label", "")
            }
        
        summary = {
            "total_companies_analyzed": total_companies,
            "total_unique_fields": len(field_catalog),
            "availability_tiers": {
                k: {"count": len(v), "percentage": round(len(v)/len(field_catalog)*100, 1)} 
                for k, v in availability_tiers.items()
            },
            "sector_specific_fields": sum(1 for f in field_analysis.values() if f["is_sector_specific"])
        }
        
        output = {"summary": summary, "field_analysis": field_analysis}
        with open(self.output_files["availability"], 'w') as f:
            json.dump(output, f, indent=2)
            
        print(f"✓ analyzed availability: {len(availability_tiers['universal'])} universal fields, {len(availability_tiers['very_common'])} very common")
        return output

    def create_standardization_rules(self, field_catalog, field_categories, availability_report):
        """Phase 4: Create standardization rules"""
        field_analysis = availability_report["field_analysis"]
        
        # 1. Deprecated fields
        deprecated = []
        for name, info in field_catalog.items():
            if "deprecated" in (info.get("label") or "").lower() or "deprecated" in (info.get("description") or "").lower():
                deprecated.append({"field_name": name, "label": info.get("label")})
        
        # 2. Similar fields
        similar_groups = self._find_similar_fields(field_catalog, field_analysis)
        
        # 3. Priority mapping
        priority_map = {}
        deprecated_names = {f["field_name"] for f in deprecated}
        
        for name, info in field_catalog.items():
            analysis = field_analysis.get(name, {})
            score = analysis.get("availability_percentage", 0)
            if analysis.get("is_critical", False): score += 50
            if analysis.get("availability_tier") == "universal": score += 25
            elif analysis.get("availability_tier") == "very_common": score += 15
            if name in deprecated_names: score -= 100
            if info.get("taxonomy") == "us-gaap": score += 5
            
            priority_map[name] = {
                "priority_score": round(score, 1),
                "availability": analysis.get("availability_percentage", 0),
                "is_critical": analysis.get("is_critical", False),
                "tier": analysis.get("availability_tier", "")
            }
            
        sorted_priority = dict(sorted(priority_map.items(), key=lambda x: -x[1]["priority_score"]))
        
        rules = {
            "deprecated_fields": deprecated,
            "similar_field_groups": similar_groups,
            "consolidation_recommendations": self._create_consolidation_rules(similar_groups, sorted_priority)
        }
        
        with open(self.output_files["mapping"], 'w') as f:
            json.dump(rules, f, indent=2)
            
        with open(self.output_files["priority"], 'w') as f:
            json.dump(sorted_priority, f, indent=2)
            
        print(f"✓ Standardization complete: {len(similar_groups)} similar field groups identified")

    # --- Helper Methods ---
    
    def _categorize_statement_type(self, field_name, label, description):
        text = f"{field_name.lower()} {label} {description}"
        if any(x in text for x in ['cash flow', 'operating activities']): return "Cash Flow Statement"
        if any(x in text for x in ['revenue', 'income', 'expense', 'profit', 'loss']) and not any(x in text for x in ['deferred', 'payable', 'receivable']): return "Income Statement"
        if any(x in text for x in ['equity', 'stock', 'shares']): return "Balance Sheet - Equity"
        if 'asset' in text: return "Balance Sheet - Assets"
        if 'liability' in text or 'payable' in text: return "Balance Sheet - Liabilities"
        if any(x in text for x in ['balance sheet', 'inventory', 'debt']): return "Balance Sheet"
        if 'entity' in text or 'document' in text: return "Document & Entity Information"
        return "Other/Footnotes"

    def _categorize_temporal_nature(self, field_name, label, description):
        text = f"{field_name.lower()} {label} {description}"
        period_keys = ['during', 'for the period', 'revenue', 'expense', 'income', 'flow', 'increase', 'decrease']
        if any(x in text for x in period_keys): return "Period"
        return "Point-in-Time"

    def _categorize_accounting_concept(self, field_name, label, description):
        text = f"{field_name.lower()} {label} {description}"
        concepts = []
        if any(x in text for x in ['revenue', 'sales']): concepts.append("Revenue")
        if any(x in text for x in ['expense', 'cost']): concepts.append("Expense")
        if any(x in text for x in ['asset', 'receivable', 'inventory']): concepts.append("Asset")
        if any(x in text for x in ['liability', 'payable', 'debt']): concepts.append("Liability")
        if any(x in text for x in ['equity', 'stock', 'capital']): concepts.append("Equity")
        if any(x in text for x in ['cash']): concepts.append("Cash")
        if any(x in text for x in ['tax']): concepts.append("Tax")
        if any(x in text for x in ['share-based']): concepts.append("Share-Based Compensation")
        if any(x in text for x in ['earnings per share', 'eps']): concepts.append("Earnings Per Share")
        return concepts if concepts else ["Other"]

    def _is_critical_field(self, field_name):
        critical = [
            r'Revenue', r'Sales', r'NetIncome', r'EarningsPerShare', r'TotalAssets', 
            r'TotalLiabilities', r'StockholdersEquity', r'CashAndCashEquivalents',
            r'OperatingCashFlow', r'FreeCashFlow', r'GrossProfit', r'OperatingIncome',
            r'AccountsReceivable', r'Inventory', r'AccountsPayable', r'Debt', r'CommonStock',
            r'SharesOutstanding'
        ]
        return any(re.search(p, field_name, re.IGNORECASE) for p in critical)

    def _identify_special_handling(self, field_name, label, description):
        text = f"{field_name.lower()} {label} {description}"
        special = []
        if 'per share' in text or 'pershare' in field_name.lower(): special.append("Per-Share Metric")
        if 'ratio' in text or 'rate' in text: special.append("Ratio/Rate")
        if 'fair value' in text: special.append("Fair Value")
        if 'deferred' in text: special.append("Deferred")
        return special if special else ["Standard"]

    def _find_similar_fields(self, field_catalog, field_analysis):
        patterns = [
            (r"Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax"]),
            (r"NetIncome", ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLossAttributableToParent"]),
            (r"^Assets$", ["AssetsCurrent", "AssetsNoncurrent"]),
            (r"Cash", ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
            (r"Debt", ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "DebtInstrumentCarryingAmount"]),
            (r"SharesOutstanding", ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"])
        ]
        
        groups = []
        for name, fields in patterns:
            matches = []
            for f in fields:
                if f in field_catalog:
                    matches.append({
                        "field_name": f,
                        "label": field_catalog[f].get("label", ""),
                        "availability": field_analysis.get(f, {}).get("availability_percentage", 0)
                    })
            if len(matches) > 1:
                groups.append({"concept": name, "fields": matches})
        return groups

    def _create_consolidation_rules(self, groups, priority_map):
        rules = []
        for group in groups:
            fields_ranked = sorted(
                [(f["field_name"], priority_map.get(f["field_name"], {}).get("priority_score", 0), f) for f in group["fields"]],
                key=lambda x: -x[1]
            )
            if fields_ranked:
                primary = fields_ranked[0][2]
                rules.append({
                    "concept": group["concept"],
                    "primary_field": primary["field_name"],
                    "primary_availability": primary["availability"],
                    "strategy": "Use primary field; fallback to alternatives in availability order"
                })
        return rules

if __name__ == "__main__":
    pipeline = FieldAnalysisPipeline()
    pipeline.run()
