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

    def add_broker(self, api_client, percentage: float, fixed_amount: float = None):
        """
        Registers a broker/account to trade on.
        
        Args:
            api_client: The async API client.
            percentage: Percentage of balance to use for initial trade.
            fixed_amount: Optional fixed amount to use instead of percentage.
        """
        self.brokers.append({
            "api": api_client,
            "percentage": float(percentage),
            "fixed_amount": float(fixed_amount) if fixed_amount else None,
            "current_amount": None,
            "base_amount": None,
            "last_trade_id": None
        })
        desc = f"{fixed_amount} fixed" if fixed_amount else f"{percentage}%"
        logger.info(f"Added broker with {desc} trade size")

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
        logger.info(f"⚡ Executing trade: {direction} (Catchup: {is_catchup})")
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
    async def handle_message(self, text: str) -> None:
        """
        Process an incoming Telegram message.
        """
        text = text.strip()
        logger.info(f"Received message: {text}")

        # Store message for UI
        from datetime import datetime
        self.last_messages.appendleft({
            'time': datetime.now().strftime('%H:%M:%S'),
            'text': text,
            'asset': self.current_asset,
            'timeframe': self.current_timeframe_sec
        })

        # 1. Try Parse Timeframe
        timeframe = self._parse_timeframe(text)
        if timeframe:
            self.current_timeframe_sec = timeframe
            logger.info(f"Updated timeframe to {timeframe} seconds")
            return

        # 2. Try Parse Asset
        # Check if text is in our list of valid assets
        if text in self.assets:
            if("OTC" in text):
                text = text.replace("OTC", "otc")
                
            self.current_asset = text.replace(" ", "_").replace("/", "")
            logger.info(f"Updated asset to {self.current_asset}")
            return

        # 3. Try Parse Catch-Up (Martingale)
        catchup = self._parse_catchup(text)
        if catchup:
            direction, time_sec = catchup
            self.current_timeframe_sec = time_sec
            self.in_catchup = True
            
            # Double amounts for all brokers
            # For percentage based: we need to know the base first. 
            # If we are in catchup, we assume we continue from previous logic.
            # But here we just set a flag to double whatever the calculation results in?
            # Or we strictly double the *previous* traded amount?
            # Prompt: "Double current trade amount"
            # Since we calculate dynamic base, we'll handle doubling in _execute_trade
            
            logger.info(f"Catch-up signal! Direction: {direction}, Time: {time_sec}s")
            await self._execute_trade(direction, is_catchup=True)
            return

        # 4. Try Parse Normal Direction
        direction = self._parse_direction(text)
        if direction:
            if not self.current_asset or not self.current_timeframe_sec:
                logger.warning("Received direction but missing asset or timeframe. Ignoring.")
                return
            
            self.in_catchup = False
            await self._execute_trade(direction, is_catchup=False)
            return

        logger.info("Message ignored (no matching instruction)")


    def _parse_timeframe(self, text: str) -> Optional[int]:
        """
        Parses timeframe string to seconds.
        Supports: "2:00 minute", "2 min", "1MIN", "1:00", "M1", "3 minute", etc.
        """
        # Simplify text: uppercased for consistent matching
        msg = text.upper()

        # 1. Check for MM:SS format (e.g., "2:00", "01:30", "2:00 minute")
        # specific regex that finds digits:digits (capturing groups)
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
        # We look for number followed optionally by space then unit. 
        # \b ensures we don't match something weird inside a word, though strictly "1M" might be attached.
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
        
        # 4. Check for just number + " MIN" attached without space from cleaning?
        # The above regexes cover "1MIN" via \s*. 
        
        # 5. Handle "1 second", "30 sec" just in case user mentioned "1sec to 30 min"
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
        up_variants = ["UP", "🔼UP"]
        down_variants = ["DOWN", "DOWN🔽"]
        
        t = text.upper().replace(" ", "")
        
        # Iterate to check exact or partial matches if needed, but strict is safer
        # Prompt examples are exact strings.
        if any(v in t for v in up_variants):
            return "call" 
        if any(v in t for v in down_variants):
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
