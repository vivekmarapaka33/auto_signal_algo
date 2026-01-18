import sys
import os
import threading
import asyncio
import json
import logging
import collections
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.core.asset_selector import get_best_forex_asset

# Ensure we can find the ChipaPocketOptionData module
# Adjust this path based on where it actually is relative to this file
# Based on User context: trading_system\tests\ChipaPocketOptionData1
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.append(os.path.join(workspace_root, "trading_system", "tests", "ChipaPocketOptionData1"))

# Fallback or direct import
try:
    from ChipaPocketOptionData import subscribe_symbol_timed
except ImportError:
    # If standard import fails, try adding root
    sys.path.append(workspace_root)
    try:
        from ChipaPocketOptionData import subscribe_symbol_timed
    except ImportError:
        logging.error("Could not import ChipaPocketOptionData. Make sure it is in the path.")
        subscribe_symbol_timed = None

try:
    from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
except ImportError:
    PocketOptionAsync = None
    logging.warning("Could not import PocketOptionAsync from BinaryOptionsToolsV2. Real trading unavailable.")

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")

logger = logging.getLogger("LiveEngine")

class LiveStrategyBase:
    """
    Base class for Live Strategies. 
    Users should implement logic here.
    """
    def __init__(self):
        self.balance = 1000.0
        self.base_bet = 1.0
        self.current_bet = 1.0
        self.martingale_factor = 2.0
        self.expiry = 60 # Default Expiry in seconds
        self.wins = 0
        self.losses = 0
        self.trades = [] # List of active trades {entry_price, direction, amount, start_time, expiry_time}
        self.signals = [] 
        self.on_signal = None  # Callback function(signal_data)

    def set_signal_callback(self, callback):
        self.on_signal = callback

    def next(self, candle):
        """Called every time a new candle arrives."""
        pass

    def buy(self, price, time):
        return self._place_trade("CALL", price, time)

    def sell(self, price, time):
        return self._place_trade("PUT", price, time)
    
    def _place_trade(self, direction, price, time):
        trade = {
            "direction": direction,
            "entry_price": price,
            "amount": self.current_bet,
            "start_time": time,
            "expiry_time": time + self.expiry,
            "active": True
        }
        self.trades.append(trade)
        
        # Emit Signal
        if self.on_signal:
            self.on_signal({
                "direction": direction,
                "price": price,
                "time": time,
                "expiry": self.expiry
            })
            
        return trade

    def update_trades(self, current_price, current_time):
        """
        Simulate trade expiry. 
        Checks if current_time >= trade.expiry_time
        """
        completed = []
        for trade in self.trades:
            if not trade['active']: continue
            
            # Expiry Check
            if current_time >= trade['expiry_time']:
                is_win = False
                if trade['direction'] == 'CALL' and current_price > trade['entry_price']:
                    is_win = True
                elif trade['direction'] == 'PUT' and current_price < trade['entry_price']:
                    is_win = True
                
                profit = 0
                if is_win:
                    profit = trade['amount'] * 0.92 # 92% Payout
                    self.balance += profit
                    self.wins += 1
                    self.on_win(trade)
                else:
                    self.balance -= trade['amount']
                    self.losses += 1
                    self.on_loss(trade)
                
                trade['active'] = False
                trade['result'] = 'WIN' if is_win else 'LOSS'
                trade['profit'] = profit if is_win else -trade['amount']
                trade['exit_price'] = current_price
                completed.append(trade)
        return completed

    def on_win(self, trade):
        # Default Martingale Logic: Reset
        self.current_bet = self.base_bet

    def on_loss(self, trade):
        # Default Martingale Logic: Catchup
        self.current_bet *= self.martingale_factor

class MyLiveStrategy(LiveStrategyBase):
    def next(self, candle):
        # Default strategy logic: Simple random 50/50 for testing
        # Or simple strategy: Buy if close > open (Green), Sell if close < open (Red)
        if candle['close'] > candle['open']:
            self.buy(candle['close'], candle['time'])
        elif candle['close'] < candle['open']:
            self.sell(candle['close'], candle['time'])

