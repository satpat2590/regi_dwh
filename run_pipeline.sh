#!/usr/bin/env bash
# ============================================================================
# Regi DWH — Data Pipeline
#
# Orchestrates the full extraction pipeline:
#   1. Enrich companies with sector/industry metadata
#   2. Fetch XBRL financial facts from SEC EDGAR
#
# Usage:
#   ./run_pipeline.sh                        # Process tickers from input.txt
#   ./run_pipeline.sh --tickers AAPL MSFT    # Process specific tickers
#   ./run_pipeline.sh --input-file my.txt    # Process from custom file
#   ./run_pipeline.sh --all                  # Process all tickers in cik.json
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
CYAN='\033[1;36m'
GREEN='\033[1;32m'
RED='\033[1;31m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
RESET='\033[0m'

# Timestamp
ts() { date +"%H:%M:%S"; }

echo ""
echo -e "${CYAN}============================================================${RESET}"
echo -e "${CYAN}  Regi DWH — Data Pipeline${RESET}"
echo -e "${CYAN}============================================================${RESET}"
echo ""

# Forward all CLI args to both scripts
ARGS=("$@")

# Determine what we're processing for display
if [[ ${#ARGS[@]} -eq 0 ]]; then
    if [[ -f "input.txt" ]]; then
        TICKER_COUNT=$(grep -v '^\s*#' input.txt | grep -v '^\s*$' | wc -l | tr -d ' ')
        echo -e "${BLUE}[$(ts)] >> Source: input.txt (${TICKER_COUNT} tickers)${RESET}"
    else
        echo -e "${YELLOW}[$(ts)] WARN No input.txt found, using defaults${RESET}"
    fi
else
    echo -e "${BLUE}[$(ts)] >> Args: ${ARGS[*]}${RESET}"
fi

echo ""

# ---- Step 1: Enrichment ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 1/3: Company Enrichment${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/sec_edgar/enrich.py "${ARGS[@]}"; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK Enrichment complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR Enrichment failed (exit code $?)${RESET}"
    exit 1
fi

echo ""

# ---- Step 2: SEC XBRL Extraction ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 2/3: SEC XBRL Financial Facts Extraction${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/sec_edgar/pipeline.py "${ARGS[@]}"; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK SEC extraction complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR SEC extraction failed (exit code $?)${RESET}"
    exit 1
fi

echo ""

# ---- Step 3: Equity Market Data ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 3/3: Equity Market Data (yfinance)${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/equity/pipeline.py "${ARGS[@]}"; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK Equity extraction complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR Equity extraction failed (exit code $?)${RESET}"
    # Continue even if equity fails (since it's paused/optional)
    echo -e "${YELLOW}[$(ts)] WARN Continuing despite equity failure${RESET}"
fi

echo ""

# ---- Step 4: Crypto Market Data ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 4/4: Crypto Market Data (Binance/Coinbase)${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/crypto/pipeline.py; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK Crypto extraction complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR Crypto extraction failed (exit code $?)${RESET}"
    exit 1
fi

echo ""
echo -e "${CYAN}============================================================${RESET}"
echo -e "${GREEN}[$(ts)] OK Pipeline complete${RESET}"
echo -e "${CYAN}============================================================${RESET}"
echo ""
