from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
import asyncio
import json
import os

def load_ssid():
    return "42[\"auth\",{\"session\":\"dummy\",\"isDemo\":1,\"uid\":123,\"platform\":2}]"

async def main():
    print("🚀 Starting Debug Script")
    ssid = load_ssid()
    print(f"📦 Loaded SSID: {ssid[:20]}...")
    
    print("⏳ Initializing PocketOptionAsync...")
    try:
        # Try with timeout to catch hang
        api = PocketOptionAsync(ssid)
        print("✅ PocketOptionAsync Initialized!")
        
        print("Testing balance fetch...")
        balance = await api.balance()
        print(f"💰 Balance: {balance}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
