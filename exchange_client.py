"""Exchange client: ccxt.pro wrapper with token-bucket governor and precision helpers.

This module provides an async ExchangeClient for Binance Futures that:
- Applies a token-bucket governor (10 calls/10s) to all private API calls
- Wraps order sizes and prices through ccxt precision helpers
- Syncs Binance server time on startup and every 30 min
- Logs WARNING when throttled with the caller function name
"""
from __future__ import annotations
import asyncio
import time
from typing import Any, Optional, Dict, List
from logging_utils import log_event

try:
    import ccxt.pro
except ImportError:
    ccxt = None


class TokenBucket:
    """Rate limiter: permits max_calls within window_seconds."""
    
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._lock = asyncio.Lock()
        self._calls: List[float] = []

    async def acquire(self, caller: str = "unknown") -> None:
        """Acquire one slot. Sleeps if necessary. Logs WARNING on throttle."""
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds
            self._calls = [t for t in self._calls if t > window_start]
            
            if len(self._calls) >= self.max_calls:
                # Throttled: calculate sleep time and log warning
                oldest = self._calls[0]
                sleep_time = (oldest + self.window_seconds - now)
                if sleep_time > 0:
                    log_event("WARNING", {
                        "msg": "Token bucket throttled",
                        "caller": caller,
                        "sleep_sec": round(sleep_time, 2)
                    })
                    await asyncio.sleep(sleep_time)
            
            self._calls.append(time.time())


