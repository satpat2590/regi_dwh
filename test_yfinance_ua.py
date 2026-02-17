import yfinance as yf
import requests

def test_custom_session(ticker_symbol):
    print(f"Testing {ticker_symbol} with custom session...")
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        ticker = yf.Ticker(ticker_symbol, session=session)
        hist = ticker.history(period="1d")
        print("Success!")
        print(hist)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_custom_session("BGFV")
