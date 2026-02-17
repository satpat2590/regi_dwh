import json
import os
import re
from pathlib import Path
from collections import defaultdict

def categorize_fields():
    """
    Task #2: Field Categorization & Mapping
    Organize fields into meaningful categories for analysis.
    
    Categories:
    1. Financial Statement Type (Balance Sheet, Income Statement, Cash Flow, Footnotes)
    2. Temporal Nature (Point-in-time vs Period metrics)
    3. Accounting Concept (Revenue, Expense, Asset, Liability, Equity, etc.)
    4. Critical for fundamental analysis
    5. Special handling required
    
    Output: field_categories.json
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = str(Path(base_dir).parent.parent.parent)
    catalog_path = os.path.join(root_dir, "reports/field_catalog.json")
    
    with open(catalog_path, 'r') as f:
        field_catalog = json.load(f)
    
    print(f"Categorizing {len(field_catalog)} fields...\n")
    
    # Initialize categorization structure
    field_categories = {}
    
    for field_name, field_info in field_catalog.items():
        label = (field_info.get("label") or "").lower()
        description = (field_info.get("description") or "").lower()
        full_text = f"{field_name.lower()} {label} {description}"
        
        category = {
            "field_name": field_name,
            "label": field_info.get("label", ""),
            "taxonomy": field_info.get("taxonomy", ""),
            "statement_type": categorize_statement_type(field_name, label, description),
            "temporal_nature": categorize_temporal_nature(field_name, label, description),
            "accounting_concept": categorize_accounting_concept(field_name, label, description),
            "is_critical": is_critical_field(field_name, label),
            "special_handling": identify_special_handling(field_name, label, description),
            "companies_using": field_info.get("companies_using", []),
            "count": field_info.get("count", 0)
        }
        
        field_categories[field_name] = category
    
    # Save categorized data
    output_path = os.path.join(root_dir, "reports/field_categories.json")
    with open(output_path, 'w') as f:
        json.dump(field_categories, f, indent=2)
    
    # Generate summary statistics
    print_summary(field_categories)
    
    print(f"\n✓ Field categories saved to {output_path}")

def categorize_statement_type(field_name, label, description):
    """Categorize by financial statement type"""
    field_lower = field_name.lower()
    text = f"{field_lower} {label} {description}"
    
    # Balance Sheet indicators
    balance_sheet_keywords = [
        'assets', 'liabilities', 'equity', 'stockholders', 'shareholders',
        'payable', 'receivable', 'inventory', 'property', 'plant', 'equipment',
        'goodwill', 'intangible', 'investment', 'debt', 'capital',
        'retained', 'accumulated', 'deferred', 'prepaid', 'accrued'
    ]
    
    # Income Statement indicators
    income_statement_keywords = [
        'revenue', 'sales', 'income', 'earnings', 'profit', 'loss',
        'expense', 'cost', 'margin', 'ebitda', 'ebit', 'operating',
        'gross', 'tax expense', 'interest expense', 'depreciation', 'amortization'
    ]
    
    # Cash Flow indicators
    cash_flow_keywords = [
        'cash flow', 'operating activities', 'investing activities',
        'financing activities', 'proceeds from', 'payments for',
        'purchase of', 'sale of', 'issuance', 'repayment'
    ]
    
    # Equity/Stockholders Equity indicators
    equity_keywords = [
        'common stock', 'preferred stock', 'treasury stock',
        'additional paid', 'dividends', 'shares issued', 'shares outstanding'
    ]
    
    # Check for statement type
    if any(keyword in text for keyword in cash_flow_keywords):
        return "Cash Flow Statement"
    elif any(keyword in text for keyword in income_statement_keywords):
        # Check if it's not a balance sheet item that happens to mention income
        if not any(keyword in text for keyword in ['deferred', 'payable', 'receivable', 'asset', 'liability']):
            return "Income Statement"
    
    if any(keyword in text for keyword in equity_keywords):
        return "Balance Sheet - Equity"
    elif any(keyword in text for keyword in balance_sheet_keywords):
        if 'asset' in text:
            return "Balance Sheet - Assets"
        elif 'liability' in text or 'payable' in text:
            return "Balance Sheet - Liabilities"
        else:
            return "Balance Sheet"
    
    # Document and Entity Information
    if 'entity' in text or 'document' in text or field_name.startswith('Entity'):
        return "Document & Entity Information"
    
    return "Other/Footnotes"

def categorize_temporal_nature(field_name, label, description):
    """Determine if metric is point-in-time or period-based"""
    field_lower = field_name.lower()
    text = f"{field_lower} {label} {description}"
    
    # Point-in-time indicators (balance sheet items)
    point_in_time_keywords = [
        'balance sheet', 'as of', 'carrying value', 'carrying amount',
        'outstanding', 'issued', 'authorized'
    ]
    
    # Period indicators (income statement, cash flow)
    period_keywords = [
        'for the period', 'during the period', 'revenue', 'expense',
        'income', 'loss', 'flow', 'proceeds', 'payments',
        'increase', 'decrease', 'change'
    ]
    
    # Balance sheet items are generally point-in-time
    if any(keyword in text for keyword in ['asset', 'liability', 'equity', 'stock', 'debt']):
        if not any(keyword in text for keyword in period_keywords):
            return "Point-in-Time"
    
    # Income and cash flow items are period-based
    if any(keyword in text for keyword in period_keywords):
        return "Period"
    
    # Check field name patterns
    if any(x in field_lower for x in ['shares', 'stock', 'balance', 'carrying', 'fair value']):
        return "Point-in-Time"
    
    return "Period"

def categorize_accounting_concept(field_name, label, description):
    """Categorize by accounting concept"""
    field_lower = field_name.lower()
    text = f"{field_lower} {label} {description}"
    
    concepts = []
    
    # Revenue concepts
    if any(x in text for x in ['revenue', 'sales', 'contract with customer']):
        concepts.append("Revenue")
    
    # Expense concepts
    if any(x in text for x in ['expense', 'cost of', 'depreciation', 'amortization']):
        concepts.append("Expense")
    
    # Asset concepts
    if any(x in text for x in ['asset', 'receivable', 'inventory', 'property', 'equipment', 'investment', 'goodwill', 'intangible']):
        concepts.append("Asset")
    
    # Liability concepts
    if any(x in text for x in ['liability', 'payable', 'debt', 'obligation', 'deferred revenue']):
        concepts.append("Liability")
    
    # Equity concepts
    if any(x in text for x in ['equity', 'stock', 'capital', 'retained earnings', 'dividend']):
        concepts.append("Equity")
    
    # Cash concepts
    if any(x in text for x in ['cash', 'cash flow']):
        concepts.append("Cash")
    
    # Tax concepts
    if any(x in text for x in ['tax', 'income tax']):
        concepts.append("Tax")
    
    # Share-based compensation
    if any(x in text for x in ['share-based', 'stock option', 'restricted stock']):
        concepts.append("Share-Based Compensation")
    
    # Earnings per share
    if any(x in text for x in ['earnings per share', 'eps']):
        concepts.append("Earnings Per Share")
    
    return concepts if concepts else ["Other"]

def is_critical_field(field_name, label):
    """Identify fields critical for fundamental analysis"""
    critical_patterns = [
        # Core financial metrics
        r'Revenue', r'Sales', r'NetIncome', r'EarningsPerShare',
        r'TotalAssets', r'TotalLiabilities', r'StockholdersEquity',
        r'CashAndCashEquivalents', r'OperatingCashFlow',
        r'FreeCashFlow', r'GrossProfit', r'OperatingIncome',
        
        # Key balance sheet items
        r'AccountsReceivable', r'Inventory', r'AccountsPayable',
        r'Debt', r'CommonStock',
        
        # Important metrics
        r'SharesOutstanding', r'SharesIssued'
    ]
    
    for pattern in critical_patterns:
        if re.search(pattern, field_name, re.IGNORECASE):
            return True
    
    return False

def identify_special_handling(field_name, label, description):
    """Identify fields requiring special handling"""
    special = []
    
    text = f"{field_name.lower()} {label} {description}"
    
    # Per-share metrics
    if 'per share' in text or 'pershare' in field_name.lower():
        special.append("Per-Share Metric")
    
    # Ratios
    if 'ratio' in text or 'rate' in text:
        special.append("Ratio/Rate")
    
    # Fair value measurements
    if 'fair value' in text:
        special.append("Fair Value")
    
    # Accumulated/Cumulative
    if 'accumulated' in text or 'cumulative' in text:
        special.append("Accumulated/Cumulative")
    
    # Deferred items
    if 'deferred' in text:
        special.append("Deferred")
    
    # Foreign currency
    if 'foreign' in text or 'currency' in text or 'exchange' in text:
        special.append("Foreign Currency")
    
    # Share-based compensation
    if 'share-based' in text or 'stock option' in text:
        special.append("Share-Based Compensation")
    
    # Discontinued operations
    if 'discontinued' in text:
        special.append("Discontinued Operations")
    
    return special if special else ["Standard"]

def print_summary(field_categories):
    """Print summary statistics"""
    print("="*70)
    print("FIELD CATEGORIZATION SUMMARY")
    print("="*70)
    
    # Statement type breakdown
    statement_types = defaultdict(int)
    for field_data in field_categories.values():
        statement_types[field_data["statement_type"]] += 1
    
    print("\nBy Statement Type:")
    for stmt_type, count in sorted(statement_types.items(), key=lambda x: -x[1]):
        print(f"  {stmt_type}: {count}")
    
    # Temporal nature
    temporal = defaultdict(int)
    for field_data in field_categories.values():
        temporal[field_data["temporal_nature"]] += 1
    
    print("\nBy Temporal Nature:")
    for temp_type, count in sorted(temporal.items(), key=lambda x: -x[1]):
        print(f"  {temp_type}: {count}")
    
    # Critical fields
    critical_count = sum(1 for f in field_categories.values() if f["is_critical"])
    print(f"\nCritical Fields for Fundamental Analysis: {critical_count}")
    
    # Accounting concepts
    concept_counts = defaultdict(int)
    for field_data in field_categories.values():
        for concept in field_data["accounting_concept"]:
            concept_counts[concept] += 1
    
    print("\nBy Accounting Concept (top 10):")
    for concept, count in sorted(concept_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {concept}: {count}")
    
    # Special handling
    special_counts = defaultdict(int)
    for field_data in field_categories.values():
        for special in field_data["special_handling"]:
            if special != "Standard":
                special_counts[special] += 1
    
    if special_counts:
        print("\nFields Requiring Special Handling:")
        for special, count in sorted(special_counts.items(), key=lambda x: -x[1]):
            print(f"  {special}: {count}")

if __name__ == "__main__":
    categorize_fields()
