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
        )

        return snapshot

    # --- typed getters/setters ---------------------------------
    async def get_automation_enabled(self) -> bool:
        v = await self._client.get(K_AUTOMATION_ENABLED)
        return self._to_bool(v)

    async def set_automation_enabled(self, value: bool) -> None:
        await self._client.set(K_AUTOMATION_ENABLED, self._from_bool(value))

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
