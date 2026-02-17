#!/bin/bash
#
# Start the Regi DWH API server
#

set -euo pipefail

# Colors
C_CYAN='\033[0;36m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[1;33m'
C_RED='\033[0;31m'
C_RESET='\033[0m'

echo -e "${C_CYAN}========================================${C_RESET}"
echo -e "${C_CYAN}  Regi DWH — API Server${C_RESET}"
echo -e "${C_CYAN}========================================${C_RESET}"
echo ""

# Check if database exists
DB_PATH="data/financials.db"
if [ ! -f "$DB_PATH" ]; then
    echo -e "${C_RED}ERROR: Database not found at $DB_PATH${C_RESET}"
    echo "Please run the pipeline first to create the database:"
    echo "  ./run_pipeline.sh"
    exit 1
fi

echo -e "${C_GREEN}✓${C_RESET} Database found: $DB_PATH"

# Check for API dependencies
echo -e "\nChecking dependencies..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${C_YELLOW}Installing API dependencies...${C_RESET}"
    pip install -r requirements_api.txt
else
    echo -e "${C_GREEN}✓${C_RESET} Dependencies installed"
fi

# Get host and port from arguments or use defaults
HOST="${1:-0.0.0.0}"
PORT="${2:-8000}"

echo ""
echo -e "${C_CYAN}Starting API server...${C_RESET}"
echo -e "  Host: ${C_GREEN}$HOST${C_RESET}"
echo -e "  Port: ${C_GREEN}$PORT${C_RESET}"
echo ""
echo -e "${C_CYAN}API Documentation:${C_RESET}"
echo -e "  Swagger UI:  ${C_GREEN}http://localhost:$PORT/docs${C_RESET}"
echo -e "  ReDoc:       ${C_GREEN}http://localhost:$PORT/redoc${C_RESET}"
echo ""
echo -e "${C_YELLOW}Press Ctrl+C to stop the server${C_RESET}"
echo ""

# Start the server
python3 -m uvicorn api.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info
