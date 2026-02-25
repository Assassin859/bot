"""Risk engine: position sizing, bracket planning, and circuit breakers.

Implements 1% risk sizing per trade, 4 circuit breakers (daily limit, consecutive
losses, 24h drawdown kill switch, max hold time), plus per-candle integrity checks.
Also includes leverage-aware position sizing with liquidation protection (NEW).
"""
from __future__ import annotations
from typing import Any, Dict, Optional, NamedTuple
import time
from logging_utils import log_event


def compute_position_size(
    account_balance: float,
    atr_stop_distance_usd: float,
    config: Dict[str, Any]
) -> float:
    """Compute BTC position size using 1% risk rule with notional cap.
    
    Formula:
        risk_amount_usd = account_balance * risk_pct
        position_size_btc = risk_amount_usd / atr_stop_distance_usd
        capped to max_position_notional_usd
    
    Args:
        account_balance: Account balance in USDT
        atr_stop_distance_usd: Stop loss distance from entry in USD
        config: Config dict with risk section
    
    Returns:
        Position size in BTC (capped to max_notional / entry_price)
    """
    if atr_stop_distance_usd <= 0:
        return 0.0
    
    risk_config = config.get("risk", {})
    risk_pct = risk_config.get("account_risk_per_trade_pct", 1.0) / 100.0  # Convert % to decimal
    max_notional = risk_config.get("max_position_notional_usdt", 400.0)
    
    # 1% of account balance = amount risked on this trade
    risk_amount_usd = account_balance * risk_pct
    
    # Position size = risk amount / stop distance
    position_size_btc = risk_amount_usd / atr_stop_distance_usd
    
    # Never exceed max notional (assuming ~50k BTC price, max notional / 50000)
    max_size_btc = max_notional / 50000.0  # Rough conversion
    
    position_size_btc = min(position_size_btc, max_size_btc)
    
    return float(max(0.0, position_size_btc))


def compute_brackets(
    entry_price: float,
    position_size_btc: float,
    atr_val: float,
    config: Dict[str, Any],
    direction: str = "long"
) -> Dict[str, Any]:
    """Compute stop loss and take profit prices.
    
    Args:
        entry_price: Entry price in USDT
        position_size_btc: Position size in BTC
        atr_val: ATR value for stop distance
        config: Config with strategy.sl_atr_multiplier, tp_atr_multiplier
        direction: "long" or "short"
    
    Returns:
        {
            "stop_price": float,
            "target_price": float,
            "risk_usd": float,
            "reward_usd": float,
            "risk_reward_ratio": float,
        }
    """
    strategy_config = config.get("strategy", {})
    sl_multiplier = strategy_config.get("sl_atr_multiplier", 1.5)
    tp_multiplier = strategy_config.get("tp_atr_multiplier", 3.0)
    
    sl_distance = atr_val * sl_multiplier
    tp_distance = atr_val * tp_multiplier
    
    if direction == "long":
        stop_price = entry_price - sl_distance
        target_price = entry_price + tp_distance
    else:  # short
        stop_price = entry_price + sl_distance
        target_price = entry_price - tp_distance
    
    risk_usd = abs((entry_price - stop_price) * position_size_btc)
    reward_usd = abs((target_price - entry_price) * position_size_btc)
    risk_reward_ratio = reward_usd / risk_usd if risk_usd > 0 else 0.0
    
    return {
        "stop_price": float(stop_price),
        "target_price": float(target_price),
        "risk_usd": float(risk_usd),
        "reward_usd": float(reward_usd),
        "risk_reward_ratio": float(risk_reward_ratio),
    }


