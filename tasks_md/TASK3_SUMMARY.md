# Task #3 Summary: Point-in-Time Calendar Mapping

## Overview
Built a Point-in-Time (PIT) mapping system to prevent look-ahead bias in backtesting. This maps every fiscal period to its actual public filing date.

## Output File
**`point_in_time_map.json`** - A timeline of filing events for each company.

## Key Concepts Implemented

### 1. The "Known As Of" Framework
- **Period End Date**: When the quarter/year actually ended (e.g., 2023-12-31)
- **Filing Date**: When the data was published to EDGAR (e.g., 2024-02-20)
- **Lag**: The critical gap between these two dates (usually 20-60 days) where trading decisions must rely on *previous* data.

### 2. Timeline Reconstruction
Successfully reconstructed filing histories for all 21 companies.

**Example: PLTR Fiscal 2023**
- **Q3 2023**: Period End `2023-09-30` -> Filed `2023-11-02` (Lag: 33 days)
- **FY 2023**: Period End `2023-12-31` -> Filed `2024-02-20` (Lag: 51 days)

**Impact on Backtest**:
- A strategy running on **Jan 15, 2024** must use **Q3 2023** numbers.
- It *cannot* see FY 2023 numbers yet, even though the year is over.
- This mapping enforces that discipline.

### 3. Handling Variations
- **Amendments**: Identified `10-K/A` and `10-Q/A` filings.
- **Form Types**: Handled `10-K`, `10-Q` (US) and `20-F`, `40-F` (International).
- **Fiscal Shifts**: Captured timeline continuity even across fiscal year changes.

## Data Verification
- **Coverage**: 21/21 Companies
- **Depth**: Historical data back to ~2009 for long-standing companies (MSFT, AAPL) and IPO dates for newer ones (PLTR, 2020).
- **Granularity**: Precise dates for quarterly and annual releases.

## Next Steps
Proceed to **Task #4: Implement Trailing Metrics System**, which will use this PIT map to calculate "TTM Sales" and "TTM Earnings" as they would have appeared to an investor on any specific historical date.
