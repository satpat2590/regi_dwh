import yfinance as yf
import pandas as pd

# Pull daily data
ticker = yf.Ticker("AAPL")
df = ticker.history(period="2y")  # 2 years of daily data

# Calculate volume statistics
df['vol_ma_20'] = df['Volume'].rolling(window=20).mean()  # 20-day moving average
df['vol_std_20'] = df['Volume'].rolling(window=20).std()
df['vol_zscore'] = (df['Volume'] - df['vol_ma_20']) / df['vol_std_20']

# Flag unusual volume days (e.g., > 2 standard deviations)
df['unusual_volume'] = abs(df['vol_zscore']) > 2