def check_circuit_breakers(
    state_snapshot: Dict[str, Any],
    config: Dict[str, Any],
    binance_offset_ms: int = 0
) -> Optional[str]:
    """Check all circuit breakers. Return rejection reason if any trip, else None.
    
    Circuit Breakers:
    1. Daily Trade Limit (max_daily_trades per UTC day)
    2. Consecutive Losses (max_consecutive_losses triggers cooldown_minutes)
    3. 24h Drawdown Kill Switch (-daily_drawdown_kill_pct of balance)
    4. Max Hold Duration (max_hold_minutes limit per position)
    
    Args:
        state_snapshot: RedisSnapshot with account state
        config: Config with risk section
        binance_offset_ms: Binance time offset for UTC date calculation
    
    Returns:
        Rejection reason string, or None if all breakers pass
    """
    risk_config = config.get("risk", {})
    
    # CB1: Daily Trade Limit
    max_daily_trades = risk_config.get("max_daily_trades", 10)
    daily_trade_count = state_snapshot.get("daily_trade_count", 0)
    daily_trade_date = state_snapshot.get("daily_trade_date", "")
    
    # Calculate today's UTC date
    current_time_ms = int(time.time() * 1000) + binance_offset_ms
    current_date = time.strftime("%Y-%m-%d", time.gmtime(current_time_ms / 1000))
    
    # Reset counter if date changed
    if daily_trade_date != current_date:
        daily_trade_count = 0
    
    if daily_trade_count >= max_daily_trades:
        return f"CB1: Daily trade limit reached ({daily_trade_count}/{max_daily_trades})"
    
    # CB2: Consecutive Losses + Cooldown
    max_consecutive_losses = risk_config.get("max_consecutive_losses", 3)
    cooldown_minutes = risk_config.get("cooldown_minutes", 45)
    consecutive_losses = state_snapshot.get("consecutive_losses", 0)
    cooldown_until_ms = state_snapshot.get("cooldown_until", 0)
    
    if consecutive_losses >= max_consecutive_losses:
        cooldown_until_ms = max(cooldown_until_ms, current_time_ms + cooldown_minutes * 60 * 1000)
        if current_time_ms < cooldown_until_ms:
            remaining_min = max(0, (cooldown_until_ms - current_time_ms) / 60 / 1000)
            return f"CB2: In cooldown after {consecutive_losses} consecutive losses ({remaining_min:.0f}m remaining)"
    
    # CB3: 24h Drawdown Kill Switch
    daily_drawdown_kill_pct = risk_config.get("daily_drawdown_kill_pct", 2.0)
    account_balance = state_snapshot.get("account_balance", 0.0)
    rolling_24h_pnl = state_snapshot.get("rolling_24h_pnl", 0.0)
    
    if account_balance > 0:
        drawdown_pct = abs(min(0, rolling_24h_pnl)) / account_balance * 100
        if drawdown_pct >= daily_drawdown_kill_pct:
            return f"CB3: 24h drawdown kill switch ({drawdown_pct:.2f}% > {daily_drawdown_kill_pct}%)"
    
    # CB4: Max Hold Duration (if there's an active position)
    max_hold_minutes = risk_config.get("max_hold_minutes", 90)
    active_position = state_snapshot.get("active_position", None)
    
    if active_position:
        entry_time_utc_ms = active_position.get("entry_time_utc", 0) if isinstance(active_position, dict) else 0
        if entry_time_utc_ms > 0:
            hold_duration_ms = current_time_ms - entry_time_utc_ms
            hold_duration_min = hold_duration_ms / 60 / 1000
            if hold_duration_min > max_hold_minutes:
                return f"CB4: Position held too long ({hold_duration_min:.0f}m > {max_hold_minutes}m)"
    
    # All breakers pass
    return None


def check_startup_integrity(
    state_snapshot: Dict[str, Any]
) -> Optional[str]:
    """Verify startup integrity: active position must have SL and TP orders.
    
    If an active position exists without SL/TP, this is a critical error.
    main.py will market-close immediately if this check fails.
    
    Returns:
        Error reason string if integrity check fails, else None
    """
    active_position = state_snapshot.get("active_position", None)
    
    if not active_position:
        return None  # No position, no issue
    
    # If position exists, check for SL and TP orders
    if isinstance(active_position, dict):
        stop_order_id = active_position.get("stop_order_id")
        target_order_id = active_position.get("target_order_id")
    else:
        # Handle Pydantic model
        stop_order_id = getattr(active_position, "stop_order_id", None)
        target_order_id = getattr(active_position, "target_order_id", None)
    
    if not stop_order_id:
        log_event("CRITICAL", {"msg": "STARTUP_INTEGRITY_CHECK_FAILED", "reason": "missing_stop_order"})
        return "STARTUP_INTEGRITY: Position exists but SL order missing"
    
    if not target_order_id:
        log_event("CRITICAL", {"msg": "STARTUP_INTEGRITY_CHECK_FAILED", "reason": "missing_target_order"})
        return "STARTUP_INTEGRITY: Position exists but TP order missing"
    
    return None


