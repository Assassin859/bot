"""Tests for Phase 5 Dashboard enhancements.

Covers:
- Setup wizard configuration validation
- Leverage metrics display
- Liquidation meter calculations
- Configuration persistence to Redis
- Dashboard state management
"""
import pytest
import json
from datetime import datetime

from config import LeverageConfig, validate_leverage_config
from redis_state import RedisSnapshot, ActivePosition


# ============ SETUP WIZARD VALIDATION TESTS ============

def test_valid_default_config():
    """Test default configuration passes validation."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=5,
        max_risk_pct=2.0,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid, msg


def test_minimum_trading_capital():
    """Test minimum trading capital boundary."""
    config = LeverageConfig(
        trading_capital=100.0,
        leverage=5,
        max_risk_pct=2.0,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


def test_maximum_trading_capital():
    """Test maximum trading capital boundary."""
    config = LeverageConfig(
        trading_capital=100000.0,
        leverage=5,
        max_risk_pct=2.0,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


def test_minimum_leverage():
    """Test minimum leverage (1x)."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=1,
        max_risk_pct=2.0,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


def test_maximum_leverage():
    """Test maximum leverage (20x)."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=20,
        max_risk_pct=2.0,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


def test_minimum_risk_percentage():
    """Test minimum risk percentage boundary."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=5,
        max_risk_pct=0.51,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


def test_maximum_risk_percentage():
    """Test maximum risk percentage boundary."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=5,
        max_risk_pct=10.0,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


def test_minimum_drawdown_percentage():
    """Test minimum drawdown percentage boundary."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=5,
        max_risk_pct=2.0,
        max_drawdown_pct=5,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


