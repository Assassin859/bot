"""Configuration loader for the trading bot.

Loads `config.yaml` and exposes a typed `Config` dataclass.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class ExchangeConfig(BaseModel):
    name: str
    api_key: str | None = None
    api_secret: str | None = None
    testnet: bool = True


class StrategyConfig(BaseModel):
    trend_timeframe: str
    signal_timeframe: str
    ema_slow: int
    ema_fast: int
    zscore_period: int
    zscore_threshold: float
    cvd_lookback: int
    atr_period: int
    extended_move_atr_multiplier: float
    extended_move_pivot_bars: int
    extended_move_lookback_bars: int
    spread_max_pct: float
    candle_history: int
    min_composite_score_short: int
    min_composite_score_long: int


class RiskConfig(BaseModel):
    account_risk_per_trade_pct: float
    max_position_notional_usdt: float
    sl_atr_multiplier: float
    tp_atr_multiplier: float
    ghost_base_balance: float
    max_daily_trades: int
    max_consecutive_losses: int
    cooldown_minutes: int
    daily_drawdown_kill_pct: float
    max_hold_minutes: int


class ExternalFeedsConfig(BaseModel):
    binance_futures_cache_minutes: int
    fear_greed_cache_minutes: int
    onchain_cache_minutes: int
    onchain_api_key: str | None = None
    funding_rate_threshold: float
    ls_ratio_high: float
    ls_ratio_low: float
    onchain_flow_threshold_btc: float
    fear_greed_extreme_fear: int
    fear_greed_extreme_greed: int


class GovernorConfig(BaseModel):
    max_calls: int
    window_seconds: int


class BinanceTimeConfig(BaseModel):
    sync_interval_minutes: int


class Config(BaseModel):
    exchange: ExchangeConfig
    trading: dict[str, Any]
    strategy: StrategyConfig
    risk: RiskConfig
    execution: dict[str, Any]
    external_feeds: ExternalFeedsConfig
    governor: GovernorConfig
    binance_time: BinanceTimeConfig


def load_config(path: str | Path = "config.yaml") -> Config:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    data = yaml.safe_load(p.read_text())
    return Config(**data)


# convenience
try:
    cfg = load_config()
except Exception:
    cfg = None

# Module-level constants for easy access
BINANCE_SYMBOL = "BTC/USDT"  # BTC/USDT Futures pair
EXEC_CONFIG = {
    "account_risk_per_trade_pct": 1.0,
    "max_position_notional_usdt": 400.0,
    "max_daily_trades": 10,
    "max_consecutive_losses": 3,
    "cooldown_minutes": 45,
    "daily_drawdown_kill_pct": -2.0,
    "max_hold_minutes": 90,
}
