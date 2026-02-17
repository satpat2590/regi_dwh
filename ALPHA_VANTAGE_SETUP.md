# Alpha Vantage Setup Guide

## Quick Start

### 1. Get Your API Key

1. Visit: https://www.alphavantage.co/support/#api-key
2. Enter your email address
3. Receive instant API key (no credit card required)

**Free Tier Limits**:
- 25 requests per day
- 5 calls per minute

**Paid Tiers** (remove daily cap):
- Basic: $29.99/month (75 calls/minute)
- Pro: $49.99/month (150 calls/minute)
- Enterprise: $249.99/month (1200 calls/minute)

### 2. Configure API Key

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```bash
ALPHA_VANTAGE_API_KEY=your_actual_key_here
```

### 3. Test the Provider

Run the test script to verify your setup:

```bash
export ALPHA_VANTAGE_API_KEY='your_key_here'
python3 test_alpha_vantage.py
```

Expected output:
```
Testing Alpha Vantage Provider with BGFV
✓ Provider initialized
✓ Retrieved 1200+ price records
✓ Retrieved dividend records
✓ Retrieved company info
```

### 4. Run the Pipeline

Test with a single ticker:

```bash
python3 sources/equity/pipeline.py --tickers BGFV --provider alpha_vantage
```

Run for all tickers in `input.txt`:

```bash
./run_pipeline.sh --tickers AAPL MSFT GOOGL
```

## Usage Examples

### Single Ticker
```bash
python3 sources/equity/pipeline.py --tickers BGFV
```

### Multiple Tickers
```bash
python3 sources/equity/pipeline.py --tickers AAPL MSFT GOOGL BGFV
```

### From File
```bash
python3 sources/equity/pipeline.py --input-file my_tickers.txt
```

### Force Refresh (Ignore Cache)
```bash
python3 sources/equity/pipeline.py --tickers BGFV --force
```

## Rate Limiting

The provider automatically handles rate limiting:
- **Free tier**: 12 seconds between calls (5 calls/minute)
- **Paid tiers**: Configurable in `alpha_vantage.py`

For 40 tickers × 4 endpoints = 160 calls:
- Free tier: ~32 minutes
- Basic tier: ~2 minutes
- Pro tier: ~1 minute

## Troubleshooting

### "API key required" Error
```
ValueError: Alpha Vantage API key required
```
**Solution**: Set `ALPHA_VANTAGE_API_KEY` environment variable or create `.env` file.

### "Rate limit exceeded" Error
```
RateLimitError: Too Many Requests
```
**Solution**: Wait 1 minute or upgrade to paid tier.

### "Data not available" Error
```
DataNotFoundError: Invalid API call
```
**Solution**: Check ticker symbol is valid. Some OTC/penny stocks may not be available.

## Migration from Yahoo Finance

The pipeline is **backward compatible**. The database schema remains unchanged.

**What changed**:
- Data source: Yahoo Finance → Alpha Vantage
- More reliable for mid-cap/small-cap stocks
- Better error handling and rate limiting

**What stayed the same**:
- Database schema (no migration needed)
- Excel output format
- API endpoints (data access layer unchanged)

## Cost Analysis

### Current Universe (40 tickers)
- 40 tickers × 4 endpoints = 160 API calls
- **Free tier**: 25 calls/day = 7 days to complete
- **Basic tier ($30/month)**: ~2 minutes to complete ✅ Recommended

### Expanded Universe (500 tickers)
- 500 tickers × 4 endpoints = 2000 API calls
- **Pro tier ($50/month)**: ~13 minutes to complete

### Full Market (5000+ tickers)
- 5000 tickers × 4 endpoints = 20,000 API calls
- **Enterprise tier ($250/month)**: ~17 minutes to complete

## Next Steps

1. ✅ Get API key from Alpha Vantage
2. ✅ Configure `.env` file
3. ✅ Test with `test_alpha_vantage.py`
4. ✅ Run pipeline for BGFV (the problematic ticker)
5. ⏭️ Upgrade to paid tier if needed
6. ⏭️ Update `input.txt` with full ticker universe
7. ⏭️ Schedule daily pipeline runs (cron job)
