import sys
import os


from ChipaPocketOptionData import get_candles


try:
    sys.modules['talib'] = None
except Exception:
    pass

import backtrader as bt
import pandas as pd
from datetime import datetime

class PocketOptionMomentumStrategy(bt.Strategy):
    """
    A simple technical analysis strategy for Binary Options backtesting.
    Setup:
      - 2 Minute Timeframe (M2 Candles)
      - 2 Minute Expiry (1 Candle)
    
    Indicators:
      - SMA Fast (Period 5) v/s SMA Slow (Period 20)
      - RSI (Period 14) for filter
    
    Logic:
      - CALL: SMA Fast crosses above SMA Slow AND RSI > 50 (Momentum Up)
      - PUT:  SMA Fast crosses below SMA Slow AND RSI < 50 (Momentum Down)
    """
    params = dict(
        fast_period=5,
        slow_period=20,
        rsi_period=14,
        expiry=1,  # 1 candle expiration (2 mins)
    )

    def __init__(self):
        self.sma_fast = bt.ind.SMA(period=self.p.fast_period)
        self.sma_slow = bt.ind.SMA(period=self.p.slow_period)
        self.rsi = bt.ind.RSI(period=self.p.rsi_period)
        self.crossover = bt.ind.CrossOver(self.sma_fast, self.sma_slow)
        
        self.entry_bar = None
        self.wins = 0
        self.losses = 0
        
        # Binary Option Simulation State
        self.equity = 1000.0  # Default, will update from broker in start()
        self.base_stake_pct = 0.01
        self.current_stake = 10.0 # Placeholder
        self.payout = 0.92 # 92% profit on win
        
    def start(self):
        self.equity = self.broker.get_cash()
        self.current_stake = self.equity * self.base_stake_pct
        print(f"Strategy Start. Capital: {self.equity:.2f}, Base Stake: {self.current_stake:.2f}")

    def next(self):
        # Open Position Management (Binary Option Simulation)
        if self.position:
            # Check expiry
            if len(self) - self.entry_bar >= self.p.expiry:
                self.close()
                
                # Binary Option Result Simulation
                entry_price = self.position.price
                close_price = self.data.close[0]
                won = False
                
                if self.position.size > 0: # Call
                    won = close_price > entry_price
                elif self.position.size < 0: # Put
                    won = close_price < entry_price
                
                if won:
                    self.wins += 1
                    profit = abs(self.position.size) * self.payout
                    self.equity += profit
                    # Reset to base stake on win
                    # Recalculate base stake based on INITIAL capital or CURRENT? 
                    # Usually "Reset to base" means the original intended fixed amount or recalculated safe amount.
                    # Let's stick to 1% of CURRENT equity to compound, or fixed? 
                    # User said "initial trading amount set to 1% on full trading amount". 
                    # I will assume "Base" is dynamic 1% of current equity to allow growth, OR static.
                    # Martingale usually implies resetting to the starting bet.
                    # I'll re-calculate 1% of current equity for the "Base" to be safe and grow.
                    self.current_stake = self.equity * self.base_stake_pct 
                    print(f"WIN | Profit: +{profit:.2f} | New Equity: {self.equity:.2f} | Next Stake: {self.current_stake:.2f}")
                else:
                    self.losses += 1
                    loss = abs(self.position.size)
                    self.equity -= loss
                    # Martingale: Double the stake on loss
                    self.current_stake = abs(self.position.size) * 2
                    print(f"LOSS | Loss: -{loss:.2f} | New Equity: {self.equity:.2f} | Next Stake: {self.current_stake:.2f}")
                
            return

        # Entry Logic
        # Ensure we have enough money
        if self.current_stake > self.equity:
            print("Margin Call: Not enough equity for next trade.")
            return

        if self.crossover > 0 and self.rsi[0] > 50:
            self.buy(size=self.current_stake)
            self.entry_bar = len(self)
        
        elif self.crossover < 0 and self.rsi[0] < 50:
            self.sell(size=self.current_stake)
            self.entry_bar = len(self)

    def stop(self):
        print(f"Strategy Results: Wins: {self.wins}, Losses: {self.losses}")
        print(f"Simulated Binary Option Ending Equity: {self.equity:.2f}")


if __name__ == '__main__':
    # 1. Configuration
    ASSET = "EURUSD_otc"
    PERIOD = 120    # 2 minutes
    TIMEFRAME = 14400 # 4 hours of data to ensure enough candles for indicators (4h = 240 mins = 120 candles)
    
    # Standard SSID list
    ssids = [
        '42["auth",{"session":"m9n4q60krjrojb1elm1g171tff","isDemo":1,"uid":120824712,"platform":2,"isFastHistory":true,"isOptimized":true}]',
    ]

    print(f"Fetching {TIMEFRAME}s of data for {ASSET} (M{PERIOD/60:.0f} Candles)...")
    
    try:
        candles = get_candles(
            asset=ASSET,
            period=PERIOD,
            time=TIMEFRAME,
            ssids=ssids
        )
    except Exception as e:
        print(f"Failed to fetch candles: {e}")
        exit(1)

    if not candles:
        print("No candles returned.")
        exit(1)

    print(f"Collected {len(candles)} candles.")

    # 2. Prepare Data Feed
    df = pd.DataFrame(candles)
    
    # Ensure standard columns
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    else:
        print("Error: DataFrame missing 'timestamp' column")
        print(df.columns)
        exit(1)
        
    df.set_index('datetime', inplace=True)
    df.sort_index(inplace=True)
    
    # Fill missing columns for Backtrader
    # Handle 'volume' specifically if it exists but has None values
    if 'volume' in df.columns:
        df['volume'] = df['volume'].fillna(0)
    else:
        df['volume'] = 0
        
    df['openinterest'] = 0
    
    # Ensure all data is float (except index) to prevent NoneTypes
    cols_to_numeric = ['open', 'high', 'low', 'close', 'volume', 'openinterest']
    for col in cols_to_numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # Create Data Feed
    data = bt.feeds.PandasData(dataname=df)

    # 3. Setup Cerebro
    cerebro = bt.Cerebro()
    cerebro.adddata(data)
    
    cerebro.addstrategy(PocketOptionMomentumStrategy)

    # 4. Configure Broker (Binary Options Simulation)
    # Binary options payout is typically fixed (e.g. 92% profit on win, 100% loss on loss)
    # Backtrader standard broker is for Spot/Futures (Price diff * Size).
    # We will simulate roughly by checking the final PnL, but the Strategy class tracks win/loss count.
    cerebro.broker.setcash(1000.0)
    cerebro.broker.setcommission(commission=0.0)

    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")
    
    cerebro.run()
    
    print(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")
    
    # 5. Plot
    try:
        cerebro.plot(style='candlestick')
    except Exception as e:
        print(f"Plotting failed (likely no display): {e}")
