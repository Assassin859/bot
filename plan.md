# BTC/USDT Futures Bot — Implementation Plan

## Purpose
Build an asyncio Python 3.11+ trading system using ccxt.pro for Binance Futures, Redis as the single source of truth, and a single strategy/risk engine reused across Backtest, Paper, and Live modes.

## High-level deliverables (strict build order)
1. Bootstrap: requirements.txt, config.yaml, .env.example
2. redis_state.py — only module that accesses Redis directly; Pydantic models; read_full_snapshot(); typed getters/setters
3. exchange_client.py — ccxt.pro wrapper, token-bucket governor (10/10s), precision helpers, Binance time sync
4. data_feed.py and indicators.py — rolling 1000-candle windows (1m, 15m), ensure_fresh(), all indicators and filter helpers
5. external_feeds.py — async feeds with TTLs, startup force-refresh, Redis writes via redis_state.py only
6. strategy.py — 4-layer confluence, strict gate ordering, structured JSON evaluation events
7. risk.py — sizing, bracket planning, circuit breakers, per-candle and startup integrity checks
8. executor.py — execute_entry_plan() supporting Ghost/Paper/Backtest/Live; SL placement guarantee
9. logging_utils.py — structured JSON logging and Redis-backed dual event streams
10. dashboard.py — Streamlit UI (2s refresh), automation toggle, ghost PnL, dual logs, Emergency Close
11. backtest.py — historical replay, validation for Feb 9 and Feb 13 2026, SHA-256 promotion gate
12. main.py — safety-first startup sequence and main strategy loop
13. tests/test_integration.py — Redis schema, behavioral contracts, backtest promotion gate

## Project file structure
```
btc_bot/
├── requirements.txt
├── .env.example
├── config.yaml
├── config.py
├── redis_state.py
├── exchange_client.py
├── data_feed.py
├── indicators.py
├── external_feeds.py
├── strategy.py
├── risk.py
├── executor.py
├── logging_utils.py
├── dashboard.py
├── backtest.py
├── main.py
└── tests/
  ├── test_redis_state.py
  ├── test_exchange_client.py
  ├── test_data_feed.py
  ├── test_indicators.py
  ├── test_external_feeds.py
  ├── test_strategy.py
  ├── test_risk.py
  ├── test_executor.py
  ├── test_logging_utils.py
  ├── test_dashboard.py
  ├── test_backtest.py
  ├── test_main.py
  └── test_integration.py
```

## config.yaml (complete, use exactly this)
```yaml
exchange:
  name: binance
  api_key: YOUR_API_KEY_HERE
  api_secret: YOUR_API_SECRET_HERE
  testnet: true

trading:
  pair: BTC/USDT
  leverage: 5
  margin_mode: isolated

strategy:
  trend_timeframe: 15m
  signal_timeframe: 1m
  ema_slow: 200
  ema_fast: 50
  zscore_period: 20
  zscore_threshold: 1.8
  cvd_lookback: 10
  atr_period: 14
  extended_move_atr_multiplier: 1.5
  extended_move_pivot_bars: 5
  extended_move_lookback_bars: 20
  spread_max_pct: 0.08
  candle_history: 1000
  min_composite_score_short: -2
  min_composite_score_long: 3

risk:
  account_risk_per_trade_pct: 1.0
  max_position_notional_usdt: 400
  sl_atr_multiplier: 1.5
  tp_atr_multiplier: 3.0
  ghost_base_balance: 10000
  max_daily_trades: 10
  max_consecutive_losses: 3
  cooldown_minutes: 45
  daily_drawdown_kill_pct: 2.0
  max_hold_minutes: 90

execution:
  order_chase_timeout_seconds: 8
  max_repost_attempts: 3
  paper_fill_fee_pct: 0.04

external_feeds:
  binance_futures_cache_minutes: 15
  fear_greed_cache_minutes: 60
  onchain_cache_minutes: 240
  onchain_api_key: ""
  funding_rate_threshold: 0.05
  ls_ratio_high: 1.8
  ls_ratio_low: 0.6
  onchain_flow_threshold_btc: 1000
  fear_greed_extreme_fear: 25
  fear_greed_extreme_greed: 75

governor:
  max_calls: 10
  window_seconds: 10

binance_time:
  sync_interval_minutes: 30
```

## .env.example
```
LIVE_TRADING_CONFIRMED=false
ONCHAIN_API_KEY=
```

