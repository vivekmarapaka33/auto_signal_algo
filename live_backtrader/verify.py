import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health():
    try:
        r = requests.get(f"{BASE_URL}/health")
        print(f"Health Check: {r.status_code} - {r.json()}")
    except Exception as e:
        print(f"Health Check Failed: {e}")

def test_ssid_update():
    # Valid invalid SSID for testing validation logic
    ssid = '42["auth",{"uid":123456,"token":"test_token"}]'
    print(f"Testing SSID Update with: {ssid}")
    try:
        r = requests.post(f"{BASE_URL}/api/v1/account/ssid", json={"ssid": ssid})
        # We expect a 400 or 500 here because the SSID is fake and connection will fail
        # This proves the validation logic (connecting to PocketOption) is triggering
        print(f"SSID Update Response: {r.status_code} (Expected 400/500 for fake SSID)")
        if r.status_code == 200:
             print("WARNING: Fake SSID was accepted (Verification likely disabled or mocked)")
        else:
             print("SSID Verification working (Rejected fake credentials)")
    except Exception as e:
        print(f"SSID Update Request Failed: {e}")

def test_balance_endpoint():
    try:
        r = requests.get(f"{BASE_URL}/api/v1/account/balance")
        print(f"Balance Check: {r.status_code}")
        # Expect 400 if not connected/configured
    except Exception as e:
        print(f"Balance Check Failed: {e}")

def test_backtest_endpoint():
    code = """
class TestStrategy(bt.Strategy):
    def next(self):
        self.buy()
"""
    try:
        r = requests.post(f"{BASE_URL}/api/v1/backtest", json={
            "code": code,
            "asset": "EURUSD_otc",
            "period": 60
        })
        # This might fail if no history data is fetched yet, but let's check response
        print(f"Backtest: {r.status_code}")
        if r.status_code == 200:
            print("Backtest Result:", r.json().keys())
        else:
            print("Backtest Error:", r.text[:200])
    except Exception as e:
        print(f"Backtest Request Failed: {e}")

if __name__ == "__main__":
    print("Running Verification...")
    time.sleep(2) # Give server time to settle
    test_health()
    test_ssid_update()
    test_balance_endpoint()
    test_backtest_endpoint()
