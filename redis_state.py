"""Redis state layer: the ONLY module to touch Redis directly.

This module implements typed Pydantic models for the Redis schema and
provides async typed getters/setters plus `read_full_snapshot()` which
atomically reads all keys on startup. All raw Redis key strings live here.
"""
from __future__ import annotations
import os
import json
from typing import Optional, Any, Dict
import redis.asyncio as aioredis
from pydantic import BaseModel
from logging_utils import log_event


# Redis key constants (raw keys live only in this file)
K_AUTOMATION_ENABLED = "automation_enabled"
K_ACTIVE_POSITION = "active_position"
K_ACCOUNT_BALANCE = "account_balance"
K_ROLLING_24H_PNL = "rolling_24h_pnl"
K_MODE = "mode"
K_DAILY_TRADE_COUNT = "daily_trade_count"
K_DAILY_TRADE_DATE = "daily_trade_date"
K_CONSECUTIVE_LOSSES = "consecutive_losses"
K_COOLDOWN_UNTIL = "cooldown_until"
K_FUNDING_RATE_CACHE = "funding_rate_cache"
K_OI_CACHE = "oi_cache"
K_LS_RATIO_CACHE = "ls_ratio_cache"
K_FEAR_GREED_CACHE = "fear_greed_cache"
K_ONCHAIN_FLOW_CACHE = "onchain_flow_cache"
K_BACKTEST_VALIDATED = "backtest_validated"
K_BACKTEST_VALIDATED_HASH = "backtest_validated_config_hash"
K_GHOST_PNL = "ghost_pnl"
K_GHOST_TRADE_COUNT = "ghost_trade_count"
K_GHOST_WIN_RATE = "ghost_win_rate"

# ============================================================
# LEVERAGE CONFIGURATION KEYS (NEW)
# ============================================================
K_LEVERAGE_TRADING_CAPITAL = "leverage:trading_capital"
K_LEVERAGE_MULTIPLIER = "leverage:leverage"  # 1-20x
K_LEVERAGE_MAX_RISK_PCT = "leverage:max_risk_pct"
K_LEVERAGE_MAX_DRAWDOWN_PCT = "leverage:max_drawdown_pct"
K_LEVERAGE_MARGIN_MODE = "leverage:margin_mode"  # "isolated" or "cross"
K_LEVERAGE_CONFIG_UPDATED = "leverage:config_updated"  # ISO8601 timestamp

# ============================================================
# LEVERAGE STATE KEYS (NEW)
# ============================================================
K_LEVERAGE_CURRENT = "leverage:current_leverage"
K_LEVERAGE_LIQUIDATION_PRICE = "leverage:liquidation_price"
K_LEVERAGE_MARGIN_UTILIZATION = "leverage:margin_utilization_pct"
K_LEVERAGE_COLLATERAL_USED = "leverage:collateral_used_usdt"
K_LEVERAGE_MAX_POSITION_NOTIONAL = "leverage:max_position_notional"

# ============================================================
# RISK TRACKING KEYS (NEW)
# ============================================================
K_RISK_DAILY_REALIZED_PNL = "risk:daily_realized_pnl"
K_RISK_UNREALIZED_PNL = "risk:unrealized_pnl"
K_RISK_LARGEST_LOSS_STREAK = "risk:largest_loss_streak"
K_RISK_EQUITY_CURVE = "risk:equity_curve"  # JSON array of hourly snapshots

# ============================================================
# BOT CONTROL KEYS (NEW)
# ============================================================
K_BOT_MODE = "bot:mode"  # Current mode (backtest|paper|ghost|live)
K_BOT_PROCESS_ID = "bot:process_id"  # Running bot PID
K_BOT_STATUS = "bot:status"  # running|stopped|error
K_BOT_STARTED_AT = "bot:started_at"  # ISO8601 timestamp


