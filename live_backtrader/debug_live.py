import sys
import os
import time
import multiprocessing

# Setup paths to find ChipaPocketOptionData
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
sys.path.append(os.path.join(workspace_root, "trading_system", "tests", "ChipaPocketOptionData1"))

def main():
    try:
        from ChipaPocketOptionData import subscribe_symbol_timed
    except ImportError:
        print("Could not import ChipaPocketOptionData")
        sys.exit(1)

    # Read SSID
    ssid = None
    if os.path.exists("ssid.txt"):
        with open("ssid.txt", "r") as f:
            ssid = f.read().strip()

    print(f"DEBUG: Using SSID: {ssid[:20]}...")

    print("DEBUG: Starting collector...")
    try:
        with subscribe_symbol_timed("EURUSD_otc", 5, ssids=[ssid]) as collector:
            print("DEBUG: Collector started. Enumerating...")
            count = 0
            for candle in collector:
                print(f"DEBUG: Received Candle! {candle}")
                count += 1
                if count >= 1:
                    break
            print("DEBUG: Loop finished.")
    except Exception as e:
        print(f"DEBUG: Exception: {e}")

    print("DEBUG: Done.")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
