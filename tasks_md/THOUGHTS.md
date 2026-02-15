# Thoughts on Field Identification from CompanyFacts Endpoint

## Current State Analysis

Looking at `SEC.py:88-103`, the `Field` column is populated from the EDGAR CompanyFacts API. These fields represent XBRL taxonomy concepts (primarily US-GAAP accounting standards).

### Data Structure
```
facts (dict)
  └── taxonomy (e.g., "us-gaap", "dei", "ifrs-full")
      └── field_name (e.g., "Revenue", "Assets", "AccountsPayable")
          └── metadata (label, description, units)
```

## Gap Analysis: What's Missing?

Currently, `SEC.py:49-50` only pulls data for 3 tickers: `['PLTR', 'AXTI', 'GOLD']`. This small sample won't reveal the full universe of field names across different industries and company types.

### Issues to Address:

1. **Limited Sample Size**: 3 companies won't capture industry-specific fields
   - Tech companies report different metrics than retailers
   - Financial institutions have unique regulatory fields
   - Each industry has specialized GAAP concepts

2. **No Field Cataloging**: Currently the data goes straight to Excel with no aggregation
   - No deduplication of field names
   - No frequency analysis (which fields appear most often)
   - No taxonomy breakdown (us-gaap vs dei vs company-specific)

3. **No Field Metadata Storage**: The API provides `label` and `description` (lines 91-94, currently commented out)
   - These would help understand what each field represents
   - Critical for later deciding which fields to use in models

4. **No Field Prioritization**: Not all ~1000+ GAAP concepts are useful for trading
   - Need to identify core fundamental metrics (Revenue, EPS, FCF, etc.)
   - Distinguish between balance sheet, income statement, and cash flow fields
   - Filter out obscure/rarely-used concepts

## Recommended Additional Tasks

### Task A: Field Discovery & Cataloging
**Purpose**: Build a comprehensive catalog of all XBRL fields across a representative sample of companies

**Actions**:
- Expand ticker list to 50-100 companies across major sectors (Tech, Finance, Retail, Healthcare, Energy, etc.)
- Run `fetch_sec_filing()` for all tickers
- Collect all unique field names with their taxonomy source
- Store field metadata (label, description) from API
- Output a master catalog: `{field_name: {taxonomy, label, description, count, companies_using}}`

**Why This Matters**: You can't normalize what you don't know exists. Different companies report different fields.

### Task B: Field Categorization & Mapping
**Purpose**: Organize fields into meaningful categories for analysis

**Actions**:
- Group fields by financial statement type (Balance Sheet, Income Statement, Cash Flow, Footnotes)
- Identify temporal nature (Point-in-time vs Period metrics)
- Tag fields by accounting concept (Revenue, Expense, Asset, Liability, Equity, etc.)
- Mark critical fields for fundamental analysis (e.g., Revenue, NetIncome, TotalAssets, etc.)
- Identify fields that require special handling (per-share metrics, ratios, etc.)

**Why This Matters**: Not all fields are equal. You need to know which ones matter for trading models.

### Task C: Field Availability Analysis
**Purpose**: Understand which fields are consistently available across companies

**Actions**:
- Calculate availability rate: What % of companies report each field?
- Identify industry-specific fields vs universal fields
- Find fields with sparse data (only a few companies report them)
- Check temporal consistency (do companies report this field every quarter?)

**Why This Matters**: Your models can only use fields that are reliably available. Sparse fields cause data quality issues.

### Task D: Field Standardization Rules
**Purpose**: Handle variations and inconsistencies in field reporting

**Actions**:
- Identify synonymous fields reported differently (e.g., "Revenues" vs "RevenueFromContractWithCustomerExcludingAssessedTax")
- Map deprecated fields to current standards
- Define consolidation rules for related fields
- Document unit handling (USD vs shares vs pure numbers)

**Why This Matters**: XBRL allows companies to use different tags for the same concept. You need mapping rules.

## Integration with Existing Tasks

These field identification tasks should occur **before** the existing normalization tasks:

**Proposed Sequence**:
1. **Task A** (Field Discovery) ← **Do this first**
2. **Task B** (Field Categorization) ← **Then this**
3. **Task C** (Field Availability Analysis) ← **Validate what's usable**
4. **Task D** (Field Standardization Rules) ← **Define how to handle variations**
5. Task #1 (Catalog Fiscal Year Ends) ← **Now ready for normalization**
6. Task #2 (Point-in-Time Mapping)
7. Task #3 (Trailing Metrics)

## Technical Considerations

### Current Code Modifications Needed:
- `SEC.py:49`: Expand ticker list significantly
- `SEC.py:91-94`: Uncomment and store label/description metadata
- Add a new method: `catalog_all_fields()` to aggregate field data
- Add field frequency tracking in `clean_facts()`

### Data Storage:
- Create `field_catalog.json` with complete field metadata
- Create `field_mapping.json` for standardization rules
- Create `field_priority.json` listing core fundamental metrics

### Performance Note:
The SEC rate limits requests to 10/second. For 100 companies, expect ~10+ seconds of API calls. Add proper rate limiting in `RequestSession`.

## Questions to Consider

1. **Scope**: How many companies define "comprehensive"?
   - S&P 500 would be thorough but takes time
   - Representative sample of 50-100 across sectors is practical

2. **Maintenance**: Fields can change as GAAP evolves
   - How often to refresh the field catalog?
   - How to handle new fields appearing?

3. **Prioritization**: Which fields are must-haves vs nice-to-haves?
   - Start with core income statement and balance sheet items
   - Expand to cash flow and detailed metrics later

4. **Field Versioning**: XBRL taxonomy versions change
   - Some fields get renamed or deprecated
   - Need strategy for handling historical data with old field names

## Recommendation

**Yes, you absolutely need field identification tasks before normalization.** You're currently operating blind - you don't know what fields exist, which ones matter, or how consistently they're reported.

Add Tasks A-D as prerequisites to your current Task #1. The time invested in field discovery will save significant rework later when you realize critical fields are missing or inconsistently named.