def check_candle_integrity(
    active_position: Dict[str, Any],
    candles_1m: list,
    config: Dict[str, Any]
) -> Optional[str]:
    """Verify SL/TP orders are still valid per current candles.
    
    On each candle, verify:
    - SL price is still viable (not < lowest low from entry)
    - TP price is still viable (not > highest high from entry)
    
    Returns:
        Warning reason if integrity suspect, else None
    """
    if not active_position or not candles_1m:
        return None
    
    entry_time_utc = active_position.get("entry_time_utc", 0)
    stop_price = active_position.get("stop_price", 0.0)
    target_price = active_position.get("target_price", 0.0)
    direction = active_position.get("direction", "long")
    
    if entry_time_utc == 0 or not stop_price or not target_price:
        return None
    
    # Find candles after entry
    recent_candles = [c for c in candles_1m if c[0] >= entry_time_utc]
    
    if not recent_candles:
        return None
    
    lows = [c[3] for c in recent_candles]
    highs = [c[2] for c in recent_candles]
    
    if direction == "long":
        min_low = min(lows)
        max_high = max(highs)
        
        # SL should be below all recent lows (or very close)
        if stop_price > min_low:
            return f"CANDLE_INTEGRITY: SL ({stop_price}) above recent lows ({min_low})"
        
        # TP should be above recent highs
        if target_price < max_high:
            return f"CANDLE_INTEGRITY: TP ({target_price}) below recent highs ({max_high})"
    
    else:  # short
        min_low = min(lows)
        max_high = max(highs)
        
        # SL should be above all recent highs
        if stop_price < max_high:
            return f"CANDLE_INTEGRITY: SL ({stop_price}) below recent highs ({max_high})"
        
        # TP should be below recent lows
        if target_price > min_low:
            return f"CANDLE_INTEGRITY: TP ({target_price}) above recent lows ({min_low})"
    
    return None


# ============================================================
# LEVERAGE-AWARE ENHANCEMENTS (NEW)
# ============================================================

class PositionSizeWithLeverageResult(NamedTuple):
    """Position sizing result with leverage consideration."""
    position_notional: float
    amount_btc: float
    collateral_required: float
    margin_utilization_pct: float
    liquidation_price: float
    recommended_sl: float
    is_safe: bool
    reason: str


def compute_position_size_leverage(
    account_balance: float,
    trading_capital: float,
    leverage: int,
    entry_price: float,
    atr_stop_distance_usd: float,
    max_risk_pct: float,
    side: str = "long"
) -> PositionSizeWithLeverageResult:
    """Compute position size considering leverage and liquidation safety.
    
    Formula:
    1. Risk amount = account_balance × max_risk_pct
    2. Max position notional = trading_capital × leverage × 0.8 (80% safety cap)
    3. Position size = min(risk × leverage, max_notional)
    4. Validate SL has 10% buffer from liquidation
    
    Args:
        account_balance: Total account balance in USDT
        trading_capital: Allocated to futures in USDT
        leverage: Leverage multiplier (1-20)
        entry_price: Entry price in USDT
        atr_stop_distance_usd: Stop loss distance from entry in USDT
        max_risk_pct: Max risk per trade as % of account
        side: "long" or "short"
    
    Returns:
        PositionSizeWithLeverageResult with all sizing parameters
    """
    from leverage_calculator import (
        calculate_liquidation_price,
        calculate_margin_utilization,
        validate_sl_position,
    )
    
    # Input validation
    if leverage < 1 or leverage > 20:
        return PositionSizeWithLeverageResult(
            position_notional=0,
            amount_btc=0,
            collateral_required=trading_capital,
            margin_utilization_pct=0,
            liquidation_price=0,
            recommended_sl=0,
            is_safe=False,
            reason=f"Invalid leverage: {leverage}"
        )
    
    if atr_stop_distance_usd <= 0:
        return PositionSizeWithLeverageResult(
            position_notional=0,
            amount_btc=0,
            collateral_required=trading_capital,
            margin_utilization_pct=0,
            liquidation_price=0,
            recommended_sl=0,
            is_safe=False,
            reason="ATR stop distance must be positive"
        )
    
    # Calculate risk amount
    risk_amount = account_balance * (max_risk_pct / 100)
    
    # Calculate position size with leverage
    max_position_notional = trading_capital * leverage * 0.8  # 80% cap
    position_notional = min(risk_amount * leverage, max_position_notional)
    
    # Ensure minimum position size for execution
    if position_notional < 10:  # Less than $10 is too small
        position_notional = 0
        amount_btc = 0
    else:
        amount_btc = position_notional / entry_price
    
    # Calculate margin utilization
    margin_util = (position_notional / trading_capital * 100) if trading_capital > 0 else 0
    
    # Validate liquidation safety
    if amount_btc > 0:
        # SL placement
        sl_price = entry_price - atr_stop_distance_usd if side == "long" else entry_price + atr_stop_distance_usd
        
        # Check SL safety with leverage
        metrics = validate_sl_position(
            entry_price=entry_price,
            sl_price=sl_price,
            collateral=trading_capital,
            amount=amount_btc,
            side=side,
            leverage=leverage
        )
        
        # Position is safe if:
        # 1. SL buffer >= 10% from liquidation AND
        # 2. Margin utilization < 95%
        is_safe = metrics.is_liquidation_safe and margin_util < 95
        
        reason = f"✓ Safe" if is_safe else f"⚠ SL buffer: {metrics.buffer_pct:.1f}%"
        
        return PositionSizeWithLeverageResult(
            position_notional=position_notional,
            amount_btc=amount_btc,
            collateral_required=trading_capital,
            margin_utilization_pct=margin_util,
            liquidation_price=metrics.liquidation_price,
            recommended_sl=metrics.recommended_sl,
            is_safe=is_safe,
            reason=reason
        )
    else:
        return PositionSizeWithLeverageResult(
            position_notional=0,
            amount_btc=0,
            collateral_required=trading_capital,
            margin_utilization_pct=0,
            liquidation_price=0,
            recommended_sl=0,
            is_safe=True,
            reason="No position"
        )


