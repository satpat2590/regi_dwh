# Task #2 Summary: Fiscal Year End Cataloging

## Overview
Successfully extracted fiscal year end (FYE) metadata for 21 target companies by analyzing historica annual filing dates (10-K, 20-F, 40-F).

## Output File
**`fiscal_year_metadata.json`** - Contains FYE month, confidence score, and filing provenance for each ticker.

## Key Findings

### 1. Fiscal Calendar Diversity
Most companies (15/21) follow the calendar year (December FYE), but significant deviations exist in Retail and Tech sectors.

| Ticker | Sector | FYE Month | Confidence | Note |
|--------|--------|-----------|------------|------|
| **MSFT** | Tech | June | High | Ends June 30 |
| **AAPL** | Tech | September | High | Ends late Sep (floating) |
| **NVDA** | Tech | January | High | Ends late Jan |
| **WMT** | Retail | January | High | Ends Jan 31 |
| **COST** | Retail | August | Medium | Ends late Aug/early Sep |
| **JNJ** | Healthcare | January/Dec | Medium | Floating (closest Sunday to Jan 1) |

### 2. Edge Case Analysis: JNJ (Johnson & Johnson)
- **Result**: "January" (Medium Confidence, 51.4%)
- **Reason**: JNJ uses a 52/53 week fiscal year ending on the Sunday closest to Jan 1st.
- **Impact**: End dates fluctuate between late Dec and early Jan.
- **Resolution**: For modeling, treat as **December 31** aligned, but expect variations in exact days.

### 3. International Filings
- **GOLD (Barrick)**: Canadian, files **40-F**. FYE: December.
- **VALE**: Brazilian, files **20-F**. FYE: December.
- **Processing**: Script successfully handled `40-F` and `20-F` forms alongside domestic `10-K`.

## Implication for Point-in-Time Mapping (Task #3)
The diversity in FYE means we cannot assume `Year-12-31` for annual data.
- **Action**: Must use the specific `end` date from the `fiscal_year_metadata.json` (or the specific filing) to align trailing metrics correctly.
- **Normalization**: Will need to map "Period 2024" to different actual dates depending on the company:
    - PLTR 2024 -> Dec 31, 2024
    - AAPL 2024 -> Sep 28, 2024
    - NVDA 2024 -> Jan 26, 2025 (often called "Fiscal 2025")

## Next Steps
Proceed to **Task #3: Implement Point-in-Time Calendar Mapping**, which will utilize these FYE anchors to build the historical timeline.
