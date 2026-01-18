import asyncio
import json
import logging
import re
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone, timedelta
from asset_selector import get_best_forex_asset
import logging
import re
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone, timedelta

# Configure logging
logger = logging.getLogger("TelegramSignalTrader")
logger.setLevel(logging.INFO)

# File handler to write to 'trader.log', overwriting each time
file_handler = logging.FileHandler('trader.log', mode='w', encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(file_formatter)

# Clear existing handlers to avoid duplicates (if reloading)
if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(file_handler)
logger.addHandler(console_handler)

class TelegramSignalTrader:
    """
    Processes Telegram messages and executes trades across multiple brokers.
    """
    def __init__(self):
        """
        Initialize the trader settings and load assets.
        """
        self.assets = self._load_assets()
        self.brokers: List[Dict[str, Any]] = []
        
        # Internal State
        self.current_asset: Optional[str] = None
        self.current_timeframe_sec: Optional[int] = None
        self.in_catchup: bool = False
        self.pending_catchup_signal: Optional[Dict] = None  # Stores recent catchup instructions
        
        # Store recent messages for UI
        from collections import deque
        self.last_messages = deque(maxlen=10)
        
        # Session Control
        self.trading_active: bool = False
        
        # Auto Asset Selection
        self.auto_select_enabled: bool = False
        self.ranked_assets: List[str] = []
        self.consecutive_losses: int = 0
        self.current_asset_index: int = 0

    def _load_assets(self) -> List[str]:
        """Loads assets.json from the current directory."""
        try:
            with open("assets.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error("assets.json not found!")
            return []
        except json.JSONDecodeError:
            logger.error("Error decoding assets.json")
            return []

    def add_broker(self, ssid: str, api_client, percentage: float, fixed_amount: float = None):
        """
        Registers a broker/account to trade on.
        
        Args:
            ssid: The raw SSID string (used for identification).
            api_client: The async API client.
            percentage: Percentage of balance to use for initial trade.
            fixed_amount: Optional fixed amount to use instead of percentage.
        """
        self.brokers.append({
            "ssid": ssid,
            "api": api_client,
            "percentage": float(percentage),
            "fixed_amount": float(fixed_amount) if fixed_amount else None,
            "current_amount": None,
            "base_amount": None,
            "last_trade_id": None
        })
        desc = f"{fixed_amount} fixed" if fixed_amount else f"{percentage}%"
        logger.info(f"Added broker for SSID {ssid[:10]}... with {desc} trade size")

    async def clear_brokers(self):
        """Disconnects and clears all registered brokers."""
        logger.info(f"Clearing {len(self.brokers)} brokers...")
        for broker in self.brokers:
            api = broker.get('api')
            if api and hasattr(api, 'disconnect'):
                try:
                    await api.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting broker: {e}")
        self.brokers = []

    def get_status(self):
        """Returns current state for UI."""
        return {
            'asset': self.current_asset,
            'timeframe': self.current_timeframe_sec,
            'trading_active': self.trading_active,
            'messages': list(self.last_messages),
            'balance': self.brokers[0].get('last_balance') if self.brokers else None,
            'auto_select': self.auto_select_enabled,
            'ranked_assets': self.ranked_assets
        }

    async def toggle_auto_asset_selection(self, enabled: bool):
        """Turn auto asset selection on/off."""
        self.auto_select_enabled = enabled
        logger.info(f"Auto Asset Selection set to: {enabled}")
        
        if enabled:
            # Initial Ranking
            await self._refresh_ranked_assets()

    async def _refresh_ranked_assets(self):
        """Runs the asset selector logic."""
        logger.info("🔄 Running Auto Asset Selection (Ranking)...")
        # Run in executor to avoid blocking
        loop = asyncio.get_running_loop()
        try:
            new_assets = await loop.run_in_executor(None, get_best_forex_asset)
            if new_assets:
                self.ranked_assets = new_assets
                self.current_asset_index = 0
                self.current_asset = self.ranked_assets[0]
                self.consecutive_losses = 0
                logger.info(f"🏆 Top Asset Selected: {self.current_asset}")
                
                # "Get 1 hour historic data" - Fetch for the new asset to ensure data availability/logging
                await self._fetch_history_for_asset(self.current_asset)
            else:
                logger.warning("⚠️ Asset Selector returned no assets. Keeping current.")
        except Exception as e:
            logger.error(f"Failed to refresh assets: {e}")

    async def _fetch_history_for_asset(self, asset):
        """Fetches 1h historic data as requested during switch."""
        if not self.brokers: return
        try:
            # Just use first broker to fetch
            api = self.brokers[0]['api']
            if hasattr(api, 'get_candles'):
                logger.info(f"📥 Fetching historic data for {asset}...")
                candles = await api.get_candles(asset, period=60, count=60)
                logger.info(f"   > Fetched {len(candles)} candles.")
        except Exception as e:
            logger.warning(f"Failed to fetch history: {e}")

    def set_trading_session(self, active: bool):
        """Manually set trading session status."""
        self.trading_active = active
        status = "ACTIVE 🟢" if active else "INACTIVE 🔴"
        logger.info(f"Manual Session Override: {status}")

    async def _execute_trade(self, direction, is_catchup=False, duration=None):
        """
        Executes trade on all brokers.
        """
        logger.info(f"⚡ Executing trade: {direction} (Catchup: {is_catchup}, Time: {duration}) | Brokers: {len(self.brokers)}")
        if not self.brokers:
            logger.error("❌ No brokers registered! Cannot trade.")
            return

        tasks = []
        for i, broker in enumerate(self.brokers):
            logger.info(f"  > queuing broker {i}")
            # Use specific duration if provided, else fallback to global (handled inside _trade_broker if None passed)
            use_duration = duration if duration else self.current_timeframe_sec
            tasks.append(self._trade_broker(broker, direction, is_catchup, duration=use_duration))
        
        await asyncio.gather(*tasks)

    async def _trade_broker(self, broker, direction, is_catchup, duration=None):
        """
        Executes a trade on a specific broker.
        If duration is None, uses self.current_timeframe_sec (or falls back to 60).
        """
        api = broker["api"]
        # Use provided duration, or fallback to global state, or default 60
        trade_time = duration if duration else (self.current_timeframe_sec or 60)

        try:
            # 1. Update Balance
            logger.info("  > Fetching balance...")
            balance = await api.balance() 
            logger.info(f"  > Balance raw response: {balance}")
            
            if balance is None:
                logger.error("❌ Could not fetch balance. Skipping.")
                return

            
            # 2. Update Balance Local State
            if isinstance(balance, (int, float)):
                 final_bal = float(balance)
            elif isinstance(balance, str):
                 try:
                     final_bal = float(balance)
                 except:
                     pass
            elif isinstance(balance, dict):
                 final_bal = float(balance.get('balance', 0))
            
            broker['last_balance'] = final_bal
            
            # 3. Calculate Amount
            if broker.get("fixed_amount"):
                base_calc = broker["fixed_amount"]
            else:
                base_calc = final_bal * (broker["percentage"] / 100.0)
            
            # Store base amount
            broker["base_amount"] = base_calc
            
            # Determine Amount based on Logic
            # "if previous trade is loss ... place catch up ... if win reset"
            
            last_res = broker.get('last_result', 'unknown')
            last_amt = broker.get('last_trade_amount', base_calc) or base_calc
            
            # Pure State-Based Logic:
            if last_res == 'loss':
                next_amount = last_amt * 2
                logger.info(f"  > Martingale Triggered (Last: LOSS): {last_amt:.2f} -> {next_amount:.2f}")
            elif last_res == 'tie':
                next_amount = last_amt
                logger.info(f"  > Tie Triggered (Last: TIE). Keeping Amount: {next_amount:.2f}")
            else:
                next_amount = base_calc
                if last_res == 'win':
                    logger.info(f"  > Reset Triggered (Last: WIN). Amount: {base_calc:.2f}")
                else:
                    logger.info(f"  > Base Amount (Last: {last_res}). Amount: {base_calc:.2f}")

            broker["current_amount"] = next_amount
            amount = next_amount
            
            # Validation
            if amount > final_bal:
                 logger.error(f"❌ Insufficient funds: {amount} > {final_bal}")
                 return
            
            logger.info(f"  > Placing {direction} trade for ${amount:.2f} on {self.current_asset} ({trade_time}s)")
            
            # 3. Execute Trade
            cmd = direction.lower()
            trade_id, trade_data = None, None
            
            # Use confirmed syntax: (id, data) = await api.buy(...)
            if cmd == 'call':
                 if hasattr(api, 'call'): # Just in case, though user said api.buy
                     trade_id, trade_data = await api.call(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=trade_time, 
                         check_win=False
                     )
                 elif hasattr(api, 'buy'):
                     trade_id, trade_data = await api.buy(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=trade_time, 
                         check_win=False
                     )
                 else:
                     logger.error("❌ API has no 'buy' method")
                     
            elif cmd == 'put':
                 if hasattr(api, 'put'):
                     trade_id, trade_data = await api.put(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=trade_time, 
                         check_win=False
                     )
                 elif hasattr(api, 'sell'):
                     trade_id, trade_data = await api.sell(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=trade_time, 
                         check_win=False
                     )
                 else:
                     logger.error("❌ API has no 'sell' method")
            
            if trade_id:
                logger.info(f"✅ Trade Placed! ID: {trade_id}")
                logger.info(f"   Data: {trade_data}")
                
                # Store trade info for next time
                broker['last_trade_amount'] = amount
                broker['last_result'] = 'pending' # Reset result until monitored

                # Start Monitoring the Result
                asyncio.create_task(
                    self._monitor_broker_result(broker, trade_id, trade_time)
                )

            else:
                logger.warning(f"⚠️ Trade executed but no ID returned (or failed)? Res: {trade_data}")
            
        except Exception as e:
            logger.error(f"❌ Trade failed for broker: {e}")
            import traceback
            traceback.print_exc()

    async def _switch_to_next_asset(self):
        """Switches to the next best asset in the rank list."""
        if not self.ranked_assets:
            await self._refresh_ranked_assets()
            return

        self.current_asset_index += 1
        if self.current_asset_index >= len(self.ranked_assets):
            logger.warning("⚠️ Cycled through ALL ranked assets! Re-ranking...")
            await self._refresh_ranked_assets()
            return
            
        next_asset = self.ranked_assets[self.current_asset_index]
        self.current_asset = next_asset
        # Reset consecutive losses for the new asset?
        # User said "continue again with the same catch up".
        # So we KEEP the Martingale state (don't reset broker['last_result']?) 
        # BUT we MUST process the switch.
        
        # We generally reset the *loss count for comparison* so we don't switch again immediately,
        # but we keep the *Trade Amount* logic (handled by broker['last_result']='loss').
        self.consecutive_losses = 0 
        
        logger.info(f"👉 Switched to Next Best Asset: {self.current_asset}")
        
        # "Clear existing chart and get 1 hour data"
        await self._fetch_history_for_asset(self.current_asset)

    async def _monitor_broker_result(self, broker, trade_id, duration):
        """
        Waits for trade expiry, checks win/loss, and handles catchup if needed.
        """
        wait_time = duration + 2  # Wait duration + small buffer
        logger.info(f"⏳ Monitoring trade {trade_id} (wait {wait_time}s)...")
        await asyncio.sleep(wait_time)
        
        api = broker["api"]
        ssid = broker.get("ssid", "unknown")
        
        try:
            # Poll for Result (up to 10s) to handle server latency
            result = 'unknown'
            profit = 0
            for attempt in range(5):
                check_data = await api.check_win(trade_id)
                print(check_data)
                result = check_data.get('result', 'unknown')
                profit = check_data.get('profit', 0)
                
                if result in ['win', 'loss']:
                    break
                
                logger.debug(f"Trade result pending/unknown ({result}). Retrying...")
                await asyncio.sleep(2)
            
            logger.info(f"🔎 Trade Finished [SSID: {ssid[:5]}] -> Result: {result}, Profit: {profit}")
            
            # Logic: Just Update State for next Trade
            is_win = (result == 'win') or (isinstance(profit, (int, float)) and profit > 0)
            is_loss = (result == 'loss') or (isinstance(profit, (int, float)) and profit < 0)
            
            # Detect Tie/Break-even
            # If result is not 'win' and profit is 0 (meaning we got money back or 0 change relative to entry for some brokers)
            # Standard PocketOption behavior: Tie = Payout 0? No, usually payout=amount. Profit=0 implies net 0.
            # We assume profit is "net profit" (payout - amount). 
            # If profit is 0, it's a tie (or strict break even).
            is_tie = (not is_win and not is_loss) and (profit == 0 or result == 'tie')

            # Fallback
            if not is_win and not is_loss and not is_tie and result == 'loss':
                is_loss = True

            if is_win:
                broker['last_result'] = 'win'
                logger.info(f"  Step Result: WIN. Next catchup will RESET amount.")
                
            elif is_loss:
                broker['last_result'] = 'loss'
                logger.info(f"  Step Result: LOSS. Next catchup will DOUBLE amount.")
                
                # Track consecutive losses for Auto Selection
                if self.auto_select_enabled:
                    self.consecutive_losses += 1
                    logger.info(f"  📉 Consecutive Losses: {self.consecutive_losses}/4")
                    
                    if self.consecutive_losses >= 4:
                        logger.info("  ⚠️ 4 Losses Reached! Switching Asset...")
                        await self._switch_to_next_asset()

            elif is_tie:
                broker['last_result'] = 'tie'
                logger.info(f"  Step Result: TIE. Next catchup will REPEAT amount.")
                    
            else:
                 broker['last_result'] = 'unknown' # Tie or error
                 logger.info(f"  Step Result: {result}. State indeterminate.")
            
            # Update Balance After Trade Result
            try:
                new_bal = await api.balance()
                logger.info(f"  > Balance Broker Update: {new_bal}")
                if new_bal is not None:
                    if isinstance(new_bal, (int, float)):
                        broker['last_balance'] = float(new_bal)
                    elif isinstance(new_bal, dict):
                        broker['last_balance'] = float(new_bal.get('balance', 0))
            except Exception as e:
                logger.error(f"Failed to fetch balance after trade: {e}")

        except Exception as e:
            logger.error(f"Error checking trade result: {e}")
            import traceback
            traceback.print_exc()

    async def handle_message(self, message_data) -> None:
        """
        Process an incoming Telegram message.
        """
        # (Imports moved to top)
        
        text = ""
        msg_date = None
        msg_id = None
        
        # 1. Parse Input Data
        if isinstance(message_data, dict):
            text = message_data.get('raw', '').strip()
            msg_id = message_data.get('id')
            date_str = message_data.get('date')
            try:
                if date_str:
                    msg_date = datetime.fromisoformat(str(date_str))
            except Exception as e:
                logger.warning(f"Could not parse message date: {e}")
        else:
            text = str(message_data).strip()

        logger.info(f"Received message: {text}")

        # 2. STATE CHECK & DEDUPLICATION (User Request)
        # "Wait for new telegram signal... use some variable state"
        if msg_id:
            # We use a primitive 'last_id' state to ensure we process each unique message exactly once
            if getattr(self, 'last_processed_id', None) == msg_id:
                logger.warning(f"🔄 Ignoring DUPLICATE message ID: {msg_id} (Already processed)")
                return
            self.last_processed_id = msg_id
        
        # 3. Check for Stale Message (Time Validation)
        if msg_date:
            now_utc = datetime.now(timezone.utc)
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            
            age = (now_utc - msg_date).total_seconds()
            if age > 120:
                logger.warning(f"⚠️ Ignoring STALE message! Age: {age:.1f}s. Date: {msg_date}")
                return

        # Store message for UI
        self.last_messages.appendleft({
            'time': datetime.now().strftime('%H:%M:%S'),
            'text': text,
            'asset': self.current_asset,
            'timeframe': self.current_timeframe_sec
        })

        # --- SESSION CONTROL ---
        text_upper = text.upper()
        
        # Start Pattern
        # "Settings for opening trades"
        if "SETTINGS FOR OPENING TRADES" in text_upper:
             self.trading_active = True
             logger.info("🟢 TRADING SESSION STARTED via Settings Message")
             # Try to parse timeframe from this start message as requested
             start_tf = self._parse_timeframe(text)
             if start_tf:
                 self.current_timeframe_sec = start_tf
                 logger.info(f"   > Initial Timeframe set to {start_tf}s from settings")
        
        # Stop Pattern
        # "Balance after trading"
        if "BALANCE AFTER TRADING" in text_upper:
             self.trading_active = False
             logger.info("🔴 TRADING SESSION ENDED via Balance Message")
             return

        # REMOVED: Early return for inactive session, so we can listen to "Asset/Timeframe" even when off.

        # 4. Try Parse Catch-Up (Martingale) - PRIORITY
        if "CATCH UP" in text.upper():
            catchup = self._parse_catchup(text)
            if catchup:
                direction, time_sec = catchup
                # Execute IMMEDIATELY as a Conditional Trade
                # is_catchup=True signals _trade_broker to check 'last_result' and decide amount
                if self.trading_active:
                    await self._execute_trade(direction, is_catchup=True, duration=time_sec)
                else:
                    logger.info("🚫 Session Inactive: Skipping Catch-up Trade")
            else:
                logger.warning("Message contained 'CATCH UP' but failed to parse direction.")
            return


        # 5. RESULT/STATUS FILTER (Prevent False Trades)
        # Avoid triggering "UP" from "UP WON" or "AUD/USD RESULT"
        result_keywords = ["WIN", "WON", "PROFIT", "ITM", "OTM", "ATM", "✅", "❌", "RESULT"]
        text_upper = text.upper()
        
        is_result = any(k in text_upper for k in result_keywords)
        if not is_result and re.search(r'\b(LOSS|LOST)\b', text_upper):
            is_result = True

        if is_result:
             logger.info(f"🛑 Ignoring Result/Status message: {text}")
             return

        # 6. Try Parse Timeframe
        timeframe = self._parse_timeframe(text)
        if timeframe:
            self.current_timeframe_sec = timeframe
            logger.info(f"Updated timeframe to {timeframe} seconds")
            return

        # 7. Try Parse Asset
        if text in self.assets:
            if("OTC" in text):
                text = text.replace("OTC", "otc")
                
            # If Auto Select is Enabled, DO NOT update asset from message
            if self.auto_select_enabled:
                logger.info(f"🔒 Auto Select Enabled: Ignoring asset change to {text}. Keeping {self.current_asset}")
            else:
                self.current_asset = text.replace(" ", "_").replace("/", "")
                logger.info(f"Updated asset to {self.current_asset}")
            return

        # 8. Try Parse Normal Direction
        direction = self._parse_direction(text)
        if direction:
            if not self.current_asset or not self.current_timeframe_sec:
                logger.warning("Received direction but missing asset or timeframe. Ignoring.")
                return
            
            self.in_catchup = False
            
            if self.trading_active:
                await self._execute_trade(direction, is_catchup=False)
            else:
                logger.info("🚫 Session Inactive: Skipping Normal Trade")
            # Trade placed (or skipped). State 'last_processed_id' prevents re-run of this same msg.
            return

        logger.info("Message ignored (no matching instruction)")


    def _parse_timeframe(self, text: str) -> Optional[int]:
        """
        Parses timeframe string to seconds.
        """
        # Simplify text: uppercased for consistent matching
        msg = text.upper()

        # Ignore "Candles M1", "Candles M5" etc
        msg = re.sub(r"CANDLES\s+M\d+", "", msg)

        # 1. Check for MM:SS format (e.g., "2:00", "01:30")
        match_colon = re.search(r"(\d+):(\d+)", msg)
        if match_colon:
            try:
                minutes = int(match_colon.group(1))
                seconds = int(match_colon.group(2))
                total_seconds = minutes * 60 + seconds
                if total_seconds > 0:
                    return total_seconds
            except ValueError:
                pass

        # 2. Check for explicit Minutes (e.g. "2 min", "3 MINS", "5 minutes", "1M")
        match_min = re.search(r"\b(\d+)\s*(MINUTES?|MINS?|M)\b", msg)
        if match_min:
            try:
                val = int(match_min.group(1))
                return val * 60
            except ValueError:
                pass

        # 3. Check for "M" prefix (e.g. "M1", "M5")
        match_m_prefix = re.search(r"\bM(\d+)\b", msg)
        if match_m_prefix:
            try:
                val = int(match_m_prefix.group(1))
                return val * 60
            except ValueError:
                pass
        
        # 5. Handle "1 second", "30 sec"
        match_sec = re.search(r"\b(\d+)\s*(SECONDS?|SEC|S)\b", msg)
        if match_sec:
           try:
               val = int(match_sec.group(1))
               return val
           except ValueError:
               pass

        return None

    def _parse_direction(self, text: str) -> Optional[str]:
        """Parses direction UP/DOWN using strict word boundaries."""
        t = text.upper()
        
        # Regex for strict UP/DOWN to avoid partial matches
        # Matches "UP", "CALL", "🔼"
        if re.search(r'\b(UP|CALL)\b|🔼', t):
            return "call"
        
        # Matches "DOWN", "PUT", "🔽"
        if re.search(r'\b(DOWN|PUT)\b|🔽', t):
            return "put"
            
        return None

    def _parse_catchup(self, text: str) -> Optional[Tuple[str, int]]:
        """Parses CATCH UP logic: returns (direction, time_sec)."""
        if "CATCH UP" not in text.upper():
            return None
            
        # Remove "CATCH UP" (case insensitive) and parse the rest
        # Example: "CATCH UP 3 min DOWN" -> " 3 min DOWN"
        remaining = re.sub(r'CATCH UP', '', text, flags=re.IGNORECASE).strip()
        
        # Find direction in the remaining text
        direction = self._parse_direction(remaining)
        if not direction:
            return None
            
        # Find timeframe in the remaining text
        time_sec = self._parse_timeframe(remaining)
        
        # If no time specified in catchup msg, we might return None.
        # But for safety, if parsed direction is valid, we return it.
        # The caller _execute_trade handles None duration by using current defaults.
        
        return (direction, time_sec)