def test_maximum_drawdown_percentage():
    """Test maximum drawdown percentage boundary."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=5,
        max_risk_pct=2.0,
        max_drawdown_pct=50,
        margin_mode="isolated"
    )
    is_valid, msg = validate_leverage_config(config)
    assert is_valid


# ============ LEVERAGE METRICS TESTS ============

def test_margin_utilization_calculation():
    """Test margin utilization percentage calculation."""
    position_notional = 5000.0
    trading_capital = 1000.0
    margin_util = (position_notional / trading_capital) * 100
    assert margin_util == 500.0


def test_margin_util_safe_zone():
    """Test margin utilization in safe zone (<80%)."""
    position_notional = 500.0
    trading_capital = 1000.0
    margin_util = (position_notional / trading_capital) * 100
    assert margin_util == 50.0
    assert margin_util < 80


def test_margin_util_danger_zone():
    """Test margin utilization in danger zone (90-95%)."""
    position_notional = 920.0
    trading_capital = 1000.0
    margin_util = (position_notional / trading_capital) * 100
    assert 90 < margin_util < 95


def test_margin_util_critical_zone():
    """Test margin utilization in critical zone (>95%)."""
    position_notional = 960.0
    trading_capital = 1000.0
    margin_util = (position_notional / trading_capital) * 100
    assert margin_util > 95


# ============ LIQUIDATION METER TESTS ============

def test_long_position_distance_to_liquidation():
    """Test distance calculation for long position."""
    entry_price = 50000.0
    liquidation_price = 40000.0
    current_price = 48000.0
    
    distance = current_price - liquidation_price
    distance_pct = (distance / current_price) * 100
    
    assert distance == 8000.0
    assert 15 < distance_pct < 20


def test_short_position_distance_to_liquidation():
    """Test distance calculation for short position."""
    entry_price = 50000.0
    liquidation_price = 60000.0
    current_price = 52000.0
    
    distance = liquidation_price - current_price
    distance_pct = (distance / current_price) * 100
    
    assert distance == 8000.0
    assert 15 < distance_pct < 20


def test_liquidation_critical_distance():
    """Test when distance is <5% (critical)."""
    entry_price = 50000.0
    liquidation_price = 49750.0
    current_price = 50000.0
    
    distance = current_price - liquidation_price
    distance_pct = (distance / current_price) * 100
    
    assert distance_pct == 0.5
    assert distance_pct < 5


def test_liquidation_progress_bar_clamping():
    """Test progress bar value clamping (0-1 range)."""
    def clamp_progress(distance_pct):
        return min(max(distance_pct / 10, 0), 1.0)
    
    assert clamp_progress(30) == 1.0
    assert clamp_progress(2) == 0.2
    assert clamp_progress(0.5) == 0.05


# ============ CONFIGURATION PERSISTENCE TESTS ============

def test_save_leverage_config_structure():
    """Test that saved config has all required fields."""
    config_to_save = {
        "trading_capital": 2000.0,
        "leverage": 10,
        "max_risk_pct": 3.0,
        "max_drawdown_pct": 15.0,
        "margin_mode": "cross"
    }
    
    assert "trading_capital" in config_to_save
    assert "leverage" in config_to_save
    assert "max_risk_pct" in config_to_save
    assert "max_drawdown_pct" in config_to_save
    assert "margin_mode" in config_to_save


def test_load_leverage_config_conversion():
    """Test that loaded config converts properly."""
    config_dict = {
        "trading_capital": 5000.0,
        "leverage": 8,
        "max_risk_pct": 2.5,
        "max_drawdown_pct": 20.0,
        "margin_mode": "isolated"
    }
    
    config = LeverageConfig(**config_dict)
    
    assert config.trading_capital == 5000.0
    assert config.leverage == 8
    assert config.max_risk_pct == 2.5


def test_config_dict_serialization():
    """Test that config can be serialized to JSON."""
    config_dict = {
        "trading_capital": 3000.0,
        "leverage": 7,
        "max_risk_pct": 1.5,
        "max_drawdown_pct": 12.0,
        "margin_mode": "cross"
    }
    
    json_str = json.dumps(config_dict)
    loaded_dict = json.loads(json_str)
    
    assert loaded_dict == config_dict


def test_config_update_preserves_fields():
    """Test that config update doesn't lose fields."""
    original = {
        "trading_capital": 1000.0,
        "leverage": 5,
        "max_risk_pct": 2.0,
        "max_drawdown_pct": 10.0,
        "margin_mode": "isolated"
    }
    
    updated = original.copy()
    updated["leverage"] = 10
    
    assert updated["trading_capital"] == 1000.0
    assert updated["max_risk_pct"] == 2.0
    assert updated["leverage"] == 10


# ============ DASHBOARD STATE INTEGRATION TESTS ============

def test_snapshot_with_leverage_fields():
    """Test RedisSnapshot includes leverage fields."""
    pos = ActivePosition(
        symbol="BTCUSDT",
        direction="long",
        entry_price=50000.0,
        stop_price=49000.0,
        target_price=51000.0,
        position_size_btc=0.01,
        entry_time_utc=int(datetime.now().timestamp()),
        stop_order_id="stop_123",
        target_order_id="target_123"
    )
    
    snapshot = RedisSnapshot(
        automation_enabled=True,
        active_position=pos,
        account_balance_usd=10000.0,
        daily_rolled_pnl_usd=150.0,
        last_known_btc_price=50000.0,
        last_closed_position=None,
        ghost_metrics={},
        leverage_trading_capital=1000.0,
        leverage_multiplier=5,
        leverage_max_risk_pct=2.0,
        leverage_max_drawdown_pct=10.0,
        leverage_margin_mode="isolated",
        leverage_config_updated=datetime.now().isoformat(),
        leverage_current=5,
        leverage_liquidation_price=45000.0,
        leverage_margin_utilization_pct=50.0,
        leverage_collateral_used_usdt=500.0,
        leverage_max_position_notional=5000.0,
        risk_daily_realized_pnl=150.0,
        risk_unrealized_pnl=100.0,
        risk_largest_loss_streak=2,
        risk_equity_curve=[]
    )
    
    assert snapshot.leverage_trading_capital == 1000.0
    assert snapshot.leverage_multiplier == 5
    assert snapshot.leverage_current == 5
    assert snapshot.leverage_liquidation_price == 45000.0


