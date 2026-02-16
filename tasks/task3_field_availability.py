import json
import os
from collections import defaultdict

def analyze_field_availability():
    """
    Task #3: Field Availability Analysis
    
    Understand which fields are consistently available across companies:
    - Calculate availability rate: What % of companies report each field?
    - Identify industry-specific fields vs universal fields
    - Find fields with sparse data (only a few companies report them)
    - Check temporal consistency (do companies report this field every quarter?)
    
    Output: field_availability_report.json
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    catalog_path = os.path.join(base_dir, "field_catalog.json")
    categories_path = os.path.join(base_dir, "field_categories.json")
    metadata_path = os.path.join(base_dir, "field_catalog_metadata.json")
    
    # Load data
    with open(catalog_path, 'r') as f:
        field_catalog = json.load(f)
    
    with open(categories_path, 'r') as f:
        field_categories = json.load(f)
    
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    
    total_companies = metadata["total_companies"]
    all_tickers = metadata["tickers_analyzed"]
    
    print(f"Analyzing field availability across {total_companies} companies...")
    print(f"Total fields: {len(field_catalog)}\n")
    
    # Categorize fields by availability
    availability_tiers = {
        "universal": [],      # 90-100% of companies
        "very_common": [],    # 70-89% of companies
        "common": [],         # 50-69% of companies
        "moderate": [],       # 30-49% of companies
        "rare": [],           # 10-29% of companies
        "very_rare": []       # <10% of companies
    }
    
    # Load sector mapping from enrichment data
    company_metadata_path = os.path.join(os.path.dirname(base_dir), "config", "company_metadata.json")
    ticker_to_sector = {}
    try:
        with open(company_metadata_path, 'r') as f:
            company_metadata = json.load(f)
        for ticker, meta in company_metadata.items():
            ticker_to_sector[ticker] = meta.get("sector", "Unknown")
    except FileNotFoundError:
        print("Warning: config/company_metadata.json not found. Run enrich.py first. Using empty sector map.")

    
    # Analyze each field
    field_analysis = {}
    
    for field_name, field_info in field_catalog.items():
        count = field_info["count"]
        companies_using = field_info["companies_using"]
        availability_pct = (count / total_companies) * 100
        
        # Get category info
        category_info = field_categories.get(field_name, {})
        
        # Determine availability tier
        if availability_pct >= 90:
            tier = "universal"
        elif availability_pct >= 70:
            tier = "very_common"
        elif availability_pct >= 50:
            tier = "common"
        elif availability_pct >= 30:
            tier = "moderate"
        elif availability_pct >= 10:
            tier = "rare"
        else:
            tier = "very_rare"
        
        availability_tiers[tier].append(field_name)
        
        # Analyze sector distribution
        sector_distribution = defaultdict(int)
        for ticker in companies_using:
            sector = ticker_to_sector.get(ticker, "Unknown")
            sector_distribution[sector] += 1
        
        # Determine if field is sector-specific
        is_sector_specific = False
        dominant_sector = None
        if sector_distribution:
            max_sector = max(sector_distribution.items(), key=lambda x: x[1])
            dominant_sector = max_sector[0]
            # If one sector has >80% of the companies using this field
            if max_sector[1] / count > 0.8 and count >= 3:
                is_sector_specific = True
        
        field_analysis[field_name] = {
            "availability_count": count,
            "availability_percentage": round(availability_pct, 1),
            "availability_tier": tier,
            "companies_using": companies_using,
            "sector_distribution": dict(sector_distribution),
            "is_sector_specific": is_sector_specific,
            "dominant_sector": dominant_sector if is_sector_specific else None,
            "statement_type": category_info.get("statement_type", "Unknown"),
            "temporal_nature": category_info.get("temporal_nature", "Unknown"),
            "is_critical": category_info.get("is_critical", False),
            "accounting_concept": category_info.get("accounting_concept", []),
            "taxonomy": field_info.get("taxonomy", ""),
            "label": field_info.get("label", "")
        }
    
    # Generate summary statistics
    summary = {
        "total_companies_analyzed": total_companies,
        "total_unique_fields": len(field_catalog),
        "availability_tiers": {
            tier: {
                "count": len(fields),
                "percentage": round((len(fields) / len(field_catalog)) * 100, 1),
                "description": get_tier_description(tier)
            }
            for tier, fields in availability_tiers.items()
        },
        "sector_specific_fields": sum(1 for f in field_analysis.values() if f["is_sector_specific"]),
        "critical_universal_fields": [
            field for field, info in field_analysis.items()
            if info["is_critical"] and info["availability_tier"] in ["universal", "very_common"]
        ]
    }
    
    # Sector-specific analysis
    sector_specific_breakdown = defaultdict(list)
    for field_name, info in field_analysis.items():
        if info["is_sector_specific"]:
            sector_specific_breakdown[info["dominant_sector"]].append({
                "field": field_name,
                "label": info["label"],
                "count": info["availability_count"]
            })
    
    summary["sector_specific_breakdown"] = dict(sector_specific_breakdown)
    
    # Save results
    output = {
        "summary": summary,
        "field_analysis": field_analysis
    }
    
    output_path = os.path.join(base_dir, "field_availability_report.json")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    # Print summary
    print_summary(summary, availability_tiers, sector_specific_breakdown)
    
    print(f"\n✓ Field availability report saved to {output_path}")

def get_tier_description(tier):
    descriptions = {
        "universal": "90-100% of companies (highly reliable for cross-company analysis)",
        "very_common": "70-89% of companies (good for most comparisons)",
        "common": "50-69% of companies (useful but may have gaps)",
        "moderate": "30-49% of companies (limited coverage)",
        "rare": "10-29% of companies (sparse data)",
        "very_rare": "<10% of companies (company-specific or niche)"
    }
    return descriptions.get(tier, "Unknown")

def print_summary(summary, availability_tiers, sector_specific_breakdown):
    print("="*70)
    print("FIELD AVAILABILITY ANALYSIS SUMMARY")
    print("="*70)
    
    print(f"\nTotal Companies: {summary['total_companies_analyzed']}")
    print(f"Total Unique Fields: {summary['total_unique_fields']}")
    
    print("\n" + "="*70)
    print("AVAILABILITY TIERS")
    print("="*70)
    
    for tier in ["universal", "very_common", "common", "moderate", "rare", "very_rare"]:
        tier_info = summary["availability_tiers"][tier]
        print(f"\n{tier.upper().replace('_', ' ')}:")
        print(f"  {tier_info['count']} fields ({tier_info['percentage']}%)")
        print(f"  {tier_info['description']}")
        
        # Show examples for universal and very_common
        if tier in ["universal", "very_common"] and availability_tiers[tier]:
            examples = availability_tiers[tier][:5]
            print(f"  Examples: {', '.join(examples[:3])}")
    
    print("\n" + "="*70)
    print("CRITICAL UNIVERSAL FIELDS")
    print("="*70)
    critical_universal = summary["critical_universal_fields"]
    print(f"\n{len(critical_universal)} critical fields with high availability (90%+):")
    for field in critical_universal[:15]:
        print(f"  • {field}")
    if len(critical_universal) > 15:
        print(f"  ... and {len(critical_universal) - 15} more")
    
    print("\n" + "="*70)
    print("SECTOR-SPECIFIC FIELDS")
    print("="*70)
    print(f"\nTotal sector-specific fields: {summary['sector_specific_fields']}")
    
    for sector, fields in sorted(sector_specific_breakdown.items(), key=lambda x: -len(x[1])):
        print(f"\n{sector}: {len(fields)} sector-specific fields")
        for field_info in fields[:3]:
            print(f"  • {field_info['field']} ({field_info['count']} companies)")

if __name__ == "__main__":
    analyze_field_availability()
