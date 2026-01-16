from typing import List, Dict, Optional
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
from app.data.candle_normalizer import CandleNormalizer
import logging
import asyncio

logger = logging.getLogger("PocketHistory")

from app.core.session_manager import session_manager

class PocketOptionHistory:
    def __init__(self, ssid: str = None):
        # We ignore the passed ssid mostly, trusting the session manager, 
        # but allow it for dependency injection if needed.
        self._manual_ssid = ssid 
        self.api: Optional[PocketOptionAsync] = None

    async def connect(self):
        current_ssid = self._manual_ssid or session_manager.get_ssid()
        if not current_ssid:
            logger.error("Cannot connect: No SSID provided")
            raise ValueError("No SSID found. Please set SSID in Account settings.")

        if not self.api:
            self.api = PocketOptionAsync(current_ssid)
            # Basic connection check or wait
            await asyncio.sleep(2) 

    async def fetch_candles(self, asset: str, period: int, count: int = 100) -> List[Dict]:
        """
        Fetch historical candles.
        Verify against PocketOption web exactly (time-aligned).
        """
        if not self.api:
            await self.connect()
            
        try:
            logger.info(f"Fetching {count} candles for {asset} (period={period})")
            
            # The underlying library usage based on previous exploration
            time_back = count * period
            
            if hasattr(self.api, 'get_candles'):
                raw = await self.api.get_candles(asset, period, time_back)
            elif hasattr(self.api, 'history'):
                raw = await self.api.history(asset, period)
            else:
                logger.error("API does not support history fetching")
                return []

            normalized = CandleNormalizer.normalize_list(raw, asset)
            
            # Filter to requested count if API returned too many
            if len(normalized) > count:
                normalized = normalized[-count:]
                
            return normalized
        except Exception as e:
            logger.error(f"Error fetching history: {e}")
            return []
            
    async def close(self):
        if self.api:
            try:
                await self.api.disconnect()
            except:
                pass
            self.api = None
