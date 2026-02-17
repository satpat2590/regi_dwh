# SEC Financial Data API

REST API server for exposing SEC EDGAR financial data to multiple clients.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_api.txt
```

### 2. Start the API Server

```bash
./run_api.sh
```

The server will start on `http://localhost:8000`

### 3. Access Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Health & Info

- `GET /` - Health check and database statistics
- `GET /sectors` - List all available sectors

### Company Information

- `GET /companies` - Get all companies
- `GET /companies/{ticker}` - Get company metadata
- `GET /sectors/{sector}/tickers` - Get tickers in a sector

### Financial Metrics

- `GET /metrics/{ticker}/{field}` - Get financial metric
  - Query params: `as_of_date`, `time_series`, `start_date`, `end_date`, `fiscal_period`, `limit`

### TTM Metrics

- `GET /ttm/{ticker}/{metric_name}` - Get TTM metric
  - Metric names: `Revenue_TTM`, `NetIncome_TTM`
  - Query params: `time_series`, `limit`

### Sector Analysis

- `GET /sectors/{sector}/compare` - Compare metric across sector
  - Query params: `field`, `fiscal_period`

### Field Discovery

- `GET /fields/{ticker}` - Get available fields for a ticker
  - Query params: `statement_type`, `min_priority`
- `GET /catalog` - Get full field catalog
  - Query params: `min_priority`

### Backtesting

- `GET /backtest/{ticker}` - Get financials as of a specific date
  - Query params: `as_of_date`, `fields`, `min_priority`

## Client Usage

### Python Client

```python
from api.client_example import SECDataClient

client = SECDataClient("http://localhost:8000")

# Get company info
company = client.get_company("AAPL")

# Get TTM revenue
revenue = client.get_ttm_revenue("AAPL")

# Compare sector
comparison = client.compare_sector("Technology", "Revenues", "FY")
```

### cURL Examples

```bash
# Health check
curl http://localhost:8000/

# Get company
curl http://localhost:8000/companies/AAPL

# Get latest revenue
curl http://localhost:8000/metrics/AAPL/Revenues

# Get TTM revenue
curl http://localhost:8000/ttm/AAPL/Revenue_TTM

# Compare sector
curl "http://localhost:8000/sectors/Technology/compare?field=Revenues&fiscal_period=FY"

# Backtesting
curl "http://localhost:8000/backtest/AAPL?as_of_date=2023-06-30&min_priority=150"
```

## Configuration

Edit `api/config.py` to customize:

- Database path
- Host and port
- CORS origins
- Rate limiting (optional)
- API key authentication (optional)

## Production Deployment

### Option 1: Direct Uvicorn

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Option 2: Systemd Service

Create `/etc/systemd/system/sec-api.service`:

```ini
[Unit]
Description=SEC Financial Data API
After=network.target

[Service]
Type=simple
User=satya
WorkingDirectory=/home/satya/company_financials
ExecStart=/usr/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable sec-api
sudo systemctl start sec-api
```

### Option 3: Docker (Future)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements_api.txt
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Security Considerations

### For Production Deployment:

1. **Enable API Key Authentication**:
   - Set `API_KEY_ENABLED = True` in `config.py`
   - Set environment variable: `export SEC_API_KEY=your-secret-key`

2. **Restrict CORS**:
   - Change `CORS_ORIGINS = ["*"]` to specific domains
   - Example: `CORS_ORIGINS = ["https://yourdomain.com"]`

3. **Add Rate Limiting**:
   - Install: `pip install slowapi`
   - Enable in `config.py`: `RATE_LIMIT_ENABLED = True`

4. **Use HTTPS**:
   - Deploy behind nginx or use Uvicorn with SSL certificates

## Performance

- **Concurrent Reads**: SQLite WAL mode supports multiple simultaneous readers
- **Response Times**: 
  - Simple queries: <10ms
  - Time series: 50-200ms
  - Sector comparisons: 100-300ms
- **Recommended Workers**: 4-8 for production

## Troubleshooting

### Database Not Found

```bash
# Run the pipeline first to create the database
./run_pipeline.sh
```

### Port Already in Use

```bash
# Use a different port
./run_api.sh 0.0.0.0 8001
```

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements_api.txt
```

## Testing

Run the example client:

```bash
# Start the server first
./run_api.sh

# In another terminal, run the client
python api/client_example.py
```

## Architecture

```
┌──────────────┐     HTTP      ┌──────────────┐
│ Trading Bot  │──────────────►│  FastAPI     │
│   (Python)   │               │  Server      │
└──────────────┘               │              │
                               │  - Routes    │
┌──────────────┐     HTTP      │  - Models    │
│ Dashboard    │──────────────►│  - Validation│
│   (Web)      │               │              │
└──────────────┘               └──────┬───────┘
                                      │
                                      ▼
                               ┌──────────────┐
                               │ Data Access  │
                               │   Layer      │
                               └──────┬───────┘
                                      │
                                      ▼
                               data/financials.db
                               (SQLite, read-only)
```