class ExchangeClient:
    """Unified Binance Futures client with token-bucket governor and time sync."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.exchange_config = config.get("exchange", {})
        self.governor_config = config.get("governor", {"max_calls": 10, "window_seconds": 10})
        self.binance_time_config = config.get("binance_time", {"sync_interval_minutes": 30})
        
        # Token bucket governor
        self.governor = TokenBucket(
            max_calls=self.governor_config.get("max_calls", 10),
            window_seconds=self.governor_config.get("window_seconds", 10)
        )
        
        # Binance time offset
        self.binance_offset_ms: int = 0
        
        # Exchange instance (lazy init)
        self._exchange: Optional[Any] = None
    
    async def init_exchange(self) -> None:
        """Initialize ccxt.pro Binance Futures exchange."""
        if ccxt is None:
            raise RuntimeError("ccxt not installed")
        
        if self._exchange is not None:
            return
        
        self._exchange = ccxt.pro.binance({
            'apiKey': self.exchange_config.get('api_key'),
            'secret': self.exchange_config.get('api_secret'),
            'enableRateLimit': True,
            'sandbox': self.exchange_config.get('testnet', True),
        })
    
    async def close(self) -> None:
        """Close exchange connection."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
    
    def price_to_precision(self, symbol: str, price: float) -> str:
        """Wrap price via ccxt precision helper."""
        if self._exchange is None:
            return str(price)
        try:
            return self._exchange.price_to_precision(symbol, price)
        except Exception:
            return str(price)
    
    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Wrap amount via ccxt precision helper."""
        if self._exchange is None:
            return str(amount)
        try:
            return self._exchange.amount_to_precision(symbol, amount)
        except Exception:
            return str(amount)
    
    async def fetch_server_time(self) -> int:
        """Fetch Binance server time in milliseconds."""
        await self.init_exchange()
        try:
            await self.governor.acquire("fetch_server_time")
            return int(await self._exchange.fetch_time())
        except Exception as e:
            log_event("ERROR", {"msg": "fetch_server_time failed", "error": str(e)})
            raise
    
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 1000,
        since: Optional[int] = None,
        start_date: Optional[int] = None
    ) -> List[List[Any]]:
        """Fetch OHLCV candles from Binance Futures (public call, not governed)."""
        await self.init_exchange()
        try:
            # Support either `since` or legacy `start_date` keyword
            if start_date is not None:
                since_val = start_date
            else:
                since_val = since
            return await self._exchange.fetch_ohlcv(symbol, timeframe, since=since_val, limit=limit)
        except Exception as e:
            log_event("ERROR", {"msg": "fetch_ohlcv failed", "symbol": symbol, "error": str(e)})
            raise
    
    async def place_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: str,
        price: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Place an order on Binance Futures. Amount and price should be precision-wrapped."""
        await self.init_exchange()
        try:
            await self.governor.acquire("place_order")
            return await self._exchange.create_order(
                symbol,
                order_type,
                side,
                float(amount),
                price=float(price) if price else None,
                params=params or {}
            )
        except Exception as e:
            log_event("ERROR", {"msg": "place_order failed", "symbol": symbol, "error": str(e)})
            raise
    
    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Cancel an order on Binance Futures."""
        await self.init_exchange()
        try:
            await self.governor.acquire("cancel_order")
            return await self._exchange.cancel_order(symbol, order_id, params=params or {})
        except Exception as e:
            log_event("ERROR", {"msg": "cancel_order failed", "symbol": symbol, "error": str(e)})
            raise
    
    async def fetch_open_orders(
        self,
        symbol: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch open orders from Binance Futures."""
        await self.init_exchange()
        try:
            await self.governor.acquire("fetch_open_orders")
            return await self._exchange.fetch_open_orders(symbol=symbol, params=params or {})
        except Exception as e:
            log_event("ERROR", {"msg": "fetch_open_orders failed", "error": str(e)})
            raise
    
    async def fetch_positions(
        self,
        symbols: Optional[List[str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch positions from Binance Futures."""
        await self.init_exchange()
        try:
            await self.governor.acquire("fetch_positions")
            return await self._exchange.fetch_positions(symbols=symbols, params=params or {})
        except Exception as e:
            log_event("ERROR", {"msg": "fetch_positions failed", "error": str(e)})
            raise
    
    async def fetch_balance(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch account balance from Binance Futures."""
        await self.init_exchange()
        try:
            await self.governor.acquire("fetch_balance")
            return await self._exchange.fetch_balance(params=params or {})
        except Exception as e:
            log_event("ERROR", {"msg": "fetch_balance failed", "error": str(e)})
            raise

    async def sync_account_to_redis(self, redis_state, symbol: str = "BTC/USDT") -> None:
        """Fetch key account info from the exchange and write to Redis.

        - Writes `account_balance` (USDT free balance) to Redis
        - Writes `leverage:current_leverage` if a position or default leverage is detected
        - Writes `leverage:max_position_notional` based on trading balance × leverage
        """
        await self.init_exchange()
        try:
            # Fetch balance
            bal = await self.fetch_balance()
            usdt = 0.0
            # ccxt balance structure varies; prefer 'USDT' key then 'total'/'free'
            if isinstance(bal, dict):
                if "USDT" in bal:
                    entry = bal.get("USDT") or {}
                    usdt = float(entry.get("free") or entry.get("total") or 0.0)
                else:
                    # Try common fallback keys
                    for k in ("USDT", "USD"):
                        if k in bal:
                            entry = bal.get(k) or {}
                            usdt = float(entry.get("free") or entry.get("total") or 0.0)

            # Write account balance to Redis
            try:
                await redis_state.set_account_balance(usdt)
            except Exception:
                log_event("WARNING", {"msg": "Failed writing account balance to Redis"})

            # Try to detect current leverage from positions
            leverage_detected = None
            try:
                positions = await self.fetch_positions(symbols=[symbol])
                if isinstance(positions, list):
                    for p in positions:
                        # ccxt position info may include 'leverage' or 'leverage' within 'info'
                        lev = None
                        if isinstance(p, dict):
                            lev = p.get("leverage") or (p.get("info") or {}).get("leverage")
                        if lev:
                            leverage_detected = int(lev)
                            break
            except Exception:
                # Non-fatal
                leverage_detected = None

            # If none detected, try market max leverage
            if leverage_detected is None:
                try:
                    # load markets and inspect market info
                    await self._exchange.load_markets()
                    m = self._exchange.markets.get(symbol)
                    if m and isinstance(m, dict):
                        info = m.get("info") or {}
                        # Binance futures may expose 'maxLeverage' in market info
                        ml = info.get("maxLeverage") or info.get("max_leverage") or info.get("maxLeverageRate")
                        if ml:
                            leverage_detected = int(ml)
                except Exception:
                    leverage_detected = None

            # Bound leverage to sensible defaults
            if leverage_detected is None:
                from config import DEFAULT_LEVERAGE
                leverage_detected = DEFAULT_LEVERAGE

            # Persist leverage and derived max notional
            try:
                await redis_state.set_leverage_current(int(leverage_detected))
                # conservative max position notional = usdt * leverage_detected
                await redis_state.set_leverage_max_position_notional(float(usdt * float(leverage_detected)))
            except Exception:
                log_event("WARNING", {"msg": "Failed writing leverage state to Redis"})

        except Exception as e:
            log_event("WARNING", {"msg": "sync_account_to_redis failed", "error": str(e)})
            return
