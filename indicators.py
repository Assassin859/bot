"""Technical indicators: EMA, Z-Score, ATR, CVD divergence, pivot detection, spread.

All indicators designed to work with rolling candle windows from data_feed.py.
"""
from __future__ import annotations
from typing import List, Tuple, Optional
import numpy as np
import pandas as pd


def ema(series: List[float], period: int) -> Optional[float]:
    """Exponential Moving Average.
    
    Args:
        series: List or array of prices (closes)
        period: EMA period (e.g., 50, 200)
    
    Returns:
        The most recent EMA value, or None if insufficient data
    """
    try:
        arr = np.array(series, dtype=np.float64)
        if len(arr) < period:
            return None
        
        ema_val = arr[-1]  # Start with most recent close
        multiplier = 2.0 / (period + 1)
        
        # Calculate EMA for all values
        for i in range(len(arr) - 1, 0, -1):
            ema_val = arr[i] * multiplier + ema_val * (1 - multiplier)
        
        return float(ema_val)
    except (TypeError, ValueError):
        return None


def zscore(series: List[float], period: int = 20) -> Optional[float]:
    """Z-Score (standard deviations from mean).
    
    Args:
        series: List or array of prices
        period: Lookback period for std dev calculation
    
    Returns:
        Z-score of the most recent value, or None if insufficient data
    """
    try:
        arr = np.array(series, dtype=np.float64)
        if len(arr) < period:
            return None
        
        arr_window = arr[-period:]
        mean = np.mean(arr_window)
        std = np.std(arr_window)
        
        if std == 0:
            return 0.0
        
        z = (arr_window[-1] - mean) / std
        return float(z)
    except (TypeError, ValueError):
        return None


def atr(ohlcv: List[List[float]] | np.ndarray, period: int = 14) -> Optional[float]:
    """Average True Range.
    
    Args:
        ohlcv: Either 2D array of [timestamp, open, high, low, close, volume] 
               or separate lists
        period: ATR period (default 14)
    
    Returns:
        ATR value, or None if insufficient data
    """
    try:
        arr = np.array(ohlcv, dtype=np.float64)
        
        if len(arr) < period + 1:
            return None
        
        # Extract high/low/close
        if arr.ndim == 2 and arr.shape[1] >= 5:
            # OHLCV format: [time, open, high, low, close, volume]
            h = arr[:, 2]
            l = arr[:, 3]
            c = arr[:, 4]
        elif arr.ndim == 1:
            # Single array of closes - can't calculate ATR
            return None
        else:
            return None
        
        # Calculate True Range
        tr1 = h[1:] - l[1:]
        tr2 = np.abs(h[1:] - c[:-1])
        tr3 = np.abs(l[1:] - c[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # Average True Range
        if len(tr) < period:
            return None
        
        atr_val = np.mean(tr[-period:])
        return float(atr_val)
    except (TypeError, ValueError, IndexError):
        return None


def find_pivot_swings(
    candles: List[List[float]] | np.ndarray,
    lookback: int = 20,
    pivot_width: int = 2
) -> Tuple[Optional[float], Optional[float]]:
    """Find 5-candle pivot swings (highs and lows) within last lookback bars.
    
    A pivot high is a candle with 2 lower highs on each side.
    A pivot low is a candle with 2 higher lows on each side.
    
    Args:
        candles: List or array of [timestamp, open, high, low, close, volume]
        lookback: Number of recent candles to search (default 20)
        pivot_width: Number of candles on each side of pivot (default 2)
    
    Returns:
        Tuple of (pivot_high, pivot_low), with None for missing pivots
    """
    try:
        arr = np.array(candles)
        if len(arr) < max(lookback, pivot_width * 2 + 1):
            return None, None
        
        # Extract highs and lows from recent candles
        recent = arr[-lookback:]
        if recent.ndim == 2 and recent.shape[1] >= 4:
            highs = [c[2] for c in recent]
            lows = [c[3] for c in recent]
        else:
            return None, None
        
        pivot_high = None
        pivot_low = None
        
        # Find pivot high (5-candle pattern: lower, lower, PIVOT, lower, lower)
        for i in range(pivot_width, len(highs) - pivot_width):
            is_pivot = all(highs[j] < highs[i] for j in range(i - pivot_width, i)) and \
                       all(highs[j] < highs[i] for j in range(i + 1, i + pivot_width + 1))
            if is_pivot:
                pivot_high = highs[i]
                break
        
        # Find pivot low (5-candle pattern: higher, higher, PIVOT, higher, higher)
        for i in range(pivot_width, len(lows) - pivot_width):
            is_pivot = all(lows[j] > lows[i] for j in range(i - pivot_width, i)) and \
                       all(lows[j] > lows[i] for j in range(i + 1, i + pivot_width + 1))
            if is_pivot:
                pivot_low = lows[i]
                break
        
        return pivot_high, pivot_low
    except (TypeError, ValueError, IndexError):
        return None, None


def cvd_divergence(
    price_series: List[float] | np.ndarray,
    cvd_series: List[float] | np.ndarray,
    lookback: int = 10
) -> int:
    """Detect CVD divergence with price.
    
    Returns 1 if bullish divergence (price lower but CVD higher),
    -1 if bearish divergence (price higher but CVD lower),
    0 if no divergence.
    
    Args:
        price_series: List or array of closing prices
        cvd_series: List or array of CVD values
        lookback: Number of candles to check for divergence
    
    Returns:
        1 (bullish), -1 (bearish), or 0 (no divergence)
    """
    try:
        prices = list(np.array(price_series, dtype=np.float64))
        cvds = list(np.array(cvd_series, dtype=np.float64))
        
        if not prices or not cvds or len(prices) < lookback:
            return 0
        
        prices = prices[-lookback:]
        cvds = cvds[-lookback:]
        
        price_min_idx = prices.index(min(prices))
        price_max_idx = prices.index(max(prices))
        cvd_min_idx = cvds.index(min(cvds))
        cvd_max_idx = cvds.index(max(cvds))
        
        # Bullish divergence: price makes lower low but CVD makes higher low
        if price_min_idx != cvd_min_idx and prices[price_min_idx] < prices[price_max_idx]:
            if cvds[cvd_min_idx] > cvds[cvd_max_idx]:
                return 1
        
        # Bearish divergence: price makes higher high but CVD makes lower high
        if price_max_idx != cvd_max_idx and prices[price_max_idx] > prices[price_min_idx]:
            if cvds[cvd_max_idx] < cvds[cvd_min_idx]:
                return -1
        
        return 0
    except (TypeError, ValueError):
        return 0


def bid_ask_spread(bid: float, ask: float) -> float:
    """Calculate bid-ask spread as percentage.
    
    Args:
        bid: Bid price
        ask: Ask price
    
    Returns:
        Spread as percentage (e.g., 0.0008 for 0.08%)
    """
    if ask == 0:
        return 0.0
    
    spread = (ask - bid) / ask
    return float(spread)
