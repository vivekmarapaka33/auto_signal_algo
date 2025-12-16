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


    # (buy_id, buy) = await api.buy(
    #     asset="EURUSD_otc", amount=1.0, time=60, check_win=False
    # )
    # print(f"Buy trade id: {buy_id}\nBuy trade data: {buy}")
    # (sell_id, sell) = await api.sell(
    #     asset="EURUSD_otc", amount=1.0, time=60, check_win=False
    # )
    # print(f"Sell trade id: {sell_id}\nSell trade data: {sell}")


if __name__ == "__main__":
    ssid = '42["auth",{"session":"4f485bb2a3a704c9e2cf101a71a3f04b","uid":118330943,"isDemo":1,"platform":2,"isFastHistory":true,"isOptimized":true}]'
    asyncio.run(main(ssid))