# --- DYNAMIC STRATEGY ---
class DynamicStrategy(LiveStrategyBase):
    def __init__(self, code_str, risk_percent, martingale_multiplier, initial_balance=1000.0):
        super().__init__()
        self.code_str = code_str
        self.risk_percent = risk_percent
        self.martingale_factor = martingale_multiplier
        self.balance = initial_balance
        self.base_bet = self.balance * (self.risk_percent / 100.0)
        self.current_bet = self.base_bet
        
        # Compile user code
        # We expect a class "MyStrategy" with a "next" method or similar simple function
        # For simplicity, let's wrap the code in a local scope
        self.user_scope = {}
        
        # Inject common libraries
        user_globals = {}
        try:
            import numpy as np
            user_globals['np'] = np
            user_globals['numpy'] = np
        except ImportError: pass
        
        try:
            import pandas as pd
            user_globals['pd'] = pd
            user_globals['pandas'] = pd
        except ImportError: pass

        try:
            exec(code_str, user_globals, self.user_scope)
            self.user_class = self.user_scope.get('MyStrategy')()
        except Exception as e:
            print(f"Strategy Compilation Error: {e}")
            self.user_class = None

    def next(self, candle):
        if not self.user_class: return
        
        try:
            # Re-calculate base bet based on new balance if needed?
            # User said: "place 1% of the trading fund as base amount"
            # Usually strict martingale keeps base static until full reset.
            # But "1% of trading fund" implies dynamic sizing.
            # Let's keep base bet dynamic based on current balance ONLY on reset.
            
            signal = self.user_class.next(candle)
            
            if signal == "CALL":
                self.buy(candle['close'], candle['time'])
            elif signal == "PUT":
                self.sell(candle['close'], candle['time'])
                
        except Exception as e:
            print(f"Strategy Execution Error: {e}")

    def on_win(self, trade):
        # Reset to Base Amount (1% of NEW balance)
        self.base_bet = self.balance * (self.risk_percent / 100.0)
        self.current_bet = self.base_bet

    def on_loss(self, trade):
        # Martingale Catchup
        self.current_bet *= self.martingale_factor

