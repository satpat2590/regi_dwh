import json
import os
from collections import defaultdict
import re
from difflib import SequenceMatcher

def analyze_field_standardization():
    """
    Task #4: Field Standardization Rules
    
    Handle variations and inconsistencies in field reporting:
    - Identify synonymous fields reported differently
    - Map deprecated fields to current standards
    - Define consolidation rules for related fields
    - Document unit handling (USD vs shares vs pure numbers)
    
    Output: field_mapping.json, field_priority.json
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    catalog_path = os.path.join(base_dir, "field_catalog.json")
    categories_path = os.path.join(base_dir, "field_categories.json")
    availability_path = os.path.join(base_dir, "field_availability_report.json")
    
    # Load data
    with open(catalog_path, 'r') as f:
        field_catalog = json.load(f)
    
    with open(categories_path, 'r') as f:
        field_categories = json.load(f)
    
    with open(availability_path, 'r') as f:
        availability_report = json.load(f)
    
    print(f"Analyzing field standardization for {len(field_catalog)} fields...\n")
    
    # 1. Identify deprecated fields
    deprecated_fields = identify_deprecated_fields(field_catalog)
    
    # 2. Find similar field names (potential synonyms)
    similar_fields = find_similar_fields(field_catalog, field_categories, availability_report)
    
    # 3. Identify GAAP vs IFRS equivalents
    gaap_ifrs_mappings = identify_gaap_ifrs_mappings(field_catalog, field_categories)
    
    # 4. Create priority mapping (which field to prefer when multiple options exist)
    field_priority = create_field_priority(field_catalog, availability_report, deprecated_fields)
    
    # 5. Identify unit types
    unit_classifications = classify_field_units(field_catalog, field_categories)
    
    # Create standardization rules
    standardization_rules = {
        "deprecated_fields": deprecated_fields,
        "similar_field_groups": similar_fields,
        "gaap_ifrs_mappings": gaap_ifrs_mappings,
        "unit_classifications": unit_classifications,
        "consolidation_recommendations": create_consolidation_rules(similar_fields, field_priority)
    }
    
    # Save outputs
    mapping_path = os.path.join(base_dir, "field_mapping.json")
    priority_path = os.path.join(base_dir, "field_priority.json")
    
    with open(mapping_path, 'w') as f:
        json.dump(standardization_rules, f, indent=2)
    
    with open(priority_path, 'w') as f:
        json.dump(field_priority, f, indent=2)
    
    # Print summary
    print_summary(standardization_rules, field_priority)
    
    print(f"\n✓ Field mapping saved to {mapping_path}")
    print(f"✓ Field priority saved to {priority_path}")

def identify_deprecated_fields(field_catalog):
    """Find fields marked as deprecated"""
    deprecated = []
    
    for field_name, field_info in field_catalog.items():
        label = field_info.get("label", "")
        description = field_info.get("description", "")
        
        # Check for deprecation markers
        if "deprecated" in label.lower() or "deprecated" in description.lower():
            # Extract deprecation date if available
            deprecation_match = re.search(r'Deprecated (\d{4}-\d{2}-\d{2})', description)
            deprecation_date = deprecation_match.group(1) if deprecation_match else None
            
            deprecated.append({
                "field_name": field_name,
                "label": label,
                "deprecation_date": deprecation_date,
                "taxonomy": field_info.get("taxonomy", ""),
                "companies_using": field_info.get("companies_using", [])
            })
    
    return deprecated

def find_similar_fields(field_catalog, field_categories, availability_report):
    """Find fields with similar names that might be synonymous"""
    similar_groups = []
    field_analysis = availability_report["field_analysis"]
    
    # Group fields by semantic similarity
    # Focus on high-value fields (universal/very_common)
    high_value_fields = [
        field for field, info in field_analysis.items()
        if info["availability_tier"] in ["universal", "very_common", "common"]
    ]
    
    # Common patterns to look for
    patterns = [
        # Revenue variations
        (r"Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", 
                      "RevenueFromContractWithCustomerIncludingAssessedTax"]),
        # Net Income variations
        (r"NetIncome", ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic",
                        "NetIncomeLossAttributableToParent"]),
        # Assets variations
        (r"^Assets$", ["AssetsCurrent", "AssetsNoncurrent"]),
        # Cash variations
        (r"Cash", ["CashAndCashEquivalentsAtCarryingValue", 
                   "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
        # Debt variations
        (r"Debt", ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent",
                   "DebtInstrumentCarryingAmount"]),
        # Shares variations
        (r"SharesOutstanding", ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding",
                                "WeightedAverageNumberOfSharesOutstandingBasic"])
    ]
    
    for pattern_name, field_list in patterns:
        matching_fields = []
        for field in field_list:
            if field in field_catalog:
                matching_fields.append({
                    "field_name": field,
                    "label": field_catalog[field].get("label", ""),
                    "availability": field_analysis.get(field, {}).get("availability_percentage", 0),
                    "companies_using": field_catalog[field].get("companies_using", []),
                    "taxonomy": field_catalog[field].get("taxonomy", "")
                })
        
        if len(matching_fields) > 1:
            similar_groups.append({
                "concept": pattern_name,
                "fields": matching_fields,
                "recommendation": "Choose highest availability field as standard"
            })
    
    return similar_groups

def identify_gaap_ifrs_mappings(field_catalog, field_categories):
    """Identify equivalent fields between US-GAAP and IFRS"""
    gaap_fields = {}
    ifrs_fields = {}
    
    for field_name, field_info in field_catalog.items():
        taxonomy = field_info.get("taxonomy", "")
        if taxonomy == "us-gaap":
            gaap_fields[field_name] = field_info
        elif taxonomy == "ifrs-full":
            ifrs_fields[field_name] = field_info
    
    # Find potential mappings based on similar concepts
    mappings = []
    
    # Common mappings we know about
    known_mappings = [
        ("Assets", "Assets"),  # Same name, different taxonomy
        ("Liabilities", "Liabilities"),
        ("Equity", "Equity"),
        ("Revenue", "Revenue"),
        ("NetIncomeLoss", "ProfitLoss"),
    ]
    
    for gaap_field, ifrs_field in known_mappings:
        if gaap_field in gaap_fields and ifrs_field in ifrs_fields:
            mappings.append({
                "us_gaap_field": gaap_field,
                "ifrs_field": ifrs_field,
                "mapping_confidence": "high",
                "note": "Standard equivalent"
            })
    
    return mappings

def create_field_priority(field_catalog, availability_report, deprecated_fields):
    """Create priority ranking for fields"""
    field_analysis = availability_report["field_analysis"]
    deprecated_names = {f["field_name"] for f in deprecated_fields}
    
    priority_map = {}
    
    for field_name, field_info in field_catalog.items():
        analysis = field_analysis.get(field_name, {})
        
        # Calculate priority score
        score = 0
        
        # Availability (0-100 points)
        score += analysis.get("availability_percentage", 0)
        
        # Critical field bonus (50 points)
        if analysis.get("is_critical", False):
            score += 50
        
        # Universal/very common tier bonus (25 points)
        tier = analysis.get("availability_tier", "")
        if tier == "universal":
            score += 25
        elif tier == "very_common":
            score += 15
        
        # Deprecated penalty (-100 points)
        if field_name in deprecated_names:
            score -= 100
        
        # US-GAAP preference (slight bonus, 5 points)
        if field_info.get("taxonomy") == "us-gaap":
            score += 5
        
        priority_map[field_name] = {
            "priority_score": round(score, 1),
            "availability_percentage": analysis.get("availability_percentage", 0),
            "is_critical": analysis.get("is_critical", False),
            "tier": tier,
            "is_deprecated": field_name in deprecated_names,
            "taxonomy": field_info.get("taxonomy", ""),
            "label": field_info.get("label", "")
        }
    
    # Sort by priority score
    sorted_priority = dict(sorted(priority_map.items(), key=lambda x: -x[1]["priority_score"]))
    
    return sorted_priority

def classify_field_units(field_catalog, field_categories):
    """Classify fields by their unit types"""
    unit_types = {
        "monetary": [],      # USD, currency
        "shares": [],        # Share counts
        "per_share": [],     # Per-share metrics
        "percentage": [],    # Rates, ratios
        "pure_number": [],   # Counts, quantities
        "other": []
    }
    
    for field_name, field_info in field_catalog.items():
        label = field_info.get("label", "").lower()
        description = field_info.get("description", "").lower()
        category = field_categories.get(field_name, {})
        
        # Classify based on patterns
        if "per share" in label or "pershare" in field_name.lower():
            unit_types["per_share"].append(field_name)
        elif "shares" in label or "stock" in label:
            unit_types["shares"].append(field_name)
        elif "percent" in label or "rate" in label or "ratio" in label:
            unit_types["percentage"].append(field_name)
        elif any(x in label for x in ["amount", "value", "expense", "income", "revenue", "assets", "liabilities"]):
            unit_types["monetary"].append(field_name)
        else:
            unit_types["other"].append(field_name)
    
    # Return counts and examples
    return {
        unit_type: {
            "count": len(fields),
            "examples": fields[:10]
        }
        for unit_type, fields in unit_types.items()
    }

def create_consolidation_rules(similar_groups, field_priority):
    """Create rules for consolidating similar fields"""
    rules = []
    
    for group in similar_groups:
        # Find the highest priority field in the group
        fields_with_priority = []
        for field_info in group["fields"]:
            field_name = field_info["field_name"]
            priority = field_priority.get(field_name, {}).get("priority_score", 0)
            fields_with_priority.append((field_name, priority, field_info))
        
        # Sort by priority
        fields_with_priority.sort(key=lambda x: -x[1])
        
        if fields_with_priority:
            primary_field = fields_with_priority[0][2]
            alternative_fields = [f[2] for f in fields_with_priority[1:]]
            
            rules.append({
                "concept": group["concept"],
                "primary_field": primary_field["field_name"],
                "primary_label": primary_field["label"],
                "primary_availability": primary_field["availability"],
                "alternative_fields": [
                    {
                        "field_name": f["field_name"],
                        "label": f["label"],
                        "availability": f["availability"]
                    }
                    for f in alternative_fields
                ],
                "consolidation_strategy": "Use primary field; fallback to alternatives in order of availability"
            })
    
    return rules

def print_summary(standardization_rules, field_priority):
    print("="*70)
    print("FIELD STANDARDIZATION ANALYSIS SUMMARY")
    print("="*70)
    
    # Deprecated fields
    deprecated = standardization_rules["deprecated_fields"]
    print(f"\nDeprecated Fields: {len(deprecated)}")
    if deprecated:
        print(f"  Examples:")
        for field in deprecated[:5]:
            print(f"    • {field['field_name']} (deprecated {field['deprecation_date'] or 'unknown date'})")
    
    # Similar field groups
    similar = standardization_rules["similar_field_groups"]
    print(f"\nSimilar Field Groups: {len(similar)}")
    for group in similar:
        print(f"\n  {group['concept']}:")
        for field in group['fields']:
            print(f"    • {field['field_name']} ({field['availability']}% availability)")
    
    # GAAP/IFRS mappings
    mappings = standardization_rules["gaap_ifrs_mappings"]
    print(f"\nGAAP/IFRS Mappings: {len(mappings)}")
    for mapping in mappings[:5]:
        print(f"  • {mapping['us_gaap_field']} (US-GAAP) ↔ {mapping['ifrs_field']} (IFRS)")
    
    # Unit classifications
    units = standardization_rules["unit_classifications"]
    print(f"\nUnit Classifications:")
    for unit_type, info in units.items():
        print(f"  {unit_type}: {info['count']} fields")
    
    # Top priority fields
    print(f"\nTop 15 Priority Fields (for standardization):")
    top_fields = list(field_priority.items())[:15]
    for field_name, info in top_fields:
        print(f"  • {field_name} (score: {info['priority_score']}, {info['availability_percentage']}% avail)")
    
    # Consolidation rules
    consolidation = standardization_rules["consolidation_recommendations"]
    print(f"\nConsolidation Rules: {len(consolidation)}")

if __name__ == "__main__":
    analyze_field_standardization()
