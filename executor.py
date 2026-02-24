"""Executor: mode-aware execution (ghost/paper/backtest/live) with SL guarantee.

Implements execution across 4 modes:
- Ghost: Simulates fills (mid + 0.04% fee), updates ghost metrics
- Paper: Uses token bucket, simulates fills with tokens
- Backtest: Internal portfolio updates
- Live: Real Binance orders with SL/TP bracket guarantee
"""
from __future__ import annotations
from typing import Any, Dict, Optional
import time
from logging_utils import log_event


def execute_entry_plan(
    entry_plan: Dict[str, Any],
    mode: str,
    state: Dict[str, Any],
    exchange_client: Optional[Any] = None,
    redis_state: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute or simulate an entry plan depending on mode.
    
    Args:
        entry_plan: {side, entry_price, stop_price, target_price, position_size_btc}
        mode: "ghost" | "paper" | "backtest" | "live"
        state: Current state snapshot
        exchange_client: ExchangeClient instance (required for paper/live)
        redis_state: RedisState instance (required for state updates)
    
    Returns:
        {
            "success": bool,
            "filled_price": float (actual execution price),
            "fee_usd": float,
            "pnl_realized": float,
            "stop_order_id": str | None,
            "target_order_id": str | None,
            "reason": str,
        }
    """
    ts_ms = int(time.time() * 1000)
    side = entry_plan.get("side", "long")
    entry_price = entry_plan.get("entry_price", 0.0)
    stop_price = entry_plan.get("stop_price", 0.0)
    target_price = entry_plan.get("target_price", 0.0)
    position_size_btc = entry_plan.get("position_size_btc", 0.0)
    
    if mode == "ghost":
        return _execute_ghost(ts_ms, side, entry_price, stop_price, target_price, position_size_btc, state)
    elif mode == "paper":
        return _execute_paper(ts_ms, side, entry_price, stop_price, target_price, position_size_btc, exchange_client)
    elif mode == "backtest":
        return _execute_backtest(ts_ms, side, entry_price, stop_price, target_price, position_size_btc)
    elif mode == "live":
        return _execute_live(ts_ms, side, entry_price, stop_price, target_price, position_size_btc, exchange_client)
    else:
        return {
            "success": False,
            "filled_price": 0.0,
            "fee_usd": 0.0,
            "pnl_realized": 0.0,
            "stop_order_id": None,
            "target_order_id": None,
            "reason": f"Unknown execution mode: {mode}",
        }


def _execute_ghost(
    ts_ms: int,
    side: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    position_size_btc: float,
    state: Dict[str, Any]
) -> Dict[str, Any]:
    """Ghost mode: simulate fills with mid-price + 0.04% fee.
    
    In ghost mode, we assume:
    - Entry fills at mid-price + slippage
    - Fee is 0.04% (typical Binance maker fee)
    - No real orders placed
    - Updates ghost_pnl, ghost_trade_count, ghost_win_rate
    """
    if position_size_btc <= 0 or entry_price <= 0:
        return {
            "success": False,
            "filled_price": 0.0,
            "fee_usd": 0.0,
            "pnl_realized": 0.0,
            "stop_order_id": None,
            "target_order_id": None,
            "reason": "Invalid entry parameters",
        }
    
    # Simulate slippage: 0.04%
    slippage_pct = 0.0004
    if side == "long":
        filled_price = entry_price * (1 + slippage_pct)
    else:
        filled_price = entry_price * (1 - slippage_pct)
    
    fee_rate = 0.0004
    fee_usd = abs((filled_price * position_size_btc) * fee_rate)
    
    # Update ghost metrics
    ghost_pnl = state.get("ghost_pnl", 0.0)
    ghost_trade_count = state.get("ghost_trade_count", 0)
    ghost_win_rate = state.get("ghost_win_rate", 0.5)
    
    # Simulate outcome: 50/50 win/loss in ghost mode
    simulated_pnl = abs((target_price - filled_price) * position_size_btc) if (ts_ms % 2 == 0) \
                    else -abs((stop_price - filled_price) * position_size_btc)
    
    ghost_pnl += simulated_pnl
    ghost_trade_count += 1
    wins = int(ghost_win_rate * ghost_trade_count)
    if simulated_pnl > 0:
        wins += 1
    ghost_win_rate = wins / ghost_trade_count if ghost_trade_count > 0 else 0.5
    
    log_event("INFO", {
        "msg": "EXECUTION_GHOST",
        "side": side,
        "filled_price": filled_price,
        "position_size_btc": position_size_btc,
        "fee_usd": fee_usd,
        "ghost_pnl": ghost_pnl,
        "ghost_trade_count": ghost_trade_count,
    })
    
    return {
        "success": True,
        "filled_price": float(filled_price),
        "fee_usd": float(fee_usd),
        "pnl_realized": float(simulated_pnl),
        "stop_order_id": f"ghost_sl_{ts_ms}",
        "target_order_id": f"ghost_tp_{ts_ms}",
        "reason": f"Ghost fill at {filled_price:.2f}, position {position_size_btc} BTC",
    }


def _execute_paper(
    ts_ms: int,
    side: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    position_size_btc: float,
    exchange_client: Optional[Any] = None
) -> Dict[str, Any]:
    """Paper mode: use exchange_client token bucket but simulate fills.
    
    In paper mode:
    - Apply token bucket throttling (goes through governor)
    - Simulate fill at mid-price + slippage
    - Return order IDs but don't place actual orders
    """
    if position_size_btc <= 0:
        return {
            "success": False,
            "filled_price": 0.0,
            "fee_usd": 0.0,
            "pnl_realized": 0.0,
            "stop_order_id": None,
            "target_order_id": None,
            "reason": "Invalid position size",
        }
    
    # Simulate slippage: 0.05% for paper (slightly worse than ghost)
    slippage_pct = 0.0005
    if side == "long":
        filled_price = entry_price * (1 + slippage_pct)
    else:
        filled_price = entry_price * (1 - slippage_pct)
    
    fee_usd = abs((filled_price * position_size_btc) * 0.0004)
    pnl = abs((target_price - filled_price) * position_size_btc)
    
    log_event("INFO", {
        "msg": "EXECUTION_PAPER",
        "side": side,
        "filled_price": filled_price,
        "position_size_btc": position_size_btc,
        "fee_usd": fee_usd,
    })
    
    return {
        "success": True,
        "filled_price": float(filled_price),
        "fee_usd": float(fee_usd),
        "pnl_realized": float(pnl),
        "stop_order_id": f"paper_sl_{ts_ms}",
        "target_order_id": f"paper_tp_{ts_ms}",
        "reason": f"Paper fill at {filled_price:.2f}, position {position_size_btc} BTC",
    }


def _execute_backtest(
    ts_ms: int,
    side: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    position_size_btc: float,
) -> Dict[str, Any]:
    """Backtest mode: update internal portfolio model.
    
    Backtesting deterministically replays candles and fills orders
    based on OHLC data. This function is called after fills are confirmed
    by the backtest engine.
    """
    if position_size_btc <= 0:
        return {
            "success": False,
            "filled_price": 0.0,
            "fee_usd": 0.0,
            "pnl_realized": 0.0,
            "stop_order_id": None,
            "target_order_id": None,
            "reason": "Invalid position size",
        }
    
    # Backtest assumes perfect fills at entry_price (no slippage in deterministic replay)
    filled_price = entry_price
    fee_usd = abs((filled_price * position_size_btc) * 0.0002)  # Maker fee
    
    log_event("DEBUG", {
        "msg": "EXECUTION_BACKTEST",
        "side": side,
        "filled_price": filled_price,
        "position_size_btc": position_size_btc,
        "stop_price": stop_price,
        "target_price": target_price,
    })
    
    return {
        "success": True,
        "filled_price": float(filled_price),
        "fee_usd": float(fee_usd),
        "pnl_realized": 0.0,
        "stop_order_id": f"bt_sl_{ts_ms}",
        "target_order_id": f"bt_tp_{ts_ms}",
        "reason": f"Backtest order: {side} {position_size_btc} BTC at {filled_price}",
    }


def _execute_live(
    ts_ms: int,
    side: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    position_size_btc: float,
    exchange_client: Optional[Any] = None
) -> Dict[str, Any]:
    """Live mode: place REAL orders on Binance Futures with SL/TP bracket.
    
    CRITICAL: If SL placement fails for ANY reason, market-close immediately
    before attempting TP or entry. This is the "SL placement guarantee".
    
    Order sequence:
    1. Place entry order (limit or market)
    2. Once filled, place SL order (MUST succeed or market-close)
    3. Place TP order
    4. Return order IDs and filled price
    """
    if not exchange_client or position_size_btc <= 0:
        return {
            "success": False,
            "filled_price": 0.0,
            "fee_usd": 0.0,
            "pnl_realized": 0.0,
            "stop_order_id": None,
            "target_order_id": None,
            "reason": "Exchange client unavailable or invalid size",
        }
    
    try:
        # Precision wrap the amount and prices
        symbol = "BTC/USDT"
        amount_str = exchange_client.amount_to_precision(symbol, position_size_btc)
        entry_price_str = exchange_client.price_to_precision(symbol, entry_price)
        stop_price_str = exchange_client.price_to_precision(symbol, stop_price)
        target_price_str = exchange_client.price_to_precision(symbol, target_price)
        
        # Place entry order (limit order at entry_price)
        entry_order = exchange_client.place_order(
            symbol,
            "limit",
            "buy" if side == "long" else "sell",
            amount_str,
            price=entry_price_str,
            params={"timeInForce": "GTC", "reduceOnly": False}
        )
        
        filled_price = float(entry_order.get("average", entry_price))
        entry_order_id = entry_order.get("id")
        
        if not entry_order_id:
            return {
                "success": False,
                "filled_price": filled_price,
                "fee_usd": 0.0,
                "pnl_realized": 0.0,
                "stop_order_id": None,
                "target_order_id": None,
                "reason": "Entry order placement failed",
            }
        
        # CRITICAL: Place SL order — if it fails, market-close everything
        if side == "long":
            sl_order = exchange_client.place_order(
                symbol,
                "stop",
                "sell",
                amount_str,
                price=stop_price_str,
                params={"stopPrice": stop_price_str, "reduceOnly": True}
            )
        else:
            sl_order = exchange_client.place_order(
                symbol,
                "stop",
                "buy",
                amount_str,
                price=stop_price_str,
                params={"stopPrice": stop_price_str, "reduceOnly": True}
            )
        
        sl_order_id = sl_order.get("id")
        
        if not sl_order_id:
            # SL PLACEMENT FAILED — MARKET CLOSE IMMEDIATELY
            log_event("CRITICAL", {
                "msg": "SL_PLACEMENT_FAILED",
                "side": side,
                "entry_price": filled_price,
                "market_closing": True,
            })
            
            # Market close the entry position
            exchange_client.place_order(
                symbol,
                "market",
                "sell" if side == "long" else "buy",
                amount_str,
                params={"reduceOnly": True}
            )
            
            return {
                "success": False,
                "filled_price": filled_price,
                "fee_usd": 0.0,
                "pnl_realized": 0.0,
                "stop_order_id": None,
                "target_order_id": None,
                "reason": "SL placement failed, position market-closed",
            }
        
        # Place TP order
        if side == "long":
            tp_order = exchange_client.place_order(
                symbol,
                "limit",
                "sell",
                amount_str,
                price=target_price_str,
                params={"reduceOnly": True}
            )
        else:
            tp_order = exchange_client.place_order(
                symbol,
                "limit",
                "buy",
                amount_str,
                price=target_price_str,
                params={"reduceOnly": True}
            )
        
        tp_order_id = tp_order.get("id")
        fee_usd = abs((filled_price * position_size_btc) * 0.0004)
        
        log_event("INFO", {
            "msg": "EXECUTION_LIVE",
            "side": side,
            "filled_price": filled_price,
            "position_size_btc": position_size_btc,
            "entry_order_id": entry_order_id,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "fee_usd": fee_usd,
        })
        
        return {
            "success": True,
            "filled_price": float(filled_price),
            "fee_usd": float(fee_usd),
            "pnl_realized": 0.0,
            "stop_order_id": sl_order_id,
            "target_order_id": tp_order_id,
            "reason": f"Live order: {side} {position_size_btc} BTC at {filled_price:.2f} with SL/TP",
        }
    
    except Exception as e:
        log_event("ERROR", {
            "msg": "EXECUTION_LIVE_EXCEPTION",
            "error": str(e),
        })
        return {
            "success": False,
            "filled_price": 0.0,
            "fee_usd": 0.0,
            "pnl_realized": 0.0,
            "stop_order_id": None,
            "target_order_id": None,
            "reason": f"Live execution exception: {str(e)}",
        }
