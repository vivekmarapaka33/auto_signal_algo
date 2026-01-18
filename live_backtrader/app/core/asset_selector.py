import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger("AssetSelector")

def get_best_forex_asset():
    # 1. List of Major Forex pairs (Yahoo Finance uses ticker format like 'EURUSD=X')
    tickers = [
        "AUD/CAD OTC",
        "AUD/USD OTC",
        "CAD/JPY OTC",
        "CHF/JPY OTC",
        "EUR/GBP OTC",
        "EUR/JPY OTC",
        "EUR/USD OTC",
        "AUD/NZD OTC",
        "CHF/JPY",
        "USD/CAD OTC",
        "USD/JPY OTC",
        "USD/CNH OTC",
    ]

    # Convert tickers to Yahoo Finance format
    formatted_tickers = []
    ticker_map = {} # Map formatted to original for return
    for ticker in tickers:
        formatted_ticker = ticker.replace('/', '').replace(' OTC', '') + '=X'
        formatted_tickers.append(formatted_ticker)
        ticker_map[formatted_ticker] = ticker

    logger.info("Fetching market data for asset selection...")
    print("Fetching market data... please wait.")

    data_dict = {}

    for ticker in formatted_tickers:
        try:
            # Fetch hourly data for the last 5 days (approx 100 candles)
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="1d", interval="2m")

            if len(df) > 0:
                df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
                df['High'] = pd.to_numeric(df['High'], errors='coerce')
                df['Low'] = pd.to_numeric(df['Low'], errors='coerce')

                df_cleaned = df.dropna(subset=['Close', 'High', 'Low'])

                if len(df_cleaned) < 24:
                    continue

                try:
                    high = df_cleaned['High']
                    low = df_cleaned['Low']
                    close = df_cleaned['Close']

                    tr1 = high - low
                    tr2 = abs(high - close.shift())
                    tr3 = abs(low - close.shift())
                    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

                    atr_series = tr.rolling(window=14).mean()
                    atr = atr_series.iloc[-1] if not atr_series.empty else float('nan')

                    current_close = float(close.iloc[-1])
                    previous_close_24h = float(close.iloc[-24])
                    atr = float(atr)

                    if pd.isna(current_close) or pd.isna(previous_close_24h) or previous_close_24h == 0:
                        roc = float('nan')
                    else:
                        roc = (current_close - previous_close_24h) / previous_close_24h * 100

                    if pd.isna(atr) or pd.isna(current_close) or current_close == 0:
                        atr_percent = float('nan')
                    else:
                        atr_percent = (atr / current_close) * 100

                    current_price_scalar = float(current_close)
                    atr_percent_scalar = float(atr_percent)
                    roc_scalar = float(roc)

                    if pd.notna(atr_percent_scalar) and pd.notna(roc_scalar):
                        original_name = ticker_map.get(ticker, ticker)
                        data_dict[ticker] = {
                            'Price': current_price_scalar,
                            'ATR_Percent': atr_percent_scalar,
                            'Momentum_24h': roc_scalar,
                            'Original': original_name
                        }
                except Exception as calc_e:
                    print(f"Error during calculation for {ticker}: {calc_e}")
            else:
                 pass 
        except Exception as download_e:
            print(f"Error downloading {ticker}: {download_e}")

    if not data_dict:
        return []

    results_df = pd.DataFrame.from_dict(data_dict, orient='index')

    results_df['Scalping_Score'] = (results_df['ATR_Percent'] * 10) + abs(results_df['Momentum_24h'])
    results_df['Scalping_Score'] = pd.to_numeric(results_df['Scalping_Score'], errors='coerce')
    results_df = results_df.dropna(subset=['Scalping_Score'])

    if results_df.empty:
        return []

    results_df = results_df.sort_values(by='Scalping_Score', ascending=False)

    sorted_tickers = results_df.index.tolist()
    top_assets_array = []
    for t in sorted_tickers:
        clean = t.replace('=X', '')
        original = data_dict[t].get('Original', '')
        if "OTC" in original:
            clean = clean + "_otc"
        top_assets_array.append(clean)

    return top_assets_array
