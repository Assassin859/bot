"""Configuration loader for the trading bot.

Loads `config.yaml` and exposes a typed `Config` dataclass.
Includes leverage and futures trading configuration.
Supports environment variable overrides for sensitive data (API keys).
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
import os

import yaml
from pydantic import BaseModel

# Load environment variables from .env file (if present)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not required, but recommended for .env support


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


# ============================================================
# LEVERAGE & FUTURES CONFIGURATION
# ============================================================

# User-facing leverage constants
DEFAULT_LEVERAGE = 5
MAX_LEVERAGE = 20
MIN_LEVERAGE = 1
DEFAULT_TRADING_CAPITAL = 1000.0  # USDT
DEFAULT_MAX_RISK_PCT = 2.0  # per trade
DEFAULT_MAX_DRAWDOWN_PCT = 10.0  # account kill switch

# Risk & safety constants
LIQUIDATION_BUFFER_PCT = 10.0  # Keep 10% SL margin above liquidation
MARGIN_DANGER_ZONE_PCT = 90.0  # Warn above this utilization
MARGIN_FORCE_CLOSE_PCT = 95.0  # Auto-close above this utilization

# Binance Futures limits
BINANCE_MAX_LEVERAGE = 20
BINANCE_MIN_LEVERAGE = 1
BINANCE_TAKER_FEE_PCT = 0.04
BINANCE_MAKER_FEE_PCT = 0.02


@dataclass
class LeverageConfig:
    """User configuration for leverage trading.
    
    Attributes:
        trading_capital: Amount of USDT allocated to futures trading
        leverage: Leverage multiplier (1-20x)
        max_risk_pct: Maximum risk per trade as % of account
        max_drawdown_pct: Maximum account drawdown before stopping
        margin_mode: "isolated" or "cross" margin
    """
    trading_capital: float
    leverage: int
    max_risk_pct: float
    max_drawdown_pct: float
    margin_mode: Literal["isolated", "cross"] = "isolated"


def validate_leverage_config(config: LeverageConfig) -> tuple[bool, str]:
    """
    Validate leverage configuration.
    
    Args:
        config: LeverageConfig to validate
    
    Returns:
        (is_valid, message) tuple
    """
    if config.trading_capital <= 0 or config.trading_capital > 100000:
        return False, f"Trading capital must be 0 < x <= 100000, got {config.trading_capital}"
    
    if config.leverage < MIN_LEVERAGE or config.leverage > MAX_LEVERAGE:
        return False, f"Leverage must be {MIN_LEVERAGE}-{MAX_LEVERAGE}, got {config.leverage}"
    
    if config.max_risk_pct <= 0.5 or config.max_risk_pct > 10:
        return False, f"Risk % must be 0.5-10, got {config.max_risk_pct}"
    
    if config.max_drawdown_pct < 5 or config.max_drawdown_pct > 50:
        return False, f"Drawdown % must be 5-50, got {config.max_drawdown_pct}"
    
    if config.margin_mode not in ("isolated", "cross"):
        return False, f"Margin mode must be 'isolated' or 'cross', got {config.margin_mode}"
    
    return True, "✅ Configuration valid"


# ============================================================
# EXISTING CONFIG CLASSES (PRESERVED)
# ============================================================


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
    """Load config from YAML file, with environment variable overrides for sensitive data."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    
    data = yaml.safe_load(p.read_text())
    
    # Override API keys from environment variables if present
    if data.get("exchange"):
        data["exchange"]["api_key"] = os.getenv("BINANCE_API_KEY", data["exchange"].get("api_key"))
        data["exchange"]["api_secret"] = os.getenv("BINANCE_API_SECRET", data["exchange"].get("api_secret"))
    
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
