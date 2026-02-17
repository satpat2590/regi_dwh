#!/usr/bin/env bash
# ============================================================================
# Regi DWH — Data Pipeline
#
# Orchestrates the full extraction pipeline:
#   1. Enrich companies with sector/industry metadata
#   2. Fetch XBRL financial facts from SEC EDGAR
#   3. Equity market data (yfinance)
#   4. Crypto market data (Binance/Coinbase)
#   5. News aggregation (NewsAPI/Finnhub/GDELT)
#   6. FRED macro economic indicators
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

# Handle --help before doing anything else
for arg in "$@"; do
    if [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
        echo "Usage:"
        echo "  ./run_pipeline.sh                          Process tickers from input.txt"
        echo "  ./run_pipeline.sh --tickers AAPL MSFT      Process specific tickers"
        echo "  ./run_pipeline.sh --input-file my.txt      Process from custom file"
        echo "  ./run_pipeline.sh --all                    Process all tickers in cik.json"
        echo "  ./run_pipeline.sh --force                  Force re-fetch, ignoring cache"
        echo ""
        echo "Crypto step options (passed to sources/crypto/pipeline.py):"
        echo "  --symbols BTCUSDT ETHUSDT                  Specific crypto symbols"
        echo "  --provider binance|coinbase                 Data provider (default: binance)"
        echo "  --interval 1m|5m|1h|4h|1d|1w              Candlestick interval (default: 1d)"
        echo "  --days N                                   Days of history (crypto, default: 365)"
        echo ""
        echo "News step options (passed to sources/news/pipeline.py):"
        echo "  --news-provider newsapi|finnhub|gdelt|all  News provider (default: all)"
        echo "  --news-queries 'inflation' 'GDP'           Custom search queries"
        echo "  --news-days N                              Days of news to fetch (default: 7)"
        echo ""
        echo "FRED step options (passed to sources/fred/pipeline.py):"
        echo "  --fred-series GDP UNRATE ...               Specific FRED series IDs"
        echo "  --fred-days N                              Days of FRED history (default: 3650)"
        exit 0
    fi
done

# Split args: stock scripts vs crypto vs news vs fred pipeline
# Stock-only:  --tickers, --input-file, --all
# Crypto-only: --symbols, --provider, --interval, --days
# News-only:   --news-provider, --news-queries, --news-days
# FRED-only:   --fred-series, --fred-days
# Shared:      --force
STOCK_ARGS=()
CRYPTO_ARGS=()
NEWS_ARGS=()
FRED_ARGS=()

_i=0
_all_args=("$@")
_n=${#_all_args[@]}
while [[ $_i -lt $_n ]]; do
    _arg="${_all_args[$_i]}"
    case "$_arg" in
        --tickers|--input-file)
            STOCK_ARGS+=("$_arg"); _i=$((_i + 1))
            while [[ $_i -lt $_n && "${_all_args[$_i]}" != --* ]]; do
                STOCK_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1))
            done ;;
        --all)
            STOCK_ARGS+=("$_arg"); _i=$((_i + 1)) ;;
        --symbols|--interval|--days)
            CRYPTO_ARGS+=("$_arg"); _i=$((_i + 1))
            while [[ $_i -lt $_n && "${_all_args[$_i]}" != --* ]]; do
                CRYPTO_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1))
            done ;;
        --provider)
            CRYPTO_ARGS+=("$_arg"); _i=$((_i + 1))
            if [[ $_i -lt $_n ]]; then CRYPTO_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1)); fi ;;
        --news-provider)
            NEWS_ARGS+=("--provider"); _i=$((_i + 1))
            if [[ $_i -lt $_n ]]; then NEWS_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1)); fi ;;
        --news-queries)
            NEWS_ARGS+=("--queries"); _i=$((_i + 1))
            while [[ $_i -lt $_n && "${_all_args[$_i]}" != --* ]]; do
                NEWS_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1))
            done ;;
        --news-days)
            NEWS_ARGS+=("--days"); _i=$((_i + 1))
            if [[ $_i -lt $_n ]]; then NEWS_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1)); fi ;;
        --fred-series)
            FRED_ARGS+=("--series"); _i=$((_i + 1))
            while [[ $_i -lt $_n && "${_all_args[$_i]}" != --* ]]; do
                FRED_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1))
            done ;;
        --fred-days)
            FRED_ARGS+=("--days"); _i=$((_i + 1))
            if [[ $_i -lt $_n ]]; then FRED_ARGS+=("${_all_args[$_i]}"); _i=$((_i + 1)); fi ;;
        --force)
            STOCK_ARGS+=("$_arg"); CRYPTO_ARGS+=("$_arg"); NEWS_ARGS+=("$_arg"); FRED_ARGS+=("$_arg"); _i=$((_i + 1)) ;;
        *)
            STOCK_ARGS+=("$_arg"); CRYPTO_ARGS+=("$_arg"); _i=$((_i + 1)) ;;
    esac
