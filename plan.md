# BTC/USDT Futures Trading Bot — Advanced Implementation Plan

## Purpose
Build a production-grade asyncio Python 3.11+ **leverage-aware** futures trading system using ccxt.pro for Binance Futures, Redis as persistent state, and dynamic risk management that auto-scales based on user leverage, account balance, and real-time technical analysis.

## Core Architecture Changes (from 1x to Leverage Support)

### **User-Configurable Parameters**
Users can now set:
- **Trading Capital**: How much USDT to allocate to futures (e.g., $1,000 - $10,000)
- **Leverage**: 1x to 20x (Binance Futures max)
- **Max Risk per Trade**: % of account (e.g., 1% - 5%)
- **Max Account Drawdown**: Before all trading stops (e.g., 5% - 20%)

### **Dynamic Risk Management**
Risk engine auto-calculates based on:
- Account balance × Leverage × Selected Risk %
- Stop-loss distance (ATR-based)
- Entry price and liquidation distance
- Margin utilization ratio

### **Liquidation Protection**
- Maintain 10%+ buffer between SL and liquidation price
- Auto-reduce position size if leverage is extreme
- Force-close at 15% margin utilization if SL not working
- Warn user before opening trades near liquidation zone

## High-level Build Order (14 modules + enhanced dashboard)