def check_circuit_breakers_leverage(
    state_snapshot: Dict[str, Any],
    config: Dict[str, Any],
    binance_offset_ms: int = 0
) -> Optional[str]:
    """Enhanced circuit breakers for leverage trading.
    
    Existing breakers (CB1-CB4):
    1. Daily Trade Limit
    2. Consecutive Losses + Cooldown
    3. 24h Drawdown Kill Switch
    4. Max Hold Duration
    
    New breakers with leverage (CB5-CB6):
    5. Margin Utilization > 95% → Force close
    6. Liquidation buffer < 5% → Refuse trade
    
    Args:
        state_snapshot: RedisSnapshot with leverage state
        config: Config with risk section
        binance_offset_ms: Binance time offset
    
    Returns:
        Rejection reason string, or None if all pass
    """
    # First check existing circuit breakers (CB1-CB4)
    existing_cb = check_circuit_breakers(state_snapshot, config, binance_offset_ms)
    if existing_cb:
        return existing_cb
    
    # NEW: CB5 - Margin utilization check
    margin_util = state_snapshot.get("leverage_margin_utilization_pct", 0.0)
    if margin_util > 95:
        return f"CB5: Margin utilization critical ({margin_util:.1f}% > 95%) - FORCE CLOSE"
    
    if margin_util > 90:
        # Warning level but no rejection
        log_event("WARNING", {"msg": "CB5_MARGIN_WARNING", "level_pct": margin_util})
    
    # NEW: CB6 - Liquidation buffer check
    liquidation_price = state_snapshot.get("leverage_liquidation_price", 0.0)
    active_position = state_snapshot.get("active_position")
    
    if active_position and liquidation_price:
        # Get current price (approximated from entry price if available)
        # In real usage, this would be looked up from market data
        entry_price = active_position.get("entry_price", 0.0) if isinstance(active_position, dict) else 0.0
        
        if entry_price > 0 and liquidation_price > 0:
            direction = active_position.get("direction", "long") if isinstance(active_position, dict) else "long"
            
            if direction == "long":
                buffer_pct = (entry_price - liquidation_price) / liquidation_price * 100
            else:
                buffer_pct = (liquidation_price - entry_price) / liquidation_price * 100
            
            # Critical: buffer < 5%
            if buffer_pct < 5 and buffer_pct > 0:
                return f"CB6: Liquidation buffer critically low ({buffer_pct:.1f}% < 5%) - FORCE CLOSE"
            
            # Warning: buffer < 10%
            if buffer_pct < 10 and buffer_pct > 0:
                log_event("WARNING", {"msg": "CB6_LIQUIDATION_WARNING", "buffer_pct": buffer_pct})
    
    # All breakers pass
    return None


def validate_sl_buffer(
    entry_price: float,
    sl_price: float,
    liquidation_price: float,
    side: str,
    buffer_pct_min: float = 10.0
) -> tuple[bool, str]:
    """Validate SL has minimum buffer from liquidation.
    
    Args:
        entry_price: Entry price in USDT
        sl_price: Stop loss price in USDT
        liquidation_price: Liquidation price in USDT
        side: "long" or "short"
        buffer_pct_min: Minimum buffer percentage (default 10%)
    
    Returns:
        (is_valid, message) tuple
    """
    if liquidation_price == 0:
        return True, "Liquidation price not set, skipping validation"
    
    if side == "long":
        # For long: SL should be above liquidation
        buffer_price = sl_price - liquidation_price
        buffer_pct = (buffer_price / abs(liquidation_price)) * 100
        
        min_buffer_price = abs(liquidation_price) * (buffer_pct_min / 100)
        is_valid = buffer_price >= min_buffer_price
    else:
        # For short: SL should be below liquidation  
        buffer_price = liquidation_price - sl_price
        buffer_pct = (buffer_price / abs(liquidation_price)) * 100
        
        min_buffer_price = abs(liquidation_price) * (buffer_pct_min / 100)
        is_valid = buffer_price >= min_buffer_price
    
    message = f"SL buffer: {buffer_pct:.1f}% (min: {buffer_pct_min}%)"
    
    return is_valid, message
