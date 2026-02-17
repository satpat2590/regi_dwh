
import subprocess
import time
import requests
import sys
import os
import signal

def test_api():
    print("Starting API server for testing...")
    # Start API server in background
    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8002"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.getcwd()
    )

    try:
        # Wait for server to start
        print("Waiting for server to start...")
        time.sleep(5)
        
        base_url = "http://127.0.0.1:8002"
        
        # Test 1: Get Crypto Symbols
        print("\n--- Testing GET /api/v1/crypto/symbols ---")
        response = requests.get(f"{base_url}/api/v1/crypto/symbols")
        if response.status_code == 200:
            symbols = response.json()
            print(f"Success! Found {len(symbols)} symbols.")
            if len(symbols) > 0:
                print(f"Sample: {symbols[0]}")
        else:
            print(f"Failed! Status: {response.status_code}")
            print(response.text)
            
        # Test 2: Get Crypto History (BTCUSDT)
        print("\n--- Testing GET /api/v1/crypto/BTCUSDT/history ---")
        response = requests.get(f"{base_url}/api/v1/crypto/BTCUSDT/history?limit=10")
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Retrieved history for {data['symbol']}")
            print(f"Count: {data['count']}")
            if data['count'] > 0:
                print(f"Latest price: {data['prices'][-1]}")
        else:
            print(f"Failed! Status: {response.status_code}")
            print(response.text)

        # Test 3: Get Crypto History (Invalid Symbol)
        print("\n--- Testing GET /api/v1/crypto/INVALID/history ---")
        response = requests.get(f"{base_url}/api/v1/crypto/INVALID/history")
        if response.status_code == 404:
            print("Success! Correctly returned 404 for invalid symbol.")
        else:
            print(f"Failed! Expected 404, got {response.status_code}")

    finally:
        print("\nStopping API server...")
        os.kill(api_process.pid, signal.SIGTERM)
        api_process.wait()

if __name__ == "__main__":
    test_api()
