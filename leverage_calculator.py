"""Core leverage mathematics for futures trading.

This module provides all calculation functions for:
- Liquidation price computation (long/short)
- Margin utilization tracking
- Stop-loss safety validation with buffer enforcement
- Position size calculation with leverage awareness
"""
from __future__ import annotations
from typing import NamedTuple, Optional
from dataclasses import dataclass

# Constants
LIQUIDATION_BUFFER_PCT = 10.0  # 10% SL margin above liquidation
MARGIN_DANGER_ZONE_PCT = 90.0  # Warn above this
MARGIN_FORCE_CLOSE_PCT = 95.0  # Auto-close above this
BINANCE_TAKER_FEE_PCT = 0.04


class LiquidationMetrics(NamedTuple):
    """Metrics for a position's liquidation risk."""
    liquidation_price: float
    buffer_to_sl: float
    margin_utilization_pct: float
    is_liquidation_safe: bool
    recommended_sl: float
    buffer_pct: float


@dataclass
class LeverageContext:
    """Context for leverage calculations."""
    account_balance: float
    trading_capital: float
    leverage: int
    entry_price: float
    atr_stop_distance: float
    max_risk_pct: float


def calculate_liquidation_price(
    side: str,
    entry_price: float,
    collateral: float,
    amount: float
) -> float:
    """
    Calculate liquidation price for a futures position.
    
    Liquidation occurs when margin drops to zero.
    
    Long:  liquidation = entry - (collateral / amount)
           (moving down by collateral/amount)
    
    Short: liquidation = entry + (collateral / amount)
           (moving up by collateral/amount)
    
    Args:
        side: "long" or "short"
        entry_price: Entry price in USDT
        collateral: Margin locked (trading capital)
        amount: BTC amount in position
    
    Returns:
        Liquidation price in USDT
    
    Example:
        Long position: entry=50000, collateral=1000, amount=0.01
        → liquidation = 50000 - (1000/0.01) = 50000 - 100000 = -50000 (too extreme)
        
        Better example: entry=50000, collateral=1000, amount=0.1
        → liquidation = 50000 - (1000/0.1) = 50000 - 10000 = 40000
    """
    if amount <= 0:
        raise ValueError(f"Amount must be positive, got {amount}")
    
    if side.lower() == "long":
        return entry_price - (collateral / amount)
    elif side.lower() == "short":
        return entry_price + (collateral / amount)
    else:
        raise ValueError(f"Side must be 'long' or 'short', got {side}")


def calculate_margin_utilization(
    collateral: float,
    position_notional: float
) -> float:
    """
    Calculate margin utilization percentage.
    
    Formula: (collateral / position_notional) × 100
    
    Args:
        collateral: Margin locked (trading capital)
        position_notional: Position value in USDT
    
    Returns:
        Margin utilization as percentage (0-100%+)
    
    Example:
        collateral=1000, notional=5000
        → (1000/5000) × 100 = 20%
    """
    if position_notional <= 0:
        return 0.0
    
    return (collateral / position_notional) * 100.0


def calculate_buffer_to_liquidation(
    current_price: float,
    liquidation_price: float,
    side: str
) -> float:
    """
    Calculate percentage buffer between current price and liquidation.
    
    Long:  buffer = (current - liquidation) / liquidation × 100
    Short: buffer = (liquidation - current) / liquidation × 100
    
    Args:
        current_price: Current market price
        liquidation_price: Price at which position liquidates
        side: "long" or "short"
    
    Returns:
        Buffer as percentage
    """
    if liquidation_price == 0:
        return 0.0
    
    if side.lower() == "long":
        buffer = (current_price - liquidation_price) / abs(liquidation_price) * 100
    else:
        buffer = (liquidation_price - current_price) / abs(liquidation_price) * 100
    
    return max(0, buffer)  # Never negative


def validate_sl_position(
    entry_price: float,
    sl_price: float,
    collateral: float,
    amount: float,
    side: str,
    leverage: int = 1
) -> LiquidationMetrics:
    """
    Verify stop-loss is safe with 10% buffer from liquidation.
    
    Rules:
    1. Calculate liquidation price
    2. Verify SL is 10%+ away from liquidation
    3. Calculate margin utilization
    4. Recommend safe SL if current is too close
    
    Args:
        entry_price: Entry price in USDT
        sl_price: Stop-loss price in USDT
        collateral: Margin locked (trading capital)
        amount: BTC amount in position
        side: "long" or "short"
        leverage: Leverage multiplier (default 1)
    
    Returns:
        LiquidationMetrics with safety assessment
    
    Raises:
        ValueError: If inputs are invalid
    """
    if amount <= 0:
        raise ValueError(f"Amount must be positive, got {amount}")
    if leverage < 1 or leverage > 20:
        raise ValueError(f"Leverage must be 1-20, got {leverage}")
    
    # Calculate liquidation price
    liq = calculate_liquidation_price(side, entry_price, collateral, amount)
    
    # Calculate position notional
    position_notional = entry_price * amount
    
    # Calculate margin utilization
    margin_util = calculate_margin_utilization(collateral, position_notional)
    
    # Calculate buffer between SL and liquidation
    if side.lower() == "long":
        # For long: SL should be above liquidation
        buffer = sl_price - liq
        buffer_pct = (buffer / abs(liq)) * 100 if liq != 0 else 0
        
        # Safety check: need 10% buffer minimum
        min_buffer = abs(liq) * (LIQUIDATION_BUFFER_PCT / 100)
        is_safe = buffer >= min_buffer
        
        # Recommend SL if not safe
        if not is_safe:
            recommended_sl = liq + min_buffer
        else:
            recommended_sl = sl_price
    else:
        # For short: SL should be below liquidation
        buffer = liq - sl_price
        buffer_pct = (buffer / abs(liq)) * 100 if liq != 0 else 0
        
        # Safety check: need 10% buffer minimum
        min_buffer = abs(liq) * (LIQUIDATION_BUFFER_PCT / 100)
        is_safe = buffer >= min_buffer
        
        # Recommend SL if not safe
        if not is_safe:
            recommended_sl = liq - min_buffer
        else:
            recommended_sl = sl_price
    
    return LiquidationMetrics(
        liquidation_price=liq,
        buffer_to_sl=buffer,
        margin_utilization_pct=margin_util,
        is_liquidation_safe=is_safe,
        recommended_sl=recommended_sl,
        buffer_pct=buffer_pct
    )