class ActivePosition(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    position_size_btc: float
    entry_time_utc: int
    stop_order_id: str
    target_order_id: str


class CacheEntry(BaseModel):
    value: Any
    timestamp: int


class RedisSnapshot(BaseModel):
    automation_enabled: bool
    active_position: Optional[ActivePosition] = None
    account_balance: float = 0.0
    rolling_24h_pnl: float = 0.0
    mode: str = "paper"
    daily_trade_count: int = 0
    daily_trade_date: str = "1970-01-01"
    consecutive_losses: int = 0
    cooldown_until: int = 0
    funding_rate_cache: Optional[CacheEntry] = None
    oi_cache: Optional[CacheEntry] = None
    ls_ratio_cache: Optional[CacheEntry] = None
    fear_greed_cache: Optional[CacheEntry] = None
    onchain_flow_cache: Optional[CacheEntry] = None
    backtest_validated: bool = False
    backtest_validated_config_hash: Optional[str] = None
    ghost_pnl: float = 0.0
    ghost_trade_count: int = 0
    ghost_win_rate: float = 0.0
    # Leverage configuration (NEW)
    leverage_trading_capital: float = 1000.0
    leverage_multiplier: int = 5
    leverage_max_risk_pct: float = 2.0
    leverage_max_drawdown_pct: float = 10.0
    leverage_margin_mode: str = "isolated"
    leverage_config_updated: Optional[str] = None
    # Leverage state (NEW)
    leverage_current: int = 1
    leverage_liquidation_price: float = 0.0
    leverage_margin_utilization_pct: float = 0.0
    leverage_collateral_used_usdt: float = 0.0
    leverage_max_position_notional: float = 0.0
    # Risk tracking (NEW)
    risk_daily_realized_pnl: float = 0.0
    risk_unrealized_pnl: float = 0.0
    risk_largest_loss_streak: int = 0
    risk_equity_curve: Optional[list[dict[str, Any]]] = None


class RedisState:
    def __init__(self, url: Optional[str] = None):
        url = url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client = aioredis.from_url(url, decode_responses=True)

    async def close(self) -> None:
        try:
            await self._client.close()
        except Exception:
            pass

    # --- helpers -------------------------------------------------
    @staticmethod
    def _to_bool(s: Optional[str]) -> bool:
        if s is None:
            return False
        return str(s).lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _from_bool(v: bool) -> str:
        return "1" if v else "0"

    @staticmethod
    def _loads_json(s: Optional[str]) -> Optional[Any]:
        if s is None:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None

    @staticmethod
    def _dumps_json(v: Any) -> str:
        return json.dumps(v)

    # --- read full snapshot (atomic-ish) ------------------------
    async def read_full_snapshot(self) -> RedisSnapshot:
        """Read all keys and return a RedisSnapshot.

        If `automation_enabled` is missing on startup, set it to False and log WARNING: AUTOMATION_DEFAULTED_OFF.
        """
        # Gather keys in a single pipeline
        keys = [
            K_AUTOMATION_ENABLED,
            K_ACTIVE_POSITION,
            K_ACCOUNT_BALANCE,
            K_ROLLING_24H_PNL,
            K_MODE,
            K_DAILY_TRADE_COUNT,
            K_DAILY_TRADE_DATE,
            K_CONSECUTIVE_LOSSES,
            K_COOLDOWN_UNTIL,
            K_FUNDING_RATE_CACHE,
            K_OI_CACHE,
            K_LS_RATIO_CACHE,
            K_FEAR_GREED_CACHE,
            K_ONCHAIN_FLOW_CACHE,
            K_BACKTEST_VALIDATED,
            K_BACKTEST_VALIDATED_HASH,
            K_GHOST_PNL,
            K_GHOST_TRADE_COUNT,
            K_GHOST_WIN_RATE,
            # Leverage config
            K_LEVERAGE_TRADING_CAPITAL,
            K_LEVERAGE_MULTIPLIER,
            K_LEVERAGE_MAX_RISK_PCT,
            K_LEVERAGE_MAX_DRAWDOWN_PCT,
            K_LEVERAGE_MARGIN_MODE,
            K_LEVERAGE_CONFIG_UPDATED,
            # Leverage state
            K_LEVERAGE_CURRENT,
            K_LEVERAGE_LIQUIDATION_PRICE,
            K_LEVERAGE_MARGIN_UTILIZATION,
            K_LEVERAGE_COLLATERAL_USED,
            K_LEVERAGE_MAX_POSITION_NOTIONAL,
            # Risk tracking
            K_RISK_DAILY_REALIZED_PNL,
            K_RISK_UNREALIZED_PNL,
            K_RISK_LARGEST_LOSS_STREAK,
            K_RISK_EQUITY_CURVE,
        ]

        pipe = self._client.pipeline()
        for k in keys:
            pipe.get(k)
        vals = await pipe.execute()

        mapping = dict(zip(keys, vals))

        # automation_enabled default handling
        auto_val = mapping.get(K_AUTOMATION_ENABLED)
        if auto_val is None:
            # Set default False in Redis and log WARNING
            await self._client.set(K_AUTOMATION_ENABLED, self._from_bool(False))
            log_event("WARNING", {"msg": "AUTOMATION_DEFAULTED_OFF"})
            automation_enabled = False
        else:
            automation_enabled = self._to_bool(auto_val)

        # active_position (JSON)
        active_raw = mapping.get(K_ACTIVE_POSITION)
        active = None
        if active_raw is not None:
            try:
                active_obj = json.loads(active_raw)
                active = ActivePosition(**active_obj)
            except Exception:
                active = None

        def _float_of(key, default=0.0):
            v = mapping.get(key)
            try:
                return float(v) if v is not None else default
            except Exception:
                return default

        def _int_of(key, default=0):
            v = mapping.get(key)
            try:
                return int(v) if v is not None else default
            except Exception:
                return default

        def _str_of(key, default=""):
            v = mapping.get(key)
            return v if v is not None else default

        funding_cache = self._loads_json(mapping.get(K_FUNDING_RATE_CACHE))
        oi_cache = self._loads_json(mapping.get(K_OI_CACHE))
        ls_cache = self._loads_json(mapping.get(K_LS_RATIO_CACHE))
        fg_cache = self._loads_json(mapping.get(K_FEAR_GREED_CACHE))
        onchain_cache = self._loads_json(mapping.get(K_ONCHAIN_FLOW_CACHE))
        
        # Parse equity curve from JSON
        equity_curve = None
        equity_raw = self._loads_json(mapping.get(K_RISK_EQUITY_CURVE))
        if isinstance(equity_raw, list):
            equity_curve = equity_raw

        snapshot = RedisSnapshot(
            automation_enabled=automation_enabled,
            active_position=active,
            account_balance=_float_of(K_ACCOUNT_BALANCE, 0.0),
            rolling_24h_pnl=_float_of(K_ROLLING_24H_PNL, 0.0),
            mode=_str_of(K_MODE, "paper"),
            daily_trade_count=_int_of(K_DAILY_TRADE_COUNT, 0),
            daily_trade_date=_str_of(K_DAILY_TRADE_DATE, "1970-01-01"),
            consecutive_losses=_int_of(K_CONSECUTIVE_LOSSES, 0),
            cooldown_until=_int_of(K_COOLDOWN_UNTIL, 0),
            funding_rate_cache=CacheEntry(**funding_cache) if funding_cache else None,
            oi_cache=CacheEntry(**oi_cache) if oi_cache else None,
            ls_ratio_cache=CacheEntry(**ls_cache) if ls_cache else None,
            fear_greed_cache=CacheEntry(**fg_cache) if fg_cache else None,
            onchain_flow_cache=CacheEntry(**onchain_cache) if onchain_cache else None,
            backtest_validated=self._to_bool(mapping.get(K_BACKTEST_VALIDATED)),
            backtest_validated_config_hash=_str_of(K_BACKTEST_VALIDATED_HASH, None),
            ghost_pnl=_float_of(K_GHOST_PNL, 0.0),
            ghost_trade_count=_int_of(K_GHOST_TRADE_COUNT, 0),
            ghost_win_rate=_float_of(K_GHOST_WIN_RATE, 0.0),
            # Leverage configuration
            leverage_trading_capital=_float_of(K_LEVERAGE_TRADING_CAPITAL, 1000.0),
            leverage_multiplier=_int_of(K_LEVERAGE_MULTIPLIER, 5),
            leverage_max_risk_pct=_float_of(K_LEVERAGE_MAX_RISK_PCT, 2.0),
            leverage_max_drawdown_pct=_float_of(K_LEVERAGE_MAX_DRAWDOWN_PCT, 10.0),
            leverage_margin_mode=_str_of(K_LEVERAGE_MARGIN_MODE, "isolated"),
            leverage_config_updated=_str_of(K_LEVERAGE_CONFIG_UPDATED, None),
            # Leverage state
            leverage_current=_int_of(K_LEVERAGE_CURRENT, 1),
            leverage_liquidation_price=_float_of(K_LEVERAGE_LIQUIDATION_PRICE, 0.0),
            leverage_margin_utilization_pct=_float_of(K_LEVERAGE_MARGIN_UTILIZATION, 0.0),
            leverage_collateral_used_usdt=_float_of(K_LEVERAGE_COLLATERAL_USED, 0.0),
            leverage_max_position_notional=_float_of(K_LEVERAGE_MAX_POSITION_NOTIONAL, 0.0),
            # Risk tracking
            risk_daily_realized_pnl=_float_of(K_RISK_DAILY_REALIZED_PNL, 0.0),
            risk_unrealized_pnl=_float_of(K_RISK_UNREALIZED_PNL, 0.0),
            risk_largest_loss_streak=_int_of(K_RISK_LARGEST_LOSS_STREAK, 0),
            risk_equity_curve=equity_curve,
        )

        return snapshot

    async def get_snapshot(self) -> RedisSnapshot:
        """Compatibility wrapper for older code: returns the current RedisSnapshot."""
        return await self.read_full_snapshot()

    # --- typed getters/setters ---------------------------------
    async def get_automation_enabled(self) -> bool:
        v = await self._client.get(K_AUTOMATION_ENABLED)
        return self._to_bool(v)

    async def set_automation_enabled(self, value: bool) -> None:
        await self._client.set(K_AUTOMATION_ENABLED, self._from_bool(value))

    # =================================================================
    # BOT MODE & PROCESS MANAGEMENT
    # =================================================================
    async def get_mode(self) -> str:
        """Get current trading mode (backtest, paper, ghost, live)."""
        v = await self._client.get(K_BOT_MODE)
        return v if v is not None else "paper"

    async def set_mode(self, mode: str) -> None:
        """Set trading mode (backtest, paper, ghost, live)."""
        valid_modes = ["backtest", "paper", "ghost", "live"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")
        await self._client.set(K_BOT_MODE, mode)

    async def get_bot_process_id(self) -> Optional[int]:
        """Get PID of running bot process."""
        v = await self._client.get(K_BOT_PROCESS_ID)
        try:
            return int(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    async def set_bot_process_id(self, pid: int) -> None:
        """Store bot process ID."""
        await self._client.set(K_BOT_PROCESS_ID, str(pid))

    async def clear_bot_process_id(self) -> None:
        """Clear process ID when bot stops."""
        await self._client.delete(K_BOT_PROCESS_ID)

    async def get_bot_status(self) -> str:
        """Get bot status (running|stopped|error)."""
        v = await self._client.get(K_BOT_STATUS)
        return v if v is not None else "stopped"

    async def set_bot_status(self, status: str) -> None:
        """Set bot status."""
        valid_statuses = ["running", "stopped", "error"]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")
        await self._client.set(K_BOT_STATUS, status)

    async def get_bot_started_at(self) -> Optional[str]:
        """Get bot start timestamp."""
        return await self._client.get(K_BOT_STARTED_AT)

    async def set_bot_started_at(self, timestamp: str) -> None:
        """Set bot start timestamp."""
        await self._client.set(K_BOT_STARTED_AT, timestamp)

    async def get_active_position(self) -> Optional[ActivePosition]:
        raw = await self._client.get(K_ACTIVE_POSITION)
        if raw is None:
            return None
        try:
            return ActivePosition(**json.loads(raw))
        except Exception:
            return None

    async def set_active_position(self, pos: Optional[ActivePosition]) -> None:
        if pos is None:
            await self._client.delete(K_ACTIVE_POSITION)
        else:
            await self._client.set(K_ACTIVE_POSITION, self._dumps_json(pos.dict()))

    async def get_account_balance(self) -> float:
        v = await self._client.get(K_ACCOUNT_BALANCE)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    async def set_account_balance(self, amount: float) -> None:
        await self._client.set(K_ACCOUNT_BALANCE, str(amount))

    # --- Leverage configuration getters/setters (NEW) ----------
    async def get_leverage_config(self) -> dict:
        """Get all leverage configuration as dict."""
        return {
            "trading_capital": await self.get_leverage_trading_capital(),
            "leverage": await self.get_leverage_multiplier(),
            "max_risk_pct": await self.get_leverage_max_risk_pct(),
            "max_drawdown_pct": await self.get_leverage_max_drawdown_pct(),
            "margin_mode": await self.get_leverage_margin_mode(),
            "config_updated": await self.get_leverage_config_updated(),
        }

    async def set_leverage_config(self, config: dict) -> None:
        """Set multiple leverage configuration keys atomically.

        Expects keys: trading_capital, leverage, max_risk_pct, max_drawdown_pct, margin_mode
        """
        # Prepare values with sane defaults/validation
        trading_capital = float(config.get("trading_capital", 1000.0))
        leverage = int(config.get("leverage", 5))
        max_risk_pct = float(config.get("max_risk_pct", 2.0))
        max_drawdown_pct = float(config.get("max_drawdown_pct", 10.0))
        margin_mode = config.get("margin_mode", "isolated")

        # Timestamp
        from datetime import datetime
        ts = datetime.utcnow().isoformat() + "Z"

        pipe = self._client.pipeline()
        pipe.set(K_LEVERAGE_TRADING_CAPITAL, str(trading_capital))
        pipe.set(K_LEVERAGE_MULTIPLIER, str(leverage))
        pipe.set(K_LEVERAGE_MAX_RISK_PCT, str(max_risk_pct))
        pipe.set(K_LEVERAGE_MAX_DRAWDOWN_PCT, str(max_drawdown_pct))
        pipe.set(K_LEVERAGE_MARGIN_MODE, margin_mode)
        pipe.set(K_LEVERAGE_CONFIG_UPDATED, ts)
        await pipe.execute()

    async def get_leverage_trading_capital(self) -> float:
        v = await self._client.get(K_LEVERAGE_TRADING_CAPITAL)
        try:
            return float(v) if v is not None else 1000.0
        except Exception:
            return 1000.0

    async def set_leverage_trading_capital(self, capital: float) -> None:
        await self._client.set(K_LEVERAGE_TRADING_CAPITAL, str(capital))

    async def get_leverage_multiplier(self) -> int:
        v = await self._client.get(K_LEVERAGE_MULTIPLIER)
        try:
            return int(v) if v is not None else 5
        except Exception:
            return 5

    async def set_leverage_multiplier(self, leverage: int) -> None:
        await self._client.set(K_LEVERAGE_MULTIPLIER, str(leverage))

    async def get_leverage_max_risk_pct(self) -> float:
        v = await self._client.get(K_LEVERAGE_MAX_RISK_PCT)
        try:
            return float(v) if v is not None else 2.0
        except Exception:
            return 2.0

    async def set_leverage_max_risk_pct(self, risk_pct: float) -> None:
        await self._client.set(K_LEVERAGE_MAX_RISK_PCT, str(risk_pct))

    async def get_leverage_max_drawdown_pct(self) -> float:
        v = await self._client.get(K_LEVERAGE_MAX_DRAWDOWN_PCT)
        try:
            return float(v) if v is not None else 10.0
        except Exception:
            return 10.0

    async def set_leverage_max_drawdown_pct(self, drawdown_pct: float) -> None:
        await self._client.set(K_LEVERAGE_MAX_DRAWDOWN_PCT, str(drawdown_pct))

    async def get_leverage_margin_mode(self) -> str:
        v = await self._client.get(K_LEVERAGE_MARGIN_MODE)
        return v if v in ("isolated", "cross") else "isolated"

    async def set_leverage_margin_mode(self, mode: str) -> None:
        if mode not in ("isolated", "cross"):
            raise ValueError(f"Invalid margin mode: {mode}")
        await self._client.set(K_LEVERAGE_MARGIN_MODE, mode)

    async def get_leverage_config_updated(self) -> str:
        v = await self._client.get(K_LEVERAGE_CONFIG_UPDATED)
        return v or ""

    async def set_leverage_config_updated(self, timestamp: str) -> None:
        await self._client.set(K_LEVERAGE_CONFIG_UPDATED, timestamp)

    # --- Leverage state getters/setters (NEW) -----------------
    async def get_leverage_state(self) -> dict:
        """Get all leverage state as dict."""
        return {
            "current_leverage": await self.get_leverage_current(),
            "liquidation_price": await self.get_leverage_liquidation_price(),
            "margin_utilization_pct": await self.get_leverage_margin_utilization(),
            "collateral_used_usdt": await self.get_leverage_collateral_used(),
            "max_position_notional": await self.get_leverage_max_position_notional(),
        }

    async def get_leverage_current(self) -> int:
        v = await self._client.get(K_LEVERAGE_CURRENT)
        try:
            return int(v) if v is not None else 1
        except Exception:
            return 1

    async def set_leverage_current(self, leverage: int) -> None:
        await self._client.set(K_LEVERAGE_CURRENT, str(leverage))

    async def get_leverage_liquidation_price(self) -> float:
        v = await self._client.get(K_LEVERAGE_LIQUIDATION_PRICE)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    async def set_leverage_liquidation_price(self, price: float) -> None:
        await self._client.set(K_LEVERAGE_LIQUIDATION_PRICE, str(price))

    async def get_leverage_margin_utilization(self) -> float:
        v = await self._client.get(K_LEVERAGE_MARGIN_UTILIZATION)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    async def set_leverage_margin_utilization(self, pct: float) -> None:
        await self._client.set(K_LEVERAGE_MARGIN_UTILIZATION, str(pct))

    async def get_leverage_collateral_used(self) -> float:
        v = await self._client.get(K_LEVERAGE_COLLATERAL_USED)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    async def set_leverage_collateral_used(self, usdt: float) -> None:
        await self._client.set(K_LEVERAGE_COLLATERAL_USED, str(usdt))

    async def get_leverage_max_position_notional(self) -> float:
        v = await self._client.get(K_LEVERAGE_MAX_POSITION_NOTIONAL)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    async def set_leverage_max_position_notional(self, notional: float) -> None:
        await self._client.set(K_LEVERAGE_MAX_POSITION_NOTIONAL, str(notional))

    # --- Risk tracking getters/setters (NEW) ------------------
    async def get_risk_tracking(self) -> dict:
        """Get all risk tracking metrics as dict."""
        return {
            "daily_realized_pnl": await self.get_risk_daily_realized_pnl(),
            "unrealized_pnl": await self.get_risk_unrealized_pnl(),
            "largest_loss_streak": await self.get_risk_largest_loss_streak(),
            "equity_curve": await self.get_risk_equity_curve(),
        }

    async def get_risk_daily_realized_pnl(self) -> float:
        v = await self._client.get(K_RISK_DAILY_REALIZED_PNL)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    async def set_risk_daily_realized_pnl(self, pnl: float) -> None:
        await self._client.set(K_RISK_DAILY_REALIZED_PNL, str(pnl))

    async def get_risk_unrealized_pnl(self) -> float:
        v = await self._client.get(K_RISK_UNREALIZED_PNL)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    async def set_risk_unrealized_pnl(self, pnl: float) -> None:
        await self._client.set(K_RISK_UNREALIZED_PNL, str(pnl))

    async def get_risk_largest_loss_streak(self) -> int:
        v = await self._client.get(K_RISK_LARGEST_LOSS_STREAK)
        try:
            return int(v) if v is not None else 0
        except Exception:
            return 0

    async def set_risk_largest_loss_streak(self, streak: int) -> None:
        await self._client.set(K_RISK_LARGEST_LOSS_STREAK, str(streak))

    async def get_risk_equity_curve(self) -> list[dict]:
        v = await self._client.get(K_RISK_EQUITY_CURVE)
        curve = self._loads_json(v)
        if isinstance(curve, list):
            return curve
        return []

    async def set_risk_equity_curve(self, curve: list[dict]) -> None:
        await self._client.set(K_RISK_EQUITY_CURVE, self._dumps_json(curve))

    # Additional setters/getters for caches and metrics
    async def set_cache(self, key: str, value: Dict[str, Any]) -> None:
        if key not in (K_FUNDING_RATE_CACHE, K_OI_CACHE, K_LS_RATIO_CACHE, K_FEAR_GREED_CACHE, K_ONCHAIN_FLOW_CACHE):
            raise ValueError("invalid cache key")
        await self._client.set(key, self._dumps_json(value))

    async def get_cache(self, key: str) -> Optional[CacheEntry]:
        raw = await self._client.get(key)
        if raw is None:
            return None
        j = self._loads_json(raw)
        if j is None:
            return None
        try:
            return CacheEntry(**j)
        except Exception:
            return None


# singleton instance used by other modules
redis_state = RedisState()