## requirements.txt
```
ccxt[pro]>=4.0.0
redis>=5.0.0
pandas>=2.0.0
numpy>=1.26.0
pandas-ta>=0.3.14b
streamlit>=1.35.0
pydantic>=2.0.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

## Complete Redis schema — redis_state.py must implement every key listed here

### Core state
- automation_enabled: bool — default False if missing; log WARNING: AUTOMATION_DEFAULTED_OFF
- active_position: JSON — fields: symbol, direction, entry_price, stop_price, target_price, position_size_btc, entry_time_utc, stop_order_id, target_order_id
- account_balance: float
- rolling_24h_pnl: float
- mode: str — values: backtest, paper, live

### Risk and circuit breaker keys
- daily_trade_count: int
- daily_trade_date: str — format YYYY-MM-DD UTC, derived from Binance server time not local OS time
- consecutive_losses: int
- cooldown_until: int — Unix timestamp in UTC milliseconds, 0 if none

### External data cache keys — all JSON with fields: value and timestamp
- funding_rate_cache
- oi_cache
- ls_ratio_cache
- fear_greed_cache
- onchain_flow_cache

### Backtest promotion gate
- backtest_validated: bool
- backtest_validated_config_hash: str — SHA-256 hex digest

### Ghost metrics
- ghost_pnl: float
- ghost_trade_count: int
- ghost_win_rate: float — range 0.0 to 1.0

### redis_state.py rules
- This is the ONLY file that may call redis.get(), redis.set(), redis.delete(), or any Redis command directly
- Every other module calls typed methods from redis_state.py only
- No raw Redis key strings exist anywhere outside redis_state.py
- Expose read_full_snapshot() that reads all keys before any exchange contact on startup

## Key engineering constraints

**Redis isolation:** redis_state.py is the only file that touches Redis directly. Every other file imports and calls typed methods from it. If any other file calls Redis directly that is a bug — flag it immediately.

**Token bucket governor:** applies to every private API call in exchange_client.py without exception: order placement, cancellations, balance queries, position queries, open order status checks. Limit 10 calls per 10 seconds. When throttled, delay and log WARNING with the name of the calling function.

**Precision:** every order size passes through ccxt.amount_to_precision() and every price through ccxt.price_to_precision() before submission. Never send raw Python floats to Binance.

**Binance server time:** on startup and every 30 minutes via asyncio task, fetch Binance server time and compute binance_offset_ms = binance_time_ms - local_time_ms stored in memory. All timestamps (daily_trade_date, entry_time_utc, cooldown_until, max hold checks, log timestamps) use now_binance_ms = local_time_ms + binance_offset_ms. If periodic refresh fails, keep existing offset and log WARNING: BINANCE_TIME_SYNC_FAILED. If startup fetch fails, set offset to 0 and log WARNING: BINANCE_TIME_SYNC_UNAVAILABLE_USING_LOCAL — do not abort startup.

**Freshness guard:** data_feed.ensure_fresh(max_age_seconds=3) is called only in the main strategy loop in main.py before every call to strategy.evaluate_signal(). strategy.py never calls ensure_fresh itself. If stale, log CRITICAL: WEBSOCKET_STALE and skip evaluation.

**Strategy isolation:** `strategy.py` must not import `exchange_client.py`, `external_feeds.py`, or `redis_state.py` directly. It receives all inputs as parameters (`state_snapshot`, `candles_1m`, `candles_15m`, and `external_scores`) and is a pure function of those inputs.

## Strategy gate order — strict, exit immediately on first failure

evaluate_signal(state_snapshot, candles_1m, candles_15m, external_scores) -> SignalDecision

Execute in this exact order, exit immediately at each failure without evaluating anything further:

1. One-Position Rule: if active_position exists in state snapshot, return no-action immediately
2. Trend gate: compute 15m EMA50 and EMA200. If price below both and EMA50 < EMA200, trend_score = -1. If price above both and EMA50 > EMA200, trend_score = +1. Otherwise return SIGNAL_REJECTED: trend_neutral immediately
3. Reversion gate: 1m Z-Score over 20 periods. Short needs Z > +1.8 AND 3 consecutive closes each below previous. Long needs Z < -1.8 AND 3 consecutive closes each above previous. Otherwise reversion_score = 0
4. Volume gate: 1m CVD over 10-candle lookback. Bearish divergence (price net higher last 5, CVD net lower) = -1. Bullish divergence (price net lower last 5, CVD net higher) = +1. Otherwise 0
5. Asymmetry Hard Gate (enforced before any external layer): Short needs trend_score == -1 AND (reversion_score == -1 OR volume_score == -1). Long needs all three scores == +1. If fails, return SIGNAL_REJECTED: asymmetry_gate_failed with trend_score, reversion_score, volume_score in log — do not evaluate Layers 2-4
6. Extended Move Filter: 1m ATR(14). Find most recent 5-candle pivot (high strictly greater than 2 before and 2 after) within last 20 bars. Short: if price fell more than 1.5x ATR below pivot high, return SIGNAL_REJECTED: extended_move with ATR, pivot price, current price. Long: symmetric using swing low. If no pivot found within 20 bars, skip filter
7. Spread Guard: if bid-ask spread > 0.08% of mid-price, return SIGNAL_SUPPRESSED: spread_guard with spread value
8. Load external scores from Redis caches (Layers 2, 3, 4)
9. Compute composite score. Short approved if composite <= -2. Long approved if composite >= +3
10. Log structured JSON for every evaluation: timestamp, side, trend_score, reversion_score, volume_score, layer2 scores, layer3 score, layer4 score, composite, decision, reason

## External layer scores

Layer 2 from Binance Futures REST cached every 15 minutes:
- Funding rate > +0.05% scores -1, < -0.05% scores +1, otherwise 0
- OI delta: price rising with OI rising scores +1 for longs, price falling with OI rising scores -1 for shorts, otherwise 0
- Long/Short ratio > 1.8 scores -1, < 0.6 scores +1, otherwise 0

Layer 3 from alternative.me cached every hour:
- Fear and Greed 0-24 scores +1, 76-100 scores -1, 25-75 scores 0

Layer 4 from CryptoQuant or Glassnode cached every 4 hours:
- Net inflow > +1000 BTC scores -1, net outflow < -1000 BTC scores +1, otherwise 0
- If no API key in config.yaml, always return 0 and log INFO: ONCHAIN_LAYER_DISABLED on startup

## Risk management rules

Position sizing: risk 1% of base balance per trade divided by ATR stop distance in dollars, result through ccxt.amount_to_precision(), hard cap at $400 notional. Base balance is account_balance from Redis for live and paper. For ghost mode, ghost_base_balance is read once from account_balance on startup and never updated.

Bracket orders: SL at 1.5x ATR from entry, TP at 3x ATR from entry, submitted simultaneously with entry.

Circuit breakers (all use Binance server time):
- Daily limit: compare daily_trade_date to current Binance UTC date on every trade attempt. If date changed, reset daily_trade_count to 0 and update daily_trade_date first. Block if count >= 10 and log SIGNAL_REJECTED: daily_limit_reached
- Cooldown: after 3 consecutive losses set cooldown_until to Binance now + 45 minutes. Reset consecutive_losses to 0 on any winning close. Log SIGNAL_REJECTED: cooldown_active when blocking
- Kill switch: if rolling_24h_pnl < -0.02 * account_balance, cancel all orders, market-close all positions, set automation_enabled to False, halt, log CRITICAL: CIRCUIT_BREAKER_TRIGGERED
- Max hold: if position open longer than 90 minutes by Binance time, market-close and log POSITION_CLOSED: max_hold_time

Per-candle integrity: every 1m close while position is open, verify stop_order_id and target_order_id still exist on exchange. If missing, re-place immediately. If re-placement fails, market-close and log CRITICAL: STOP_ORDER_MISSING.

Startup integrity: on startup, if active_position exists in Redis, query the exchange for stop_order_id and target_order_id before starting the strategy loop. If either is missing on the exchange, market-close immediately and log CRITICAL: UNPROTECTED_POSITION_ON_STARTUP.

## Executor rules

Ghost mode (automation_enabled == False in any operational mode):
- Never place real or paper orders
- Simulate fill at mid-price plus 0.04% fee using ghost-sized quantity
- Update ghost_pnl, ghost_trade_count, ghost_win_rate in Redis after each ghost trade close

Live mode SL guarantee: if entry order fills but SL placement fails, immediately market-close the position and log CRITICAL: SL_PLACEMENT_FAILED. Never allow an unprotected position under any circumstances.

## Startup sequence in main.py — exact order, no changes

1. Call redis_state.read_full_snapshot() — reconstruct all state before any exchange contact
2. If active_position exists, query exchange for stop_order_id and target_order_id. If either missing, market-close and log CRITICAL: UNPROTECTED_POSITION_ON_STARTUP before proceeding
3. Force-refresh all external feeds regardless of TTL, overwrite Redis caches
4. Fetch 1000 historical candles for 1m and 15m, initialise DataFrames
5. Fetch Binance server time, compute and store binance_offset_ms
6. Start WebSocket connections and main strategy loop

## Main loop responsibilities

On every 1m candle close:
- Compare automation_enabled to previous tick value (in-memory). If changed False to True, reset ghost metrics in Redis before proceeding
- Call data_feed.ensure_fresh(3). If stale, log CRITICAL: WEBSOCKET_STALE and skip
- Check evaluation_suspended_due_to_position flag. Log EVALUATION_SUSPENDED: active_position_open once when position opens (flag False to True). Log EVALUATION_RESUMED once when position closes (flag True to False). Never log per-candle while position held. Initialise flag to True on startup if active_position exists in Redis
- If not suspended and fresh, call strategy.evaluate_signal() with current state snapshot
- If approved, pass to risk.py for sizing and circuit breaker checks, then to executor.py

## Backtest validation gate

Run against February 9 2026 and February 13 2026. Manual history shows 54 trades on Feb 9 and 25 trades on Feb 13. Bot must produce 8 or fewer trades on each day.

If any day exceeds 8 trades: log Extended Move Filter failure, do not write any validation flag, exit with sys.exit(1).

If both days pass and profit factor exceeds 1.3: compute hash as hashlib.sha256((open('strategy.py','rb').read() + open('risk.py','rb').read())).hexdigest(). Write backtest_validated = True and backtest_validated_config_hash = hash to Redis. Exit successfully.

On Mode B and C startup in main.py: recompute same hash from current files. If backtest_validated is not True or hashes do not match, set backtest_validated = False in Redis, log CRITICAL: STRATEGY_MODIFIED_SINCE_VALIDATION with stored hash and current hash, refuse to start.

## One-Position Rule logging detail

Maintain in-memory boolean evaluation_suspended_due_to_position in main loop. On startup, initialise to True if active_position exists in Redis (prevents false EVALUATION_RESUMED on first tick). Log transition events once only, never per-candle.

## Ghost mode automation transition

In main loop, store previous_automation_enabled as in-memory variable. On every tick, read current automation_enabled from Redis. If previous was False and current is True, reset ghost_pnl to 0.0, ghost_trade_count to 0, ghost_win_rate to 0.0 in Redis via redis_state setters before evaluating anything. Update previous_automation_enabled after the check.

## Dashboard panels

Auto-refresh every 2 seconds. Top row: automation toggle (large red OFF / green ON writing to Redis on click), mode, trade count vs limit, open position with unrealised PnL or None, 24h rolling PnL.

Market Context Panel reads from Redis caches only (never live API calls on refresh): funding rate value and score and timestamp, OI delta direction and score, long/short ratio and score, Fear and Greed value and label and score, on-chain flow and score or disabled label.

Ghost PnL panel visible when automation OFF: ghost_pnl, ghost_trade_count, ghost_win_rate. Label clearly as theoretical.

Emergency Close All button in orange. Requires confirmation click. Cancels all orders, market-closes all positions, sets automation_enabled to False.

Dual logs: left panel shows last 50 execution JSON events from Redis stream. Right panel shows last 50 rejection and suppression events with full score breakdowns.

## Acceptance checks — every item must pass before moving to next file

- redis_state.read_full_snapshot() populates every key in the schema. Missing automation_enabled defaults to False and logs WARNING: AUTOMATION_DEFAULTED_OFF
- No file other than redis_state.py contains any Redis call. Grep for redis.get and redis.set in all other files — result must be empty
- exchange_client token bucket logs WARNING with caller function name on every throttle
- data_feed.ensure_fresh() is never called inside strategy.py — grep confirms this
- Mode B and C startup recomputes SHA-256 of strategy.py + risk.py and refuses start on mismatch
- SL failure in live executor triggers immediate market-close before any other action
- EVALUATION_SUSPENDED and EVALUATION_RESUMED log exactly once per position lifecycle, never per-candle
- Automation False to True transition resets all three ghost metrics in Redis in the main loop
- All timestamps in logs and Redis use Binance server time via binance_offset_ms
- backtest.py exits with sys.exit(1) if either validation day exceeds 8 trades

- Per-candle integrity check in `risk.py` queries exchange open orders on every 1m close while a position is open, attempts re-placement if SL or TP is missing, and market-closes with `CRITICAL: STOP_ORDER_MISSING` if re-placement fails
- On startup, if `active_position` exists in Redis, exchange is queried for both order IDs before the strategy loop starts, and `CRITICAL: UNPROTECTED_POSITION_ON_STARTUP` triggers immediate market-close if either is missing

## Verification commands
```bash
pip install -r requirements.txt
pytest tests/
python backtest.py --validate
python main.py --mode paper
streamlit run dashboard.py
```

## How we will work

I will say "build file N" and you build only that file. After generating it, you will review it against the requirements above, list every missing or incorrect item, fix them, then stop and wait for me to say "next". Do not start the next file until I confirm. Do not tell me the code looks good if any acceptance check for that file would fail.

Start now by creating the empty project structure, then wait for me to say "build file 1".