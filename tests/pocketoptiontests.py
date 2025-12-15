from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync

import asyncio
# from BinaryOptionsToolsV2.tracing import start_logs

# # Initialize logging
# start_logs(path="logs/", level="INFO", terminal=True)

# Main part of the code
async def main(ssid: str):
    # The api automatically detects if the 'ssid' is for real or demo account
    api = PocketOptionAsync(ssid)
    await asyncio.sleep(5)

    balance = await api.balance()
    print(f"Balance: {balance}")


if __name__ == "__main__":
    ssid = input("Please enter your ssid: ")
    asyncio.run(main(ssid))