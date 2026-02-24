"""Strategy engine: 4-layer confluence gate with pure function evaluation.

This module implements the trading strategy as a pure function with NO imports
of redis_state, exchange_client, or external_feeds. All inputs are passed as
parameters. Structured JSON logging for every gate evaluation.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, List
import json
from logging_utils import log_event


def evaluate_signal(
    state_snapshot: Dict[str, Any],
    candles_1m: List[List[float]],
    candles_15m: List[List[float]],
    external_scores: Dict[str, Any]
) -> Dict[str, Any]:
    """4-layer confluence gate evaluation.
    
    PURE FUNCTION: Takes all inputs as parameters. No state mutations.
    
    Args:
        state_snapshot: RedisSnapshot with automation_enabled, account_balance, etc
        candles_1m: List of 1m OHLCV candles
        candles_15m: List of 15m OHLCV candles
        external_scores: Dict with funding_rate, fear_greed_value, onchain_flow, ls_ratio
    
    Returns:
        {
            "timestamp": int (ms),
            "side": "long" | "short" | None,
            "trend_score": float (-100 to +100),
            "reversion_score": float (-100 to +100),
            "volume_score": float (-100 to +100),
            "layer2_atr_multiplier": float (stop distance in ATR),
            "layer3_extended_move": bool (extended move active),
            "layer4_spread_ok": bool (spread under threshold),
            "composite_score": float,
            "decision": "entry_long" | "entry_short" | "no_action",
            "reason": str (detailed explanation),
        }
    """
    import time
    from indicators import ema, zscore, atr, find_pivot_swings, bid_ask_spread
    
    ts_ms = int(time.time() * 1000)
    
    # ============================================================================
    # GATE 1: Data Freshness & Minimum Candles
    # ============================================================================
    if not candles_1m or len(candles_1m) < 50 or not candles_15m or len(candles_15m) < 20:
        return {
            "timestamp": ts_ms,
            "side": None,
            "trend_score": 0.0,
            "reversion_score": 0.0,
            "volume_score": 0.0,
            "layer2_atr_multiplier": 0.0,
            "layer3_extended_move": False,
            "layer4_spread_ok": False,
            "composite_score": 0.0,
            "decision": "no_action",
            "reason": "Gate 1 failed: insufficient candle data",
        }
    
    # ============================================================================
    # GATE 2: Extract OHLCV Data with Precision
    # ============================================================================
    closes_1m = [c[4] for c in candles_1m]
    closes_15m = [c[4] for c in candles_15m]
    highs_1m = [c[2] for c in candles_1m]
    lows_1m = [c[3] for c in candles_1m]
    
    # ============================================================================
    # LAYER 1: TREND SCORE (EMA 50 vs 200 on 15m)
    # ============================================================================
    ema_50_15m = ema(closes_15m, 50)
    ema_200_15m = ema(closes_15m, 200)
    
    if ema_50_15m is None or ema_200_15m is None:
        return {
            "timestamp": ts_ms,
            "side": None,
            "trend_score": 0.0,
            "reversion_score": 0.0,
            "volume_score": 0.0,
            "layer2_atr_multiplier": 0.0,
            "layer3_extended_move": False,
            "layer4_spread_ok": False,
            "composite_score": 0.0,
            "decision": "no_action",
            "reason": "Gate 2 failed: cannot calculate EMAs",
        }
    
    current_price_15m = closes_15m[-1]
    trend_score = 0.0
    
    if ema_50_15m > ema_200_15m and current_price_15m > ema_50_15m:
        trend_score = 50.0  # Strong uptrend
    elif ema_50_15m > ema_200_15m and current_price_15m > ema_200_15m:
        trend_score = 30.0  # Uptrend
    elif ema_50_15m < ema_200_15m and current_price_15m < ema_50_15m:
        trend_score = -50.0  # Strong downtrend
    elif ema_50_15m < ema_200_15m and current_price_15m < ema_200_15m:
        trend_score = -30.0  # Downtrend
    else:
        trend_score = 0.0  # No clear trend
    
    # ============================================================================
    # LAYER 2: REVERSION SCORE (Z-Score + Pivot Analysis on 1m)
    # ============================================================================
    z_score_1m = zscore(closes_1m, 20)
    pivot_high, pivot_low = find_pivot_swings(candles_1m, lookback=20, pivot_width=2)
    
    reversion_score = 0.0
    if z_score_1m is not None:
        if z_score_1m > 2.0:  # Price is 2+ std devs above mean (overbought)
            reversion_score = -30.0
        elif z_score_1m < -2.0:  # Price is 2+ std devs below mean (oversold)
            reversion_score = 30.0
        elif z_score_1m > 1.0:
            reversion_score = -15.0
        elif z_score_1m < -1.0:
            reversion_score = 15.0
    
    # Check pivot-based reversion
    if pivot_high and current_price_15m > pivot_high * 1.02:  # Price above pivot by 2%
        reversion_score -= 10.0  # Bias bearish on reversion
    if pivot_low and current_price_15m < pivot_low * 0.98:  # Price below pivot by 2%
        reversion_score += 10.0  # Bias bullish on reversion
    
    # ============================================================================
    # LAYER 3: VOLUME SCORE (CVD-like analysis using external data)
    # ============================================================================
    ls_ratio = external_scores.get("ls_ratio", 1.0)
    funding_rate = external_scores.get("funding_rate", 0.0)
    onchain_flow = external_scores.get("onchain_flow", 0.0)
    
    volume_score = 0.0
    
    # Long/Short ratio (users) analysis
    if ls_ratio > 1.1:  # More longs
        volume_score += 15.0
    elif ls_ratio < 0.9:  # More shorts
        volume_score -= 15.0
    
    # Funding rate analysis
    if funding_rate > 0.0001:  # High positive (bullish)
        volume_score += 10.0
    elif funding_rate < -0.0001:  # High negative (bearish)
        volume_score -= 10.0
    
    # On-chain flow analysis
    if onchain_flow > 100:  # Positive inflow
        volume_score += 10.0
    elif onchain_flow < -100:  # Negative outflow
        volume_score -= 10.0
    
    # ============================================================================
    # ASYMMETRY GATE: Log all three scores
    # ============================================================================
    log_event("INFO", {
        "msg": "STRATEGY_ASYMMETRY_GATE",
        "trend_score": trend_score,
        "reversion_score": reversion_score,
        "volume_score": volume_score,
        "ls_ratio": ls_ratio,
        "funding_rate": funding_rate,
    })
    
    # ============================================================================
    # LAYER 4: ATR-based Stop Placement (Layer 2 extended)
    # ============================================================================
    atr_val = atr(highs_1m, lows_1m, closes_1m, period=14)
    
    if atr_val is None or atr_val == 0:
        return {
            "timestamp": ts_ms,
            "side": None,
            "trend_score": trend_score,
            "reversion_score": reversion_score,
            "volume_score": volume_score,
            "layer2_atr_multiplier": 0.0,
            "layer3_extended_move": False,
            "layer4_spread_ok": False,
            "composite_score": 0.0,
            "decision": "no_action",
            "reason": "Gate 4 failed: cannot calculate ATR",
        }
    
    # SL should be 1.5 ATR away from entry
    atr_multiplier = 1.5
    
    # ============================================================================
    # EXTENDED MOVE FILTER (Layer 3)
    # ============================================================================
    # Check if price is within 1.5 ATR below pivot low OR above pivot high
    extended_move_active = False
    
    if pivot_high and current_price_15m > (pivot_high + atr_val * 1.5):
        extended_move_active = True  # Price has extended significantly above pivot
    if pivot_low and current_price_15m < (pivot_low - atr_val * 1.5):
        extended_move_active = True  # Price has extended significantly below pivot
    
    # ============================================================================
    # SPREAD GUARD (Layer 4)
    # ============================================================================
    # Assume mid-price is close[−1], bid-ask estimated at 0.04%
    estimated_bid = closes_1m[-1] * 0.9998
    estimated_ask = closes_1m[-1] * 1.0002
    spread = bid_ask_spread(estimated_bid, estimated_ask)
    
    spread_ok = spread <= 0.0008  # 0.08% = acceptable
    
    # ============================================================================
    # COMPOSITE SCORE & DECISION LOGIC
    # ============================================================================
    composite_score = trend_score + reversion_score + volume_score
    
    # Minimum thresholds from config (defaults)
    min_score_long = 3.0
    min_score_short = -2.0
    
    decision = "no_action"
    side = None
    reason = "Composite score below threshold"
    
    if composite_score >= min_score_long and not extended_move_active and spread_ok:
        decision = "entry_long"
        side = "long"
        reason = f"Long signal (composite={composite_score:.1f}, trend={trend_score:.1f}, volume={volume_score:.1f})"
    elif composite_score <= min_score_short and not extended_move_active and spread_ok:
        decision = "entry_short"
        side = "short"
        reason = f"Short signal (composite={composite_score:.1f}, trend={trend_score:.1f}, volume={volume_score:.1f})"
    elif extended_move_active:
        reason = "Rejected: Price in extended move (Layer 3 gate)"
    elif not spread_ok:
        reason = f"Rejected: Spread too wide ({spread*100:.2f}% > 0.08%)"
    
    return {
        "timestamp": ts_ms,
        "side": side,
        "trend_score": float(trend_score),
        "reversion_score": float(reversion_score),
        "volume_score": float(volume_score),
        "layer2_atr_multiplier": float(atr_multiplier),
        "layer3_extended_move": extended_move_active,
        "layer4_spread_ok": spread_ok,
        "composite_score": float(composite_score),
        "decision": decision,
        "reason": reason,
    }