1. **Bootstrap**: requirements.txt, config.yaml, .env.example, .gitignore
2. **config.py** (UPDATED): User-facing parameters + leverage constants
3. **redis_state.py** (UPDATED): New keys for leverage, capital, liquidation prices
4. **exchange_client.py**: Unchanged (reuse existing)
5. **data_feed.py**: Unchanged (reuse existing)
6. **indicators.py**: Unchanged (reuse existing)
7. **external_feeds.py**: Unchanged (reuse existing)
8. **strategy.py**: Unchanged (reuse existing)
9. **risk.py** (ENHANCED): Leverage-aware position sizing + liquidation checks
10. **executor.py**: Unchanged (reuse existing)
11. **logging_utils.py**: Unchanged (reuse existing)
12. **leverage_calculator.py** (NEW): Core leverage math, liquidation prices, margin ratios
13. **dashboard.py** (MAJOR UPDATE): Setup wizard, live leverage/capital config, liquidation meter
14. **backtest.py**: Unchanged (reuse existing)
15. **main.py**: Unchanged (reuse existing)
16. **tests/**: Updated test suite for leverage scenarios

## Project File Structure (Updated)

```
bot/
├── requirements.txt
├── .env.example
├── config.yaml
├── config.py (UPDATED)
├── redis_state.py (UPDATED)
├── exchange_client.py (REUSE)
├── data_feed.py (REUSE)
├── indicators.py (REUSE)
├── external_feeds.py (REUSE)
├── strategy.py (REUSE)
├── risk.py (UPDATED)
├── executor.py (REUSE)
├── logging_utils.py (REUSE)
├── leverage_calculator.py (NEW)
├── dashboard.py (ENHANCED)
├── backtest.py (REUSE)
├── main.py (REUSE)
├── plan.md (THIS FILE)
└── tests/
    ├── test_leverage_calculator.py (NEW)
    ├── test_risk_leverage.py (NEW)
    └── [other existing tests...]
```

## User Configuration Flow

### **Step 1: Initial Setup (Dashboard)**
User lands on dashboard and sees "SETUP REQUIRED" state:
```
┌─────────────────────────────────────────┐
│  ⚙️ FUTURES BOT SETUP                   │
├─────────────────────────────────────────┤
│                                         │
│  Trading Capital (USDT):  [____1000__]  │
│  Leverage (1x-20x):       [____5____]   │
│  Max Risk per Trade (%):  [____2____]   │
│  Max Daily Drawdown (%):  [____10___]   │
│  Margin Mode:            [Isolated ▼]  │
│                                         │
│  [VALIDATE]  [SAVE]  [BACKTEST]        │
│                                         │
└─────────────────────────────────────────┘
```

### **Step 2: Configuration Validation**
System validates:
- Account has enough USDT: balance >= trading_capital
- Leverage is within Binance limits (1-20x)
- Risk % makes sense with leverage
- No excessive liquidation risk (SL > liquidation by 10%)

### **Step 3: Risk Calculation**
```python
# Example calculation:
trading_capital = $1,000
leverage = 5x
max_risk_per_trade = 2%
account_balance = $10,000

# Position sizing:
risk_amount = $10,000 × 2% = $200
ATR = $50
position_size = $200 / $50 = 4 BTC equivalent

# With leverage:
actual_position = $1,000 × 5 = $5,000 notional
amount = $5,000 / 50020 = 0.0999 BTC

# Liquidation price (short example):
liquidation = entry_price + (trading_capital / amount)
liquidation = 50020 + (1000 / 0.0999) = 60030

# SL must be > liquidation + 10% buffer:
buffer = (50020 - liquidation) × 0.10 = -1001 (need bigger buffer)
SL = liquidation + buffer
```

## Enhanced Redis Schema

### **User Configuration (NEW)**
```
bot:config:trading_capital (float) — allocated USDT for futures
bot:config:leverage (int) — 1 to 20x
bot:config:max_risk_pct (float) — 1-5%
bot:config:max_drawdown_pct (float) — account kill switch level
bot:config:margin_mode (str) — "isolated" or "cross"
bot:config:last_updated (ISO8601 timestamp)
```

### **Leverage State (NEW)**
```
bot:leverage:current (int) — active leverage multiplier
bot:leverage:liquidation_price (float) — current position liquidation level
bot:leverage:margin_utilization_pct (float) — 0-100% (95%+ is danger zone)
bot:leverage:collateral_used_usdt (float) — actual margin locked
bot:leverage:max_position_notional (float) — largest allowed position
```

### **Risk Tracking (NEW)**
```
bot:risk:daily_realized_pnl (float) — closed trades P&L
bot:risk:unrealized_pnl (float) — open position P&L
bot:risk:largest_loss_streak (int) — consecutive losses seen
bot:risk:account_equity_curve (JSON array) — hourly snapshots
```

### **Existing Keys (Keep all)**
All previous redis_state.py keys remain:
- automation_enabled, active_position, account_balance, etc.

## config.py (UPDATED)

```python
"""Configuration loader with leverage support"""

from dataclasses import dataclass
from typing import Literal

# User-facing constants
DEFAULT_LEVERAGE = 5
MAX_LEVERAGE = 20
MIN_LEVERAGE = 1
DEFAULT_TRADING_CAPITAL = 1000  # USDT
DEFAULT_MAX_RISK_PCT = 2.0  # per trade
DEFAULT_MAX_DRAWDOWN_PCT = 10.0  # account kill switch

# Leverage constants
LIQUIDATION_BUFFER_PCT = 10  # Keep 10% SL margin above liquidation
MARGIN_DANGER_ZONE_PCT = 90  # Warn above this
MARGIN_FORCE_CLOSE_PCT = 95  # Auto-close above this

# Binance limits
BINANCE_MAX_LEVERAGE = 20
BINANCE_MIN_LEVERAGE = 1
BINANCE_TAKER_FEE_PCT = 0.04
BINANCE_MAKER_FEE_PCT = 0.02

@dataclass
class LeverageConfig:
    trading_capital: float
    leverage: int
    max_risk_pct: float
    max_drawdown_pct: float
    margin_mode: Literal["isolated", "cross"]

def validate_config(config: LeverageConfig) -> bool:
    """Validate leverage configuration"""
    assert 0 < config.trading_capital <= 100000, "Invalid capital"
    assert MIN_LEVERAGE <= config.leverage <= MAX_LEVERAGE, "Invalid leverage"
    assert 0.5 <= config.max_risk_pct <= 10, "Invalid risk %"
    assert 5 <= config.max_drawdown_pct <= 50, "Invalid drawdown %"
    return True

BINANCE_SYMBOL = "BTC/USDT"
EXEC_CONFIG = {...}  # Keep existing config
```

## leverage_calculator.py (NEW MODULE)

```python
"""Core leverage mathematics for futures trading"""

from typing import NamedTuple
import numpy as np

class LeverageContext(NamedTuple):
    account_balance: float
    trading_capital: float
    leverage: int
    entry_price: float
    atr_stop_distance: float
    max_risk_pct: float

class LiquidationMetrics(NamedTuple):
    liquidation_price: float
    buffer_to_sl: float
    margin_utilization_pct: float
    is_liquidation_safe: bool
    recommended_sl: float

def calculate_liquidation_price(
    side: str,
    entry_price: float,
    collateral: float,
    amount: float
) -> float:
    """
    Calculate liquidation price for futures position.
    
    Long liquidation: entry - (collateral / amount)
    Short liquidation: entry + (collateral / amount)
    """
    if side == "long":
        return entry_price - (collateral / amount)
    else:  # short
        return entry_price + (collateral / amount)

def calculate_position_size(
    account_balance: float,
    trading_capital: float,
    leverage: int,
    atr_stop_distance: float,
    max_risk_pct: float,
    account_balance_usdt: float
) -> dict:
    """
    Calculate position size with leverage consideration
    
    Formula:
    1. Risk amount = account_balance × max_risk_pct
    2. Position notional = (trading_capital × leverage) / entry_price
    3. Verify: (notional / leverage) provides enough margin
    4. Verify: SL distance allows 10% buffer from liquidation
    """
    risk_amount = account_balance * (max_risk_pct / 100)
    max_position_notional = (trading_capital * leverage) / 10  # Rough max
    
    return {
        "position_notional": min(risk_amount * 10, max_position_notional),
        "max_position_notional": max_position_notional,
        "collateral_required": trading_capital,
        "risk_amount": risk_amount
    }

def validate_sl_position(
    entry_price: float,
    sl_price: float,
    collateral: float,
    amount: float,
    side: str,
    leverage: int
) -> LiquidationMetrics:
    """
    Verify stop-loss is safe (10% above liquidation)
    """
    liq = calculate_liquidation_price(side, entry_price, collateral, amount)
    
    if side == "long":
        buffer = sl_price - liq
        is_safe = buffer > abs(liq * 0.10)  # 10% buffer
    else:
        buffer = liq - sl_price
        is_safe = buffer > abs(liq * 0.10)
    
    margin_util = (collateral / (entry_price * amount)) * 100
    
    return LiquidationMetrics(
        liquidation_price=liq,
        buffer_to_sl=buffer,
        margin_utilization_pct=margin_util,
        is_liquidation_safe=is_safe,
        recommended_sl=liq + (buffer * 0.5)  # 5% margin
    )
```

## risk.py (UPDATED)

Key changes to add leverage-aware calculations:

```python
"""Risk management with leverage support"""

def compute_position_size_leverage(
    account_balance: float,
    trading_capital: float,
    leverage: int,
    atr_stop_distance_usd: float,
    max_risk_pct: float
) -> dict:
    """
    Compute position size considering leverage
    
    Returns:
    {
        "amount_btc": float,
        "notional_usd": float,
        "collateral_required": float,
        "margin_utilization": float,
        "is_safe": bool,
        "reason": str
    }
    """
    from leverage_calculator import calculate_position_size, validate_sl_position
    
    # Calculate base position
    risk_amount = account_balance * (max_risk_pct / 100)
    notional = (trading_capital * leverage) / 100  # Simplified
    
    # Cap at trading capital limits
    max_notional = trading_capital * leverage
    position_notional = min(risk_amount * leverage, max_notional * 0.8)  # 80% max
    
    # Check liquidation safety
    if leverage > 1:
        liq_check = validate_sl_position(...)
        if not liq_check.is_liquidation_safe:
            return {"is_safe": False, "reason": "Liquidation too close"}
    
    return {
        "position_notional": position_notional,
        "amount_btc": position_notional / current_price,
        "collateral_required": trading_capital,
        "margin_utilization": (trading_capital / position_notional) * 100,
        "is_safe": True,
        "liquidation_price": liq_check.liquidation_price
    }

def check_circuit_breakers_leverage(
    state_snapshot,
    config,
    leverage: int,
    trading_capital: float
) -> Optional[str]:
    """
    Enhanced circuit breakers for leverage
    
    New CB5: Margin utilization >95% → force close
    New CB6: Liquidation approaching (SL buffer <5%) → warn
    """
    # Existing checks...
    
    # CB5: Margin check
    margin_util = state_snapshot.margin_utilization_pct
    if margin_util > 95:
        return "CB5: Margin utilization critical (>95%)"
    
    # CB6: Liquidation buffer check
    if state_snapshot.liquidation_buffer_pct < 5:
        return "CB6: Liquidation buffer insufficient (<5%)"
    
    return None  # All checks pass
```

## dashboard.py (MAJOR UPDATES)

Add new sections:

### **Setup Wizard (First Launch)**
```python
if not bot_config_exists():
    st.title("⚙️ FUTURES BOT SETUP")
    
    col1, col2 = st.columns(2)
    with col1:
        trading_capital = st.number_input(
            "Trading Capital (USDT)",
            min_value=100,
            max_value=100000,
            value=1000,
            step=100
        )
    with col2:
        leverage = st.slider(
            "Leverage",
            min_value=1,
            max_value=20,
            value=5
        )
    
    col1, col2 = st.columns(2)
    with col1:
        max_risk = st.slider(
            "Max Risk per Trade (%)",
            min_value=0.5,
            max_value=10.0,
            value=2.0
        )
    with col2:
        max_drawdown = st.slider(
            "Max Daily Drawdown (%)",
            min_value=5,
            max_value=50,
            value=10
        )
    
    if st.button("SAVE CONFIGURATION"):
        validate_and_save_config(...)
        st.success("Config saved!")
```

### **Live Leverage Metrics Panel**
```python
st.subheader("📊 Leverage & Margin")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Leverage", f"{leverage}x")
with col2:
    st.metric("Margin Util.", f"{margin_util:.1f}%")
with col3:
    st.metric("Liquidation", f"${liquidation_price:,.2f}")
with col4:
    st.metric("Buffer to SL", f"{buffer_pct:.1f}%")

# Danger zone warning
if margin_util > 90:
    st.warning(f"⚠️  Margin utilization critical: {margin_util:.1f}%")
if buffer_pct < 10:
    st.error(f"🚨 SL too close to liquidation! Buffer: {buffer_pct:.1f}%")
```

### **Liquidation Meter**
```python
# Visual liquidation risk indicator
liq_risk = (current_price - liquidation_price) / current_price * 100
st.progress(min(liq_risk / 10, 1.0), text=f"Distance: {liq_risk:.1f}%")

if liq_risk < 5:
    st.error("EXTREME LIQUIDATION RISK - AUTO-CLOSE TRIGGERED")
elif liq_risk < 10:
    st.warning("DANGER ZONE - Manual intervention recommended")
```

## Test Suite

New test files:
- **test_leverage_calculator.py**: Liquidation math, margin calculations
- **test_risk_leverage.py**: Position sizing with leverage, circuit breakers

Example test:
```python
def test_liquidation_calculation_long():
    """Test long position liquidation"""
    liq = calculate_liquidation_price(
        side="long",
        entry_price=50020,
        collateral=1000,
        amount=0.01
    )
    expected = 50020 - (1000 / 0.01)
    assert abs(liq - expected) < 0.01

def test_sl_safety_check():
    """Test SL is 10% above liquidation"""
    metrics = validate_sl_position(
        entry_price=50020,
        sl_price=49000,
        collateral=1000,
        amount=0.01,
        side="long",
        leverage=5
    )
    assert metrics.is_liquidation_safe == True
    assert metrics.margin_utilization_pct < 100
```

## Implementation Phases

### **Phase 1: Core Leverage Math** (Implement leverage_calculator.py)
- Liquidation price calculation
- Margin utilization tracking
- SL safety validation
- Tests

### **Phase 2: Risk Engine Updates** (Update risk.py)
- Leverage-aware position sizing
- Enhanced circuit breakers (CB5, CB6)
- Integration with leverage_calculator

### **Phase 3: Redis Schema** (Update redis_state.py)
- New leverage config keys
- New leverage state keys
- Getters/setters for all

### **Phase 4: Dashboard Setup** (Update dashboard.py)
- Setup wizard for first-time users
- Live leverage metrics panel
- Liquidation meter
- Configuration persistence

### **Phase 5: Integration & Testing**
- End-to-end tests with leverage
- Backtest with variable leverage
- Dashboard validation

## Key Safety Principles

1. **Liquidation Buffer**: SL must be 10%+ away from liquidation price
2. **Margin Threshold**: Stop all trading at 95% margin utilization
3. **Force Close**: Auto-close positions at 95% margin or SL <5% from liquidation
4. **User Confirmation**: Large leverage (>5x) requires dashboard confirmation
5. **Drawdown Kill Switch**: Existing -10% (adjustable) stops all trading

## Success Criteria

- ✅ User can set trading capital, leverage, and risk % via dashboard
- ✅ System prevents liquidations via SL placement validation
- ✅ Risk scales dynamically with leverage
- ✅ Liquidation prices calculated correctly for shorts/longs
- ✅ Dashboard shows real-time margin utilization and liquidation distance
- ✅ All tests pass (including new leverage tests)
- ✅ Backtest works with variable leverage settings
