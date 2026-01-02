import asyncio
import json
import logging
import re
from typing import List, Optional, Tuple, Dict, Any

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
        
        # Store recent messages for UI
        from collections import deque
        self.last_messages = deque(maxlen=10)

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
            'messages': list(self.last_messages)
        }

    async def _execute_trade(self, direction, is_catchup=False):
        """
        Executes trade on all brokers.
        """
        logger.info(f"⚡ Executing trade: {direction} (Catchup: {is_catchup}) | Brokers: {len(self.brokers)}")
        if not self.brokers:
            logger.error("❌ No brokers registered! Cannot trade.")
            return

        tasks = []
        for i, broker in enumerate(self.brokers):
            logger.info(f"  > queuing broker {i}")
            tasks.append(self._trade_broker(broker, direction, is_catchup))
        
        await asyncio.gather(*tasks)

    async def _trade_broker(self, broker, direction, is_catchup):
        api = broker["api"]
        try:
            # 1. Update Balance
            logger.info("  > Fetching balance...")
            balance = await api.balance() 
            logger.info(f"  > Balance raw response: {balance}")
            
            if balance is None:
                logger.error("❌ Could not fetch balance. Skipping.")
                return

            # Handle parsing if it returns a dict, but likely float based on tests
            final_bal = 0.0
            if isinstance(balance, (int, float)):
                final_bal = float(balance)
            elif isinstance(balance, str):
                try:
                    final_bal = float(balance)
                except:
                    pass
            elif isinstance(balance, dict):
                 final_bal = float(balance.get('balance', 0))
            
            # 2. Calculate Amount
            if broker.get("fixed_amount"):
                base_calc = broker["fixed_amount"]
            else:
                base_calc = final_bal * (broker["percentage"] / 100.0)
            
            # Store base amount
            broker["base_amount"] = base_calc
            
            if not is_catchup:
                broker["current_amount"] = base_calc
            else:
                if broker["current_amount"] is None:
                    broker["current_amount"] = base_calc * 2
                else:
                    broker["current_amount"] *= 2

            amount = broker["current_amount"]
            
            # Validation
            if amount > final_bal:
                 logger.error(f"❌ Insufficient funds: {amount} > {final_bal}")
                 return
            
            logger.info(f"  > Placing {direction} trade for ${amount:.2f} on {self.current_asset} ({self.current_timeframe_sec}s)")
            
            # 3. Execute Trade
            cmd = direction.lower()
            trade_id, trade_data = None, None
            
            # Use confirmed syntax: (id, data) = await api.buy(...)
            if cmd == 'call':
                 if hasattr(api, 'call'): # Just in case, though user said api.buy
                     trade_id, trade_data = await api.call(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=self.current_timeframe_sec, 
                         check_win=False
                     )
                 elif hasattr(api, 'buy'):
                     trade_id, trade_data = await api.buy(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=self.current_timeframe_sec, 
                         check_win=False
                     )
                 else:
                     logger.error("❌ API has no 'buy' method")
                     
            elif cmd == 'put':
                 if hasattr(api, 'put'):
                     trade_id, trade_data = await api.put(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=self.current_timeframe_sec, 
                         check_win=False
                     )
                 elif hasattr(api, 'sell'):
                     trade_id, trade_data = await api.sell(
                         asset=self.current_asset, 
                         amount=amount, 
                         time=self.current_timeframe_sec, 
                         check_win=False
                     )
                 else:
                     logger.error("❌ API has no 'sell' method")
            
            if trade_id:
                logger.info(f"✅ Trade Placed! ID: {trade_id}")
                logger.info(f"   Data: {trade_data}")
            else:
                logger.warning(f"⚠️ Trade executed but no ID returned (or failed)? Res: {trade_data}")
            
        except Exception as e:
            logger.error(f"❌ Trade failed for broker: {e}")
            import traceback
            traceback.print_exc()
    async def handle_message(self, message_data) -> None:
        """
        Process an incoming Telegram message.
        """
        from datetime import datetime, timezone, timedelta
        
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

        # 4. Try Parse Catch-Up (Martingale) - PRIORITY
        if "CATCH UP" in text.upper():
            catchup = self._parse_catchup(text)
            if catchup:
                direction, time_sec = catchup
                self.current_timeframe_sec = time_sec
                self.in_catchup = True
                
                logger.info(f"Catch-up signal! Direction: {direction}, Time: {time_sec}s")
                await self._execute_trade(direction, is_catchup=True)
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
            await self._execute_trade(direction, is_catchup=False)
            # Trade placed. State 'last_processed_id' prevents re-run of this same msg.
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

        # 2. Check for explicit Minutes (e.g. "2 min", "5 minutes", "1M")
        match_min = re.search(r"\b(\d+)\s*(MINUTES?|MIN|M)\b", msg)
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
        """Parses direction UP/DOWN."""
        t = text.upper()
        
        # Simple inclusion check as requested (not strict)
        if "UP" in t or "🔼" in t:
            return "call"
        if "DOWN" in t or "🔽" in t:
            return "put"
            
        return None

    def _parse_catchup(self, text: str) -> Optional[Tuple[str, int]]:
        """Parses CATCH UP logic: returns (direction, time_sec)."""
        if "CATCH UP" not in text.upper():
            return None
            
        # Remove "CATCH UP" and parse the rest
        # Example: "CATCH UP 2 min UP"
        remaining = text.upper().replace("CATCH UP", "").strip()
        
        # Find direction
        direction = self._parse_direction(remaining)
        if not direction:
            return None
            
        # Find timeframe in the *original* text strings (handle "2 min")
        # simpler to just pass the remaining text to _parse_timeframe
        time_sec = self._parse_timeframe(remaining)
        if not time_sec:
            # Fallback if timeframe not found in catchup message? 
            # Prompt says "Update timeframe from message". Implies it MUST be there.
            return None
            
        return (direction, time_sec)