class LiveEngine:
    def __init__(self, callback):
        self.running = False
        self.callback = callback # Async function
        self.thread = None
        self.strategy = None
        self.mode = "FORWARD_TEST"
        self.logs = collections.deque(maxlen=50) # Keep persistent logs
        self.config = {}
        
        # Auto Asset Selection
        self.auto_select = False
        self.ranked_assets = []
        self.consecutive_losses = 0
        self.current_asset_index = 0
        self.switch_asset_flag = False

    def toggle_auto_select(self, enabled: bool):
        self.auto_select = enabled
        self._emit_log(f"Auto Asset Selection: {'ON' if enabled else 'OFF'}", "text-purple-400")
        if enabled and not self.ranked_assets:
             # Initial Fetch
             threading.Thread(target=self._refresh_assets, daemon=True).start()

    def _refresh_assets(self):
        self._emit_log("Auto Select: Ranking Assets...", "text-slate-400")
        try:
            assets = get_best_forex_asset()
            if assets:
                self.ranked_assets = assets
                self._emit_log(f"Assets Ranked: {len(assets)} found. Top: {assets[0]}", "text-blue-300")
                # Send to UI?
                self._emit_data({"type": "ranked_assets", "assets": assets})
            else:
                self._emit_log("Auto Select: No assets found.", "text-orange-400")
        except Exception as e:
            self._emit_log(f"Auto Select Error: {e}", "text-red-400")

    def _trigger_switch_asset(self):
        if not self.ranked_assets:
             self._refresh_assets()
             return # Wait for next trigger or immediate async?
             
        self.current_asset_index += 1
        if self.current_asset_index >= len(self.ranked_assets):
             self.current_asset_index = 0
             self._refresh_assets() # Refresh list on cycle complete
        
        next_asset = self.ranked_assets[self.current_asset_index]
        self._emit_log(f"📉 4 Losses Reached. Switching to {next_asset}...", "text-yellow-400")
        
        # Set new asset and flag restart
        self.asset = next_asset
        self.switch_asset_flag = True

    def get_state(self):
        return {
            "type": "state",
            "running": self.running,
            "config": self.config,
            "logs": list(self.logs)
        }
    
    def start(self, asset="EURUSD_otc", timeframe=5, expiry=60, mode="FORWARD_TEST", code=None, risk_percent=1.0, martingale_multiplier=2.0):
        if self.running: return
        
        self.asset = asset
        self.timeframe = timeframe
        self.expiry = expiry
        self.mode = mode
        self.code = code
        self.risk_percent = risk_percent
        self.risk_percent = risk_percent
        self.martingale_multiplier = martingale_multiplier
        
        # Reset Auto Select State on Start
        self.consecutive_losses = 0
        self.switch_asset_flag = False
        if self.auto_select:
             threading.Thread(target=self._refresh_assets, daemon=True).start()
        
        self.config = {
            "asset": asset,
            "timeframe": timeframe,
            "expiry": expiry,
            "mode": mode,
            "risk": risk_percent
        }
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            
    def _run_loop(self):
        if subscribe_symbol_timed is None:
            self._emit_log("Error: ChipaPocketOptionData library not found.", "text-red-500")
            return

        # Initialize Strategy
        if self.code:
            self.strategy = DynamicStrategy(self.code, self.risk_percent, self.martingale_multiplier)
            self._emit_log("Forward Test Started with Custom Strategy", "text-emerald-400")
        else:
            self.strategy = MyLiveStrategy() # Fallback
            self._emit_log("Forward Test Started with Default Strategy", "text-blue-400")
        
        # Configure Strategy Expiry & Hook
        self.strategy.expiry = self.expiry
        self.strategy.set_signal_callback(self._on_strategy_signal)
        
        # Override _place_trade method if in Publish Mode
        if self.mode == "PUBLISH":
             original_place_trade = self.strategy._place_trade
             def publish_trade_wrapper(direction, price, time):
                 # Call original to keep Sim stats updated
                 trade = original_place_trade(direction, price, time)
                 # Log Real Trade attempt
                 self._emit_log(f"*** REAL TRADE: {direction} ${self.strategy.current_bet} @ {price} ***", "text-orange-400 font-bold")
                 # Here we would call the actual API: client.buy(...)
                 return trade
             self.strategy._place_trade = publish_trade_wrapper

        self._emit_log(f"Config: {self.mode}, {self.timeframe}s Bar, {self.expiry}s Expiry", "text-slate-400")

        # Load SSID (omitted for brevity, assume same logic as before or simplified)
        ssid = None 
        # ... (Include existing SSID loading logic here or assume it's set) ...
        # For brevity in this diff, I'm just reusing the file reading logic quickly:
        possible_paths = ["ssid.txt", os.path.join(workspace_root, "ssid.txt"), os.path.join(workspace_root, "live_backtrader", "ssid.txt")]
        for p in possible_paths:
            if os.path.exists(p):
                with open(p, "r") as f: ssid = f.read().strip()
                if ssid: break
        if not ssid: ssid = '42["auth",{"session":"m9n4q60krjrojb1elm1g171tff","isDemo":1,"uid":120824712,"platform":2,"isFastHistory":true,"isOptimized":true}]'

        ssids = [ssid]
        
        # --- DEDICATED LOOP FOR REAL TRADING ---
        # We need a running loop to execute async broker methods.
        # The main thread is blocked by the candle generator loop most of the time.
        self.real_trade_loop = asyncio.new_event_loop()
        t_trade_loop = threading.Thread(target=self.real_trade_loop.run_forever, daemon=True)
        t_trade_loop.start()
        self._emit_log("Started Real Trading Logic Thread", "text-slate-500")

        # --- FORWARD TEST TRADING SETUP ---
        if self.mode == "FORWARD_TEST" and PocketOptionAsync:
             self._emit_log("Initializing Real Trader for Forward Test...", "text-blue-400")
             
             async def _init_trader_async():
                 try:
                     self.trader = PocketOptionAsync(ssid)
                     # Retry loop for balance to ensure valid connection
                     for i in range(10):  # Retry for up to 20 seconds
                        try:
                            bal = await self.trader.balance()
                            if isinstance(bal, (int, float)) and bal > 0:
                                 self._emit_log(f"Real Trader Connected. Balance: {bal}", "text-emerald-400")
                                 return True
                            self._emit_log(f"Waiting for valid balance... (Current: {bal})", "text-yellow-400")
                        except Exception as inner_e:
                             self._emit_log(f"Balance check error: {inner_e}", "text-orange-400")
                        
                        await asyncio.sleep(2)
                     
                     self._emit_log(f"Real Trader Init Warning: Balance unavailable or zero ({bal}). Proceeding anyway.", "text-orange-400")
                     return True
                 except Exception as e:
                     self._emit_log(f"Real Trader Connection Failed: {e}", "text-red-500")
                     return False

             # Run Init
             future = asyncio.run_coroutine_threadsafe(_init_trader_async(), self.real_trade_loop)
             try:
                 # Wait for init
                 future.result(timeout=10)
             except Exception as e:
                 self._emit_log(f"Real Trader Init Timed Out/Failed: {e}", "text-red-500")
                 # Proceed anyway, but the trader might not be ready yet.
             
             # Override _place_trade (ALWAYS, so we can trade when it connects later)
             original_place_trade = self.strategy._place_trade
             
             def forward_trade_wrapper(direction, price, time):
                 # 1. Internal Sim
                 t = original_place_trade(direction, price, time)
                 
                 # SAFETY: Do NOT execute real trades during WARMUP (History Loading)
                 if getattr(self, 'skip_real_trades', False):
                      return t

                 # 2. Real Execution
                 amount = self.strategy.current_bet
                 asset_name = self.asset
                 duration = self.expiry
                 
                 async def execute_real_trade():
                     # Check if trader is ready
                     if not hasattr(self, 'trader') or not self.trader: 
                         self._emit_log(" >> Real Trade Skipped: Trader not initialized.", "text-yellow-500")
                         return
                     
                     try:
                         # Ensure valid balance before trading? (Optional, maybe assume if trader object exists it's ok)
                         # We can just try-catch the trade
                         
                         action = direction.lower()
                         self._emit_log(f" >> PLACING REAL TRADE: {action.upper()} ${amount} ({duration}s)", "text-orange-400 font-bold")
                         
                         trade_result = None
                         if action == 'call':
                             if hasattr(self.trader, 'call'):
                                 trade_result = await self.trader.call(asset_name, amount, duration, check_win=False)
                             else:
                                 trade_result = await self.trader.buy(asset_name, amount, duration, check_win=False)
                         elif action == 'put':
                             if hasattr(self.trader, 'put'):
                                 trade_result = await self.trader.put(asset_name, amount, duration, check_win=False)
                             else:
                                 trade_result = await self.trader.sell(asset_name, amount, duration, check_win=False)
                             
                         if trade_result:
                             # API generally returns (trade_id, info) OR just info if it failed? 
                             # BinaryOptionsToolsV2 usually returns (id, bool/dict)
                             # Let's handle tuple unpacking carefully
                             trade_id = None
                             if isinstance(trade_result, tuple):
                                 trade_id = trade_result[0]
                             elif isinstance(trade_result, (str, int)):
                                 trade_id = trade_result
                                 
                             if trade_id:
                                 self._emit_log(f" >> Trade Placed. ID: {trade_id}", "text-emerald-400")
                                 
                                 # Monitor
                                 await asyncio.sleep(duration + 2)
                                 
                                 win_res = {'result': 'unknown'}
                                 for _ in range(5):
                                     try:
                                         win_res = await self.trader.check_win(trade_id)
                                         print(win_res)
                                         if win_res.get('result') in ['win', 'loss']:
                                              break
                                     except: pass
                                     await asyncio.sleep(2)
                                 
                                 final_status = win_res.get('result', 'unknown')
                                 profit = win_res.get('profit', 0)
                                 color = "text-emerald-400" if final_status == 'win' else "text-rose-400"
                                 self._emit_log(f" >> REAL RESULT: {final_status.upper()} (${profit})", color)
                             else:
                                  self._emit_log(f" >> Trade placement invalid result: {trade_result}", "text-red-400")
                         else:
                             self._emit_log(" >> Trade Placement Failed (None Result)", "text-red-400")

                     except Exception as e:
                         self._emit_log(f" >> Trade Logic Error: {e}", "text-red-500")

                 # Schedule on REAL TRADER loop
                 asyncio.run_coroutine_threadsafe(execute_real_trade(), self.real_trade_loop)
                 return t

             self.strategy._place_trade = forward_trade_wrapper
             self._emit_log("Real Trading Enabled (Async Hook).", "text-emerald-400")

        loop = asyncio.new_event_loop()


        asyncio.set_event_loop(loop)
        
        # --- HISTORY FETCHING ---
        try:
            from ChipaPocketOptionData import get_candles
            self._emit_log("Fetching last 1 hour history...", "text-blue-400")
            history = get_candles(self.asset, self.timeframe, 3600, ssids)
            
            if history:
                 # Normalize Keys: Ensure 'time' exists
                 for h in history:
                     if 'time' not in h and 'timestamp' in h:
                         h['time'] = h['timestamp']
                 
                 # Filter out malformed candles
                 history = [h for h in history if 'time' in h]
                 history.sort(key=lambda x: x['time'])
                 
                 # Emit history to frontend
                 self._emit_data({
                     "type": "history",
                     "data": history
                 })
                 
                 # If SIMULATION MODE: The 'History' IS the test.
                 if self.mode == "SIMULATION":
                      self._emit_log(f"Starting Simulation on {len(history)} candles...", "text-purple-400")
                      
                      for h_candle in history:
                           if not self.running: break
                           c = {
                              'time': h_candle['time'],
                              'open': h_candle['open'],
                              'high': h_candle['high'],
                              'low': h_candle['low'],
                              'close': h_candle['close'],
                              'volume': h_candle.get('volume', 0),
                              'timestamp': h_candle['time']
                           }
                           # Update trades (simulate expiry for PREVIOUS trades)
                           self.strategy.update_trades(c['close'], c['time'])
                           # Execute Strategy
                           self.strategy.next(c)
                           # Small delay to visualize?
                           pass 
                      
                      self._emit_log("Simulation Complete.", "text-yellow-400")
                      self.running = False
                      return 

                 # NORMAL MODES: Warmup
                 self._emit_log(f"Warming up strategy with {len(history)} candles...", "text-purple-400")
                 self.skip_real_trades = True # DISABLE Real Trading
                 start_balance = self.strategy.balance
                 self.strategy.set_signal_callback(None) # Disable live signals during warmup
                 
                 for h_candle in history:
                      c = {
                          'time': h_candle['time'],
                          'open': h_candle['open'],
                          'high': h_candle['high'],
                          'low': h_candle['low'],
                          'close': h_candle['close'],
                          'volume': h_candle.get('volume', 0),
                          'timestamp': h_candle['time']
                      }
                      self.strategy.next(c)
                 
                 # Re-enable signals
                 self.strategy.time_offset = 0
                 self.strategy.set_signal_callback(self._on_strategy_signal)
                 # Reset balance/stats
                 self.strategy.balance = start_balance 
                 self.strategy.trades = []
                 self.strategy.wins = 0
                 self.strategy.losses = 0
                 self.skip_real_trades = False # ENABLE Real Trading
                 self._emit_log("History processed. Strategy ready.", "text-emerald-400")

        except ImportError:
            self._emit_log("Function 'get_candles' not found. Skipping history.", "text-orange-400")
        except Exception as e:
            self._emit_log(f"History fetch failed: {e}", "text-red-400")
            if self.mode == "SIMULATION":
                self._emit_log("Simulation aborted due to no history.", "text-red-500")
                self.running = False
                return

        self._emit_log(f"Connecting to {self.asset} (1s Feed -> {self.timeframe}s Candles)...", "text-blue-400")
        
        # OUTER LOOP for ASSET SWITCHING
        while self.running:
            try:
                # Update Asset Log
                self._emit_log(f"Feed: {self.asset}...", "text-blue-500")
                
                # Re-fetch history for new asset?
                if self.mode != "SIMULATION": # Avoid disrupting simulation loop
                    try:
                        from ChipaPocketOptionData import get_candles
                        # Just fetch small context (e.g. 50 candles) to warm up indicators
                        self._emit_log(f"Fetching context for {self.asset}...", "text-slate-500")
                        history = get_candles(self.asset, self.timeframe, 300, ssids) 
                        # ... logic to pump history into strategy ...
                        if history and self.strategy:
                            # Pump into strategy without trading
                            self.skip_real_trades = True
                            cb_backup = self.strategy.on_signal
                            self.strategy.set_signal_callback(None)
                            for h in history:
                                if 'timestamp' in h: h['time'] = h['timestamp']
                                if 'time' in h: 
                                    self.strategy.next(h)
                            self.strategy.set_signal_callback(cb_backup)
                            self.skip_real_trades = False
                    except: pass

                with subscribe_symbol_timed(self.asset, 1, ssids=ssids) as collector:
                    self._emit_log("Data Feed Active. Aggregating candles...", "text-emerald-300")
                    
                    time_offset = None
                    current_candle = None
                    last_processed_ts = 0
                    
                    for raw_candle in collector:
                        if not self.running: break
                        
                        raw_ts = int(raw_candle['timestamp'])
                        raw_close = raw_candle['close']
                        raw_vol = raw_candle.get('volume') or 0 
                        
                        # FILTER: Strict Time Ordering
                        # Reject duplicate or late ticks to maintain deterministic state
                        if raw_ts <= last_processed_ts:
                            continue
                        last_processed_ts = raw_ts
                        
                        # 1. Sync Time Offset (Once)
                        if time_offset is None:
                            server_utc = datetime.fromtimestamp(raw_ts, tz=UTC)
                            local_utc_now = datetime.now(tz=UTC)
                            time_offset = (local_utc_now - server_utc).total_seconds()
                            
                        # 2. Determine Candle Bucket (Flooring)
                        candle_start_time = (raw_ts // self.timeframe) * self.timeframe
                        
                        # 3. Handle Candle Logic
                        
                        # Case A: Initialize First Candle
                        if current_candle is None:
                            current_candle = {
                                'time': candle_start_time,
                                'open': raw_candle['open'],
                                'high': raw_candle['high'],
                                'low': raw_candle['low'],
                                'close': raw_close,
                                'volume': raw_vol,
                                'timestamp': candle_start_time
                            }
                        
                        # Case B: New Candle Boundary Detected
                        elif candle_start_time != current_candle['time']:
                            # The bucket has changed. Finalize the OLD candle.
                            final_candle = current_candle
                            
                            # --- STRATEGY EXECUTION (On Close) ---
                            completed_trades = self.strategy.update_trades(final_candle['close'], final_candle['time'])
                            
                            # Process Auto Switch Logic
                            if self.auto_select and completed_trades:
                                for t in completed_trades:
                                    if t['result'] == 'LOSS':
                                        self.consecutive_losses += 1
                                        self._emit_log(f"Loss #{self.consecutive_losses}", "text-rose-500")
                                        if self.consecutive_losses >= 4:
                                                self._trigger_switch_asset()
                                    elif t['result'] == 'WIN':
                                        self.consecutive_losses = 0
                            
                            # Execute 'next' logic on the COMPLETED candle
                            self.strategy.next(final_candle)
                            
                            # --- LOGGING & STATS ---
                            ist_time = (datetime.fromtimestamp(final_candle['time'], tz=UTC) + timedelta(seconds=time_offset)).astimezone(IST)
                            self._emit_log(f"Closed Candle: {final_candle['close']} @ {ist_time.strftime('%H:%M:%S')}", "text-slate-500")

                            # Emit Stats (Balance, WinRate, etc.)
                            stats = {
                                "balance": self.strategy.balance,
                                "winRate": 0,
                                "totalTrades": self.strategy.wins + self.strategy.losses,
                                "currentBet": self.strategy.current_bet
                            }
                            if stats['totalTrades'] > 0:
                                stats['winRate'] = round((self.strategy.wins / stats['totalTrades']) * 100, 2)
                            self._emit_data({"type": "stats", **stats})
                            
                            # --- START NEW CANDLE ---
                            current_candle = {
                                'time': candle_start_time,
                                'open': raw_candle['open'], 
                                'high': raw_candle['high'],
                                'low': raw_candle['low'],
                                'close': raw_close,
                                'volume': raw_vol,
                                'timestamp': candle_start_time
                            }
                            
                        # Case C: Update Existing Candle
                        else:
                            current_candle['high'] = max(current_candle['high'], raw_candle['high'])
                            current_candle['low'] = min(current_candle['low'], raw_candle['low'])
                            current_candle['close'] = raw_close
                            current_candle['volume'] += raw_vol
                        
                        # 4. Emit Real-Time Update
                        server_utc = datetime.fromtimestamp(current_candle['time'], tz=UTC)
                        corrected_utc = server_utc + timedelta(seconds=time_offset)
                        time_str = corrected_utc.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
                        
                        self._emit_data({
                            "type": "candle",
                            "data": {
                                "time": current_candle["time"],
                                "open": current_candle["open"],
                                "high": current_candle["high"],
                                "low": current_candle["low"],
                                "close": current_candle["close"],
                                "dateStr": time_str
                            }
                        })

                        # Check for Switch Flag inside the loop
                        if self.switch_asset_flag:
                            self.switch_asset_flag = False
                            self._emit_log(f"Switching Asset Context now...", "text-yellow-500")
                            break # Break inner loop to restart with new asset

            except Exception as e:
                self._emit_log(f"Runtime Error: {e}", "text-red-500")
                print(f"Error: {e}")
                # Prevent rapid loop on error
                import time
                time.sleep(5)
                
            finally:
                # Check if we should really stop or just restarting
                if not self.running:
                    self._emit_log("Test Stopped.", "text-yellow-500")
                    # Cleanup Trade Loop
                    if hasattr(self, 'real_trade_loop') and self.real_trade_loop.is_running():
                        self.real_trade_loop.call_soon_threadsafe(self.real_trade_loop.stop)





    def _emit_data(self, data):
        asyncio.run_coroutine_threadsafe(self.callback(data), self.loop)

    def _emit_log(self, message, color="text-slate-300"):
        log_entry = {
            "type": "log",
            "message": message,
            "color": color
        }
        self.logs.append(log_entry)
        self._emit_data(log_entry)

    @property
    def loop(self):
        # We need the main loop to run the async callback
        return self._main_loop

    def _on_strategy_signal(self, signal_data):
        """Callback for strategy signals."""
        self._emit_data({
            "type": "signal",
            "data": signal_data
        })
        # Determine color
        color = "text-emerald-400" if signal_data['direction'] == "CALL" else "text-rose-400"
        self._emit_log(f"SIGNAL: {signal_data['direction']} @ {signal_data['price']}", color)

# Helper to manage the single instance
engine_instance = None

def get_live_engine(callback, main_loop):
    global engine_instance
    if engine_instance is None:
        engine_instance = LiveEngine(callback)
        engine_instance._main_loop = main_loop
    # Update callback/loop if needed or just return
    # If connection drops and reconnects, we might update callback
    engine_instance.callback = callback
    engine_instance._main_loop = main_loop
    return engine_instance
