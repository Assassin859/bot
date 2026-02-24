"""Structured logging: JSON to stdout and Redis event streams.

Provides log_event() for structured JSON logging and optional Redis-backed
event streams for debugging and audit trails.
"""
from __future__ import annotations
import json
import sys
from typing import Any, Dict, Optional
from datetime import datetime


def log_event(level: str, event: Dict[str, Any]) -> None:
    """Log a structured event as JSON with timestamp and level.
    
    Args:
        level: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        event: Dictionary with event data
    
    Creates output like:
        {"level": "INFO", "timestamp": "2026-02-24T12:34:56Z", "msg": "...", ...}
    
    This outputs to stdout which is captured by:
    - docker logs in production
    - pytest capture in testing
    - dashboard log panel in UI
    """
    payload = {
        "level": level,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **event
    }
    print(json.dumps(payload), file=sys.stdout)
    sys.stdout.flush()


def format_event_for_redis(level: str, event: Dict[str, Any]) -> str:
    """Format an event for storage in Redis streams.
    
    Returns JSON string suitable for XADD to Redis streams.
    """
    payload = {
        "level": level,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **event
    }
    return json.dumps(payload)


async def write_event_to_redis_stream(
    redis_state,
    stream_name: str,
    level: str,
    event: Dict[str, Any],
    max_stream_length: int = 1000
) -> Optional[str]:
    """Write event to Redis stream (async).
    
    Args:
        redis_state: RedisState instance
        stream_name: Name of the stream (e.g. "execution_events", "rejections")
        level: Log level
        event: Event data
        max_stream_length: Max entries to keep in stream (FIFO trim)
    
    Returns:
        Event ID from Redis, or None on error
    """
    try:
        message = format_event_for_redis(level, event)
        # This would call redis_state.xadd(stream_name, message)
        # Placeholder for actual implementation
        log_event("DEBUG", {
            "msg": "Redis stream write placeholder",
            "stream": stream_name,
        })
        return None
    except Exception as e:
        log_event("ERROR", {
            "msg": "Failed to write to Redis stream",
            "stream": stream_name,
            "error": str(e),
        })
        return None


# Standard event categories

def log_startup(msg: str) -> None:
    """Log startup event."""
    log_event("INFO", {"msg": "STARTUP", "details": msg})


def log_strategy_gate(step: int, passed: bool, reason: str = "") -> None:
    """Log strategy gate evaluation."""
    log_event("INFO", {
        "msg": "STRATEGY_GATE",
        "step": step,
        "passed": passed,
        "reason": reason,
    })


def log_signal_received(side: str, composite_score: float) -> None:
    """Log when strategy.evaluate_signal returns a signal."""
    log_event("INFO", {
        "msg": "SIGNAL_RECEIVED",
        "side": side,
        "composite_score": composite_score,
    })


def log_signal_rejected(reason: str) -> None:
    """Log when a signal is rejected by risk checks."""
    log_event("INFO", {
        "msg": "SIGNAL_REJECTED",
        "reason": reason,
    })


def log_execution(mode: str, side: str, filled_price: float, position_size: float) -> None:
    """Log execution of an order."""
    log_event("INFO", {
        "msg": "EXECUTION",
        "mode": mode,
        "side": side,
        "filled_price": filled_price,
        "position_size": position_size,
    })


def log_position_closed(pnl: float, pnl_pct: float, reason: str) -> None:
    """Log position closure."""
    log_event("INFO", {
        "msg": "POSITION_CLOSED",
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "reason": reason,
    })


def log_circuit_breaker_trip(breaker: str, reason: str) -> None:
    """Log circuit breaker activation."""
    log_event("WARNING", {
        "msg": "CIRCUIT_BREAKER",
        "breaker": breaker,
        "reason": reason,
    })


def log_token_bucket_throttle(caller: str, sleep_sec: float) -> None:
    """Log token bucket rate limiting."""
    log_event("WARNING", {
        "msg": "TOKEN_BUCKET_THROTTLE",
        "caller": caller,
        "sleep_sec": sleep_sec,
    })


def log_websocket_stale(age_sec: float) -> None:
    """Log stale WebSocket data (data freshness guard triggered)."""
    log_event("CRITICAL", {
        "msg": "WEBSOCKET_STALE",
        "age_sec": age_sec,
    })


def log_external_feed_fallback(feed: str, reason: str) -> None:
    """Log external feed fallback to neutral defaults."""
    log_event("INFO", {
        "msg": "EXTERNAL_FEED_FALLBACK",
        "feed": feed,
        "reason": reason,
    })


def log_redis_connection(status: str, error: Optional[str] = None) -> None:
    """Log Redis connection events."""
    if error:
        log_event("ERROR", {"msg": "REDIS_CONNECTION", "status": status, "error": error})
    else:
        log_event("INFO", {"msg": "REDIS_CONNECTION", "status": status})
