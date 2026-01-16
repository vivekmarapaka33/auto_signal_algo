from typing import Dict, List, Any
import logging
from datetime import datetime

logger = logging.getLogger("CandleNormalizer")

class CandleNormalizer:
    @staticmethod
    def normalize_candle(candle: Any, asset: str) -> Dict[str, Any]:
        """
        Normalize a single candle to {time: int, open: float, high: float, low: float, close: float, volume: float, asset: str}
        """
        try:
            # Handle if candle is already dict
            if not isinstance(candle, dict):
                # Try converting object to dict if possible
                if hasattr(candle, '__dict__'):
                    candle = candle.__dict__
                else:
                    return None
            
            # Time normalization
            time_val = candle.get('time') or candle.get('timestamp') or candle.get('t')
            if isinstance(time_val, str):
                try:
                    dt = datetime.fromisoformat(time_val.replace('Z', '+00:00'))
                    time_ts = int(dt.timestamp())
                except:
                    time_ts = 0 # Fail safe?
            elif isinstance(time_val, (int, float)):
                time_ts = int(time_val)
            else:
                time_ts = 0
                
            def get_f(keys):
                for k in keys:
                    if k in candle and candle[k] is not None:
                        return float(candle[k])
                return 0.0

            return {
                'time': time_ts,
                'open': get_f(['open', 'Open', 'o']),
                'high': get_f(['high', 'High', 'h']),
                'low': get_f(['low', 'Low', 'l']),
                'close': get_f(['close', 'Close', 'c']),
                'volume': get_f(['volume', 'Volume', 'v']),
                'asset': asset
            }
        except Exception as e:
            logger.error(f"Error normalizing candle: {e}")
            return None

    @staticmethod
    def normalize_list(candles: List[Any], asset: str) -> List[Dict[str, Any]]:
        normalized = []
        for c in candles:
            n = CandleNormalizer.normalize_candle(c, asset)
            if n:
                normalized.append(n)
        
        # Sort by time
        normalized.sort(key=lambda x: x['time'])
        return normalized
