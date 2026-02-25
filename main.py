"""Main startup sequence and strategy loop.

Implements 6-step startup:
1. Redis snapshot read and SL/TP integrity check
2. Force external feeds refresh
3. Fetch 1000 historical candles
4. Binance time sync (startup + periodic 30min refresh)
5. WebSocket startup
6. Main loop with freshness guard and automation toggle handling
"""
from __future__ import annotations
import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

from config import BINANCE_SYMBOL, EXEC_CONFIG
from redis_state import RedisState
from exchange_client import ExchangeClient
from data_feed import DataFeed
from external_feeds import fetch_all_external_data
from strategy import evaluate_signal
from risk import check_circuit_breakers, compute_position_size, check_startup_integrity, check_candle_integrity
from executor import execute_entry_plan
from logging_utils import log_event, log_signal_received, log_circuit_breaker_trip, log_execution, log_position_closed


class BotState:
    """Track bot runtime state."""
    
    def __init__(self):
        self.redis: Optional[RedisState] = None
        self.exchange: Optional[ExchangeClient] = None
        self.data_feed: Optional[DataFeed] = None
        self.binance_offset_ms: int = 0
        self.last_external_refresh: Optional[datetime] = None
        self.last_binance_sync: Optional[datetime] = None
        self.prev_automation_enabled: bool = False
        self.ws_connected: bool = False
    
    async def close(self):
        """Cleanup resources."""
        if self.redis:
            self.redis.close()
        if self.exchange:
            self.exchange.close()


async def step_1_redis_snapshot(bot_state: BotState, mode: str) -> bool:
    """Step 1: Read Redis snapshot and verify SL/TP integrity.
    
    If active_position exists without SL/TP, execute market close.
    Returns True if OK, False if critical error.
    """
    log_event("INFO", {"msg": "Step 1: Reading Redis snapshot and checking integrity"})
    
    bot_state.redis = RedisState()
    try:
        snapshot = await bot_state.redis.get_snapshot()
        
        if snapshot is None:
            log_event("WARNING", {"msg": "Redis snapshot not found, initializing"})
            # Initialize new snapshot
            await bot_state.redis.set_automation_enabled(False)
            return True
        
        # Check startup integrity (SL/TP presence)
        integrity_error = check_startup_integrity(snapshot)
        if integrity_error:
            log_event("ERROR", {
                "msg": "Startup integrity check failed",
                "reason": integrity_error
            })
            
            if mode != "backtest":
                # Market close active position
                log_event("WARNING", {"msg": "Executing emergency market close"})
                if snapshot.active_position:
                    await bot_state.redis.set_emergency_close_flag(True)
            
            return False
        
        log_event("INFO", {"msg": "Redis snapshot OK, integrity passed"})
        return True
    
    except Exception as e:
        log_event("ERROR", {"msg": "Redis error", "error": str(e)})
        return False


async def step_2_external_feeds_refresh(bot_state: BotState) -> bool:
    """Step 2: Force-refresh external feeds (Fear & Greed, funding rate, etc).
    
    Returns True if successful, False on critical error.
    """
    log_event("INFO", {"msg": "Step 2: Refreshing external feeds"})
    
    try:
        external_scores, external_meta = await fetch_all_external_data()
        bot_state.last_external_refresh = datetime.now()
        log_event("INFO", {
            "msg": "External feeds refreshed",
            "feeds": list(external_scores.keys())
        })
        return True
    except Exception as e:
        log_event("WARNING", {"msg": "External feeds refresh failed", "error": str(e)})
        return False


async def step_3_fetch_historical_candles(bot_state: BotState, config: dict) -> bool:
    """Step 3: Fetch 1000 historical candles (1m and 15m).
    
    Initializes DataFeed rolling windows.
    Returns True if OK, False on error.
    """
    log_event("INFO", {"msg": "Step 3: Fetching 1000 historical candles"})
    
    bot_state.exchange = ExchangeClient(config)
    bot_state.data_feed = DataFeed(BINANCE_SYMBOL)
    
    try:
        # Fetch 1000 candles at 1m
        candles_1m = await bot_state.exchange.fetch_ohlcv(
            BINANCE_SYMBOL, "1m",
            start_date=int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
        )
        
        # Fetch last 67 candles at 15m (≈ 1000 minutes)
        candles_15m = await bot_state.exchange.fetch_ohlcv(
            BINANCE_SYMBOL, "15m",
            start_date=int((datetime.now() - timedelta(days=10)).timestamp() * 1000)
        )
        
        # Load into DataFeed
        for candle in candles_1m:
            await bot_state.data_feed.insert_candle_1m(candle)
        
        for candle in candles_15m:
            await bot_state.data_feed.insert_candle_15m(candle)
        
        log_event("INFO", {
            "msg": "Historical candles loaded",
            "candles_1m": len(candles_1m),
            "candles_15m": len(candles_15m)
        })
        return True
    
    except Exception as e:
        log_event("ERROR", {"msg": "Failed to fetch historical candles", "error": str(e)})
        return False


