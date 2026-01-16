from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")

time_offset = None  # seconds

if __name__ == '__main__':
    from ChipaPocketOptionData import subscribe_symbol_timed

    ssids = [
        '42["auth",{"session":"m9n4q60krjrojb1elm1g171tff","isDemo":1,"uid":120824712,"platform":2,"isFastHistory":true,"isOptimized":true}]'
    ]

    with subscribe_symbol_timed("EURUSD_otc", 5, ssids=ssids) as collector:
        for i, candle in enumerate(collector):

            server_utc = datetime.fromtimestamp(
                candle["timestamp"], tz=UTC
            )

            # Calculate offset once
            if time_offset is None:
                local_utc_now = datetime.now(tz=UTC)
                time_offset = (local_utc_now - server_utc).total_seconds()

            # Correct timestamp
            corrected_utc = server_utc + timedelta(seconds=time_offset)
            ist_time = corrected_utc.astimezone(IST)

            print({
                "symbol": candle["symbol"],
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "time_ist": ist_time.strftime("%Y-%m-%d %H:%M:%S")
            })

            # if i >= 100:
            #     break
