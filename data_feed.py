"""Data feed layer: rolling window and freshness tracking.

Maintains rolling 1000-candle windows for 1m and 15m timeframes. The
`ensure_fresh(max_age_seconds=3)` method checks WebSocket freshness.
Candles should be OHLCV tuples: [timestamp_ms, open, high, low, close, volume].
"""
from __future__ import annotations
import time
from collections import deque
from typing import Optional, List, Tuple, Deque
import pandas as pd


class DataFeed:
    """Rolling 1000-candle window for 1m and 15m with freshness tracking."""
    
    def __init__(self, symbol: str = "BTC/USDT", window_size: int = 1000):
        self.symbol = symbol
        self.window_size = window_size
        
        # Rolling windows using deque for efficient memory management
        self.candles_1m: Deque = deque(maxlen=window_size)  # [ts_ms, o, h, l, c, v]
        self.candles_15m: Deque = deque(maxlen=window_size)
        
        # Timestamp of last WebSocket tick
        self._last_tick_ts: float = time.time()
    
    def update_tick(self, candle_1m: List[float], candle_15m: Optional[List[float]] = None) -> None:
        """Add a 1m candle; optionally a 15m candle too.
        
        Args:
            candle_1m: [timestamp_ms, open, high, low, close, volume]
            candle_15m: Optional 15m candle in same format
        """
        self.candles_1m.append(tuple(candle_1m))
        if candle_15m:
            self.candles_15m.append(tuple(candle_15m))
        self._last_tick_ts = time.time()
    
    def last_tick_ts(self) -> float:
        """Return timestamp of last WebSocket tick in seconds."""
        return self._last_tick_ts
    
    def ensure_fresh(self, max_age_seconds: float = 3.0) -> bool:
        """Check if last WebSocket tick is recent.
        
        Returns:
            True if tick age <= max_age_seconds, False if stale.
        """
        age = time.time() - self._last_tick_ts
        return age <= max_age_seconds
    
    def get_dataframe_1m(self) -> pd.DataFrame:
        """Get 1m candles as pandas DataFrame.
        
        Returns:
            DataFrame with columns: [timestamp, open, high, low, close, volume]
        """
        if not self.candles_1m:
            return pd.DataFrame()
        
        data = list(self.candles_1m)
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    
    def get_dataframe_15m(self) -> pd.DataFrame:
        """Get 15m candles as pandas DataFrame.
        
        Returns:
            DataFrame with columns: [timestamp, open, high, low, close, volume]
        """
        if not self.candles_15m:
            return pd.DataFrame()
        
        data = list(self.candles_15m)
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    
    def get_close_prices_1m(self) -> List[float]:
        """Get all 1m closing prices as list."""
        return [candle[4] for candle in self.candles_1m]
    
    def get_close_prices_15m(self) -> List[float]:
        """Get all 15m closing prices as list."""
        return [candle[4] for candle in self.candles_15m]
    
    def get_hlc_1m(self) -> Tuple[List[float], List[float], List[float]]:
        """Get 1m high, low, close lists.
        
        Returns:
            (high_list, low_list, close_list)
        """
        highs = [candle[2] for candle in self.candles_1m]
        lows = [candle[3] for candle in self.candles_1m]
        closes = [candle[4] for candle in self.candles_1m]
        return highs, lows, closes
    
    def get_hlc_15m(self) -> Tuple[List[float], List[float], List[float]]:
        """Get 15m high, low, close lists.
        
        Returns:
            (high_list, low_list, close_list)
        """
        highs = [candle[2] for candle in self.candles_15m]
        lows = [candle[3] for candle in self.candles_15m]
        closes = [candle[4] for candle in self.candles_15m]
        return highs, lows, closes