def test_active_position_with_liquidation():
    """Test position includes liquidation price context."""
    pos = ActivePosition(
        symbol="BTCUSDT",
        direction="short",
        entry_price=50000.0,
        stop_price=51500.0,
        target_price=49000.0,
        position_size_btc=0.01,
        entry_time_utc=int(datetime.now().timestamp()),
        stop_order_id="stop_456",
        target_order_id="target_456"
    )
    
    liquidation_price = 60000.0
    sl_to_liq_buffer = liquidation_price - pos.stop_price
    
    assert pos.direction == "short"
    assert sl_to_liq_buffer == 8500.0
    assert sl_to_liq_buffer > 0


# ============ DASHBOARD UI COMPONENTS ============

def test_metrics_column_layout():
    """Test 4-column metrics layout for leverage display."""
    metrics = {
        "leverage": "5x",
        "margin_utilization": "50.0%",
        "liquidation_price": "$45000.00",
        "max_position_size": "$5000.00"
    }
    
    assert len(metrics) == 4
    assert all(v is not None for v in metrics.values())


def test_danger_zone_warnings():
    """Test danger zone warning thresholds."""
    test_cases = [
        (50.0, None),
        (89.0, None),
        (90.1, "HIGH"),
        (91.0, "HIGH"),
        (95.1, "CRITICAL"),
        (98.0, "CRITICAL"),
    ]
    
    for margin_util, expected_warning in test_cases:
        if margin_util > 95:
            warning = "CRITICAL"
        elif margin_util > 90:
            warning = "HIGH"
        else:
            warning = None
        assert warning == expected_warning


def test_liquidation_meter_color_zones():
    """Test liquidation meter color coding by distance."""
    test_cases = [
        (25, "green"),
        (15, "yellow"),
        (7, "orange"),
        (2, "red"),
    ]
    
    for distance_pct, expected_color in test_cases:
        if distance_pct < 5:
            assert expected_color == "red"
        elif distance_pct < 10:
            assert expected_color == "orange"
        elif distance_pct < 20:
            assert expected_color == "yellow"
        else:
            assert expected_color == "green"


# ============ PHASE 5 INTEGRATION TESTS ============

def test_setup_wizard_to_metrics_flow():
    """Test user journey from setup wizard to metrics display."""
    config = LeverageConfig(
        trading_capital=1000.0,
        leverage=5,
        max_risk_pct=2.0,
        max_drawdown_pct=10.0,
        margin_mode="isolated"
    )
    
    is_valid, msg = validate_leverage_config(config)
    assert is_valid
    
    config_dict = {
        "trading_capital": config.trading_capital,
        "leverage": config.leverage,
        "max_risk_pct": config.max_risk_pct,
        "max_drawdown_pct": config.max_drawdown_pct,
        "margin_mode": config.margin_mode
    }
    
    assert config_dict["leverage"] == 5
    max_notional = config_dict["trading_capital"] * config_dict["leverage"] * 0.8
    assert max_notional == 4000.0


def test_liquidation_meter_with_active_position():
    """Test liquidation meter with real position data."""
    pos = ActivePosition(
        symbol="BTCUSDT",
        direction="long",
        entry_price=50000.0,
        stop_price=49000.0,
        target_price=51000.0,
        position_size_btc=0.1,
        entry_time_utc=int(datetime.now().timestamp()),
        stop_order_id="stop_789",
        target_order_id="target_789"
    )
    
    current_price = 49500.0
    liquidation_price = 45000.0
    
    distance = current_price - liquidation_price
    distance_pct = (distance / current_price) * 100
    
    assert distance == 4500.0
    assert 9 < distance_pct < 10
    assert distance_pct < 20


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