done

# Determine what we're processing for display
if [[ $# -eq 0 ]]; then
    if [[ -f "input.txt" ]]; then
        TICKER_COUNT=$(grep -v '^\s*#' input.txt | grep -v '^\s*$' | wc -l | tr -d ' ')
        echo -e "${BLUE}[$(ts)] >> Source: input.txt (${TICKER_COUNT} tickers)${RESET}"
    else
        echo -e "${YELLOW}[$(ts)] WARN No input.txt found, using defaults${RESET}"
    fi
else
    [[ ${#STOCK_ARGS[@]} -gt 0 ]] && echo -e "${BLUE}[$(ts)] >> Stock args: ${STOCK_ARGS[*]}${RESET}"
    [[ ${#CRYPTO_ARGS[@]} -gt 0 ]] && echo -e "${BLUE}[$(ts)] >> Crypto args: ${CRYPTO_ARGS[*]}${RESET}"
    [[ ${#NEWS_ARGS[@]} -gt 0 ]] && echo -e "${BLUE}[$(ts)] >> News args: ${NEWS_ARGS[*]}${RESET}"
    [[ ${#FRED_ARGS[@]} -gt 0 ]] && echo -e "${BLUE}[$(ts)] >> FRED args: ${FRED_ARGS[*]}${RESET}"
fi

echo ""

# ---- Step 1: Enrichment ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 1/6: Company Enrichment${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/sec_edgar/enrich.py "${STOCK_ARGS[@]}"; then
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
echo -e "${BLUE}[$(ts)] >> Step 2/6: SEC XBRL Financial Facts Extraction${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/sec_edgar/pipeline.py "${STOCK_ARGS[@]}"; then
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
echo -e "${BLUE}[$(ts)] >> Step 3/6: Equity Market Data (yfinance)${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/equity/pipeline.py "${STOCK_ARGS[@]}"; then
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
echo -e "${BLUE}[$(ts)] >> Step 4/6: Crypto Market Data (Binance/Coinbase)${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/crypto/pipeline.py "${CRYPTO_ARGS[@]}"; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK Crypto extraction complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR Crypto extraction failed (exit code $?)${RESET}"
    exit 1
fi

echo ""

# ---- Step 5: News Aggregation ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 5/6: News Aggregation (NewsAPI/Finnhub/GDELT)${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/news/pipeline.py "${NEWS_ARGS[@]}"; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK News extraction complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR News extraction failed (exit code $?)${RESET}"
    echo -e "${YELLOW}[$(ts)] WARN Continuing despite news failure (supplementary data)${RESET}"
fi

echo ""

# ---- Step 5.5: NLP Sentiment Enrichment ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 5.5: NLP Sentiment Enrichment (VADER)${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/news/enrich_sentiment.py; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK Sentiment enrichment complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR Sentiment enrichment failed (exit code $?)${RESET}"
    echo -e "${YELLOW}[$(ts)] WARN Continuing despite enrichment failure${RESET}"
fi

echo ""

# ---- Step 6: FRED Macro Economic Data ----
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo -e "${BLUE}[$(ts)] >> Step 6/6: FRED Macro Economic Indicators${RESET}"
echo -e "${CYAN}──────────────────────────────────────────────────────────${RESET}"
echo ""

if python3 sources/fred/pipeline.py "${FRED_ARGS[@]}"; then
    echo ""
    echo -e "${GREEN}[$(ts)] OK FRED extraction complete${RESET}"
else
    echo ""
    echo -e "${RED}[$(ts)] ERR FRED extraction failed (exit code $?)${RESET}"
    echo -e "${YELLOW}[$(ts)] WARN Continuing despite FRED failure (supplementary data)${RESET}"
fi

echo ""
echo -e "${CYAN}============================================================${RESET}"
echo -e "${GREEN}[$(ts)] OK Pipeline complete${RESET}"
echo -e "${CYAN}============================================================${RESET}"
echo ""