def calculate_position_size_with_leverage(
    account_balance: float,
    trading_capital: float,
    leverage: int,
    entry_price: float,
    atr_stop_distance: float,
    max_risk_pct: float
) -> dict:
    """
    Calculate position size considering leverage and liquidation safety.
    
    Formula:
    1. Risk amount = account_balance × max_risk_pct
    2. Max position notional = trading_capital × leverage × 0.8 (80% max)
    3. Position size = min(risk_amount × leverage, max_notional)
    4. Amount (BTC) = position_notional / entry_price
    5. Verify: SL allows 10% buffer from liquidation
    
    Args:
        account_balance: Total account balance in USDT
        trading_capital: Allocated trading capital in USDT
        leverage: Leverage multiplier (1-20)
        entry_price: Entry price in USDT
        atr_stop_distance: Stop-loss distance in USDT (from ATR)
        max_risk_pct: Max risk % per trade
    
    Returns:
        Dict with:
        - position_notional: Notional USD value
        - amount_btc: BTC amount
        - collateral_required: Trading capital reserved
        - margin_utilization_pct: Current margin %
        - is_safe: Whether SL buffer is OK
        - reason: Safety assessment message
        - liquidation_price: Position liquidation level
        - recommended_sl: Safe SL price
    
    Example:
        account=10000, capital=1000, leverage=5, entry=50000
        atr=50, risk=2%, current_price=50020
        
        risk_amount = 10000 × 2% = 200
        max_notional = 1000 × 5 × 0.8 = 4000
        position = min(200 × 5, 4000) = 1000
        amount = 1000 / 50000 = 0.02 BTC
    """
    if leverage < 1 or leverage > 20:
        return {
            "is_safe": False,
            "reason": f"Leverage must be 1-20, got {leverage}",
            "position_notional": 0,
            "amount_btc": 0
        }
    
    # Calculate risk amount
    risk_amount = account_balance * (max_risk_pct / 100)
    
    # Calculate max position with leverage
    max_position_notional = trading_capital * leverage * 0.8  # 80% safety cap
    
    # Position sizing: larger of risk-based or risk × leverage
    position_notional = min(risk_amount * leverage, max_position_notional)
    
    # Ensure minimum position to avoid rounding errors
    if position_notional < 10:  # Less than $10 is too small
        position_notional = 0
        amount_btc = 0
    else:
        amount_btc = position_notional / entry_price
    
    # Margin utilization
    margin_util = calculate_margin_utilization(trading_capital, position_notional) if position_notional > 0 else 0
    
    # Verify liquidation safety if position exists
    if amount_btc > 0 and atr_stop_distance > 0:
        # Estimate SL based on ATR (default 1.5x ATR below entry for long)
        sl_price = entry_price - atr_stop_distance * 1.5
        
        metrics = validate_sl_position(
            entry_price=entry_price,
            sl_price=sl_price,
            collateral=trading_capital,
            amount=amount_btc,
            side="long",  # Simplified: assume long for sizing
            leverage=leverage
        )
        
        is_safe = metrics.is_liquidation_safe and margin_util < MARGIN_FORCE_CLOSE_PCT
        reason = (
            "✓ Safe" if is_safe
            else f"⚠ SL buffer too close: {metrics.buffer_pct:.1f}%"
        )
        
        return {
            "position_notional": position_notional,
            "amount_btc": amount_btc,
            "collateral_required": trading_capital,
            "margin_utilization_pct": margin_util,
            "is_safe": is_safe,
            "reason": reason,
            "liquidation_price": metrics.liquidation_price,
            "recommended_sl": metrics.recommended_sl,
            "buffer_pct": metrics.buffer_pct
        }
    else:
        return {
            "position_notional": 0,
            "amount_btc": 0,
            "collateral_required": trading_capital,
            "margin_utilization_pct": 0,
            "is_safe": True,
            "reason": "No position",
            "liquidation_price": None,
            "recommended_sl": None,
            "buffer_pct": None
        }


def check_margin_danger_zones(
    margin_utilization_pct: float,
    buffer_to_liquidation_pct: float
) -> dict:
    """
    Check for dangerous margin/liquidation conditions.
    
    Returns warnings and action flags:
    - margin_warning: True if >90%
    - margin_critical: True if >95% (force close)
    - liquidation_warning: True if <10%
    - liquidation_critical: True if <5% (force close)
    
    Args:
        margin_utilization_pct: Margin utilization percentage
        buffer_to_liquidation_pct: Buffer to liquidation price %
    
    Returns:
        Dict with warning flags and messages
    """
    return {
        "margin_warning": margin_utilization_pct > MARGIN_DANGER_ZONE_PCT,
        "margin_critical": margin_utilization_pct > MARGIN_FORCE_CLOSE_PCT,
        "liquidation_warning": buffer_to_liquidation_pct < 10,
        "liquidation_critical": buffer_to_liquidation_pct < 5,
        "margin_level": f"{margin_utilization_pct:.1f}%",
        "liquidation_buffer": f"{buffer_to_liquidation_pct:.1f}%"
    }