async def step_4_binance_sync(bot_state: BotState) -> bool:
    """Step 4: Fetch Binance server time and compute offset.
    
    Binance_offset_ms = (binance_server_time_ms - local_time_ms)
    This is called again every 30 minutes in the loop.
    """
    log_event("INFO", {"msg": "Step 4: Syncing Binance server time"})
    
    try:
        server_time_ms = await bot_state.exchange.get_server_time_ms()
        local_time_ms = int(datetime.now().timestamp() * 1000)
        bot_state.binance_offset_ms = server_time_ms - local_time_ms
        bot_state.last_binance_sync = datetime.now()
        
        log_event("INFO", {
            "msg": "Binance time synced",
            "offset_ms": bot_state.binance_offset_ms
        })
        return True
    
    except Exception as e:
        log_event("ERROR", {"msg": "Binance time sync failed", "error": str(e)})
        return False


async def step_5_websocket_startup(bot_state: BotState) -> bool:
    """Step 5: Start WebSocket for live price updates.
    
    Placeholder for WS initialization.
    """
    log_event("INFO", {"msg": "Step 5: Starting WebSocket"})
    
    try:
        # TODO: Implement WebSocket connection to Binance
        bot_state.ws_connected = True
        log_event("INFO", {"msg": "WebSocket started"})
        return True
    
    except Exception as e:
        log_event("ERROR", {"msg": "WebSocket startup failed", "error": str(e)})
        return False


async def main_loop(bot_state: BotState, mode: str) -> None:
    """Main strategy loop.
    
    - Checks freshness on each candle (data_feed.ensure_fresh)
    - Calls strategy.evaluate_signal only if fresh
    - Handles automation toggle transition (False→True resets ghost metrics)
    - Executes approved signals through risk/executor
    - Syncs Binance time every 30 minutes
    """
    log_event("INFO", {"msg": "Entering main loop", "mode": mode})
    
    loop_count = 0
    
    while True:
        try:
            loop_count += 1
            current_time = datetime.now()
            
            # 30-minute periodic Binance sync
            if (bot_state.last_binance_sync is None or
                (current_time - bot_state.last_binance_sync).total_seconds() > 1800):
                await step_4_binance_sync(bot_state)
            
            # 6-hour periodic external feeds refresh
            if (bot_state.last_external_refresh is None or
                (current_time - bot_state.last_external_refresh).total_seconds() > 21600):
                await step_2_external_feeds_refresh(bot_state)
            
            # Read current snapshot
            snapshot = await bot_state.redis.get_snapshot()
            
            # Check automation toggle transition: False → True
            if snapshot and snapshot.automation_enabled and not bot_state.prev_automation_enabled:
                log_event("INFO", {"msg": "Automation toggled ON, resetting ghost metrics"})
                await bot_state.redis.reset_ghost_metrics()
                bot_state.prev_automation_enabled = True
            elif snapshot and not snapshot.automation_enabled:
                bot_state.prev_automation_enabled = False
            
            # Freshness check (ONLY HERE, never in strategy.py)
            try:
                await bot_state.data_feed.ensure_fresh(max_age_seconds=65)
            except Exception as e:
                log_event("WARNING", {
                    "msg": "Data not fresh, skipping signal evaluation",
                    "error": str(e)
                })
                await asyncio.sleep(1)
                continue
            
            # Get candles from data_feed
            candles_1m_df = bot_state.data_feed.get_candles_1m_df()
            candles_15m_df = bot_state.data_feed.get_candles_15m_df()
            
            if candles_1m_df.empty or candles_15m_df.empty:
                log_event("WARNING", {"msg": "Insufficient candle data"})
                await asyncio.sleep(1)
                continue
            
            # Convert to list format for strategy
            candles_1m = candles_1m_df.values.tolist()
            candles_15m = candles_15m_df.values.tolist()
            
            # Fetch external data
            external_scores, _ = await fetch_all_external_data()
            
            # Evaluate signal (pure function, no side effects)
            signal = evaluate_signal(
                state_snapshot=snapshot,
                candles_1m=candles_1m,
                candles_15m=candles_15m,
                external_scores=external_scores
            )
            
            # Log signal
            if signal.get("decision") == "entry":
                log_signal_received(signal.get("side", "long"), signal.get("composite_score", 0))
            
            # Automation check
            if not snapshot or not snapshot.automation_enabled:
                log_event("INFO", {
                    "msg": "Automation disabled, skipping execution",
                    "decision": signal.get("decision")
                })
                await asyncio.sleep(1)
                continue
            
            # Risk checks
            cb_error = check_circuit_breakers(snapshot, EXEC_CONFIG)
            if cb_error:
                log_circuit_breaker_trip("AUTO", cb_error)
                await asyncio.sleep(1)
                continue
            
            # Per-candle integrity check
            integrity_error = check_candle_integrity(snapshot)
            if integrity_error:
                log_event("ERROR", {
                    "msg": "Per-candle integrity failed",
                    "error": integrity_error
                })
                await asyncio.sleep(1)
                continue
            
            # Execute if signal
            if signal.get("decision") == "entry":
                atr_stop = signal.get("atr_stop_usd", 50.0)
                position_size = compute_position_size(
                    account_balance=snapshot.account_balance_usd,
                    atr_stop_distance_usd=atr_stop,
                    config=EXEC_CONFIG
                )
                
                entry_plan = {
                    "side": signal.get("side", "long"),
                    "amount": position_size,
                    "entry_price": candles_1m[-1][4],  # Close price
                    "sl_price": signal.get("sl_price", candles_1m[-1][4] * 0.97),
                    "tp_price": signal.get("tp_price", candles_1m[-1][4] * 1.03),
                }
                
                result = await execute_entry_plan(entry_plan, mode, snapshot)
                
                if result and result.get("success"):
                    log_execution(
                        mode=mode,
                        side=signal.get("side", "long"),
                        filled_price=result.get("filled_price"),
                        position_size=position_size
                    )
            
            # Sleep before next iteration
            await asyncio.sleep(1)
        
        except KeyboardInterrupt:
            log_event("INFO", {"msg": "Keyboard interrupt, shutting down"})
            break
        except Exception as e:
            log_event("ERROR", {"msg": "Main loop error", "error": str(e)})
            await asyncio.sleep(5)


async def main(mode: str = "paper") -> None:
    """Main entry point with 6-step startup and loop."""
    log_event("INFO", {"msg": "Bot starting", "mode": mode})
    
    bot_state = BotState()
    
    try:
        # Load configuration (includes API keys from .env if present)
        from config import load_config
        cfg = load_config()
        config_dict = cfg.dict()
        
        # Step 1: Redis snapshot
        if not await step_1_redis_snapshot(bot_state, mode):
            log_event("ERROR", {"msg": "Step 1 failed, aborting"})
            sys.exit(1)
        
        # Step 2: External feeds
        if not await step_2_external_feeds_refresh(bot_state):
            log_event("WARNING", {"msg": "Step 2 warning, continuing"})
        
        # Step 3: Historical candles
        if not await step_3_fetch_historical_candles(bot_state, config_dict):
            log_event("ERROR", {"msg": "Step 3 failed, aborting"})
            sys.exit(1)
        else:
            # Sync account balance and leverage from exchange into Redis
            try:
                if bot_state.exchange and bot_state.redis:
                    await bot_state.exchange.sync_account_to_redis(bot_state.redis, BINANCE_SYMBOL)
            except Exception as e:
                log_event("WARNING", {"msg": "Account sync warning", "error": str(e)})
        
        # Step 4: Binance sync
        if not await step_4_binance_sync(bot_state):
            log_event("WARNING", {"msg": "Step 4 warning, continuing"})
        
        # Step 5: WebSocket
        if not await step_5_websocket_startup(bot_state):
            log_event("WARNING", {"msg": "Step 5 warning, continuing"})
        
        log_event("INFO", {"msg": "Startup complete, entering main loop"})
        
        # Step 6: Main loop
        await main_loop(bot_state, mode)
    
    except Exception as e:
        log_event("ERROR", {"msg": "Critical error", "error": str(e)})
        sys.exit(1)
    
    finally:
        log_event("INFO", {"msg": "Shutting down"})
        await bot_state.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BTC/USDT Futures Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["backtest", "paper", "ghost", "live"],
        default="paper",
        help="Execution mode"
    )
    args = parser.parse_args()
    
    asyncio.run(main(mode=args.mode))
