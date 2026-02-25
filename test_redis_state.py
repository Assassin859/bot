"""Unit tests for redis_state.py with leverage support."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from redis_state import (
    RedisState,
    RedisSnapshot,
    K_LEVERAGE_TRADING_CAPITAL,
    K_LEVERAGE_MULTIPLIER,
    K_LEVERAGE_MAX_RISK_PCT,
    K_LEVERAGE_MAX_DRAWDOWN_PCT,
    K_LEVERAGE_MARGIN_MODE,
    K_LEVERAGE_CONFIG_UPDATED,
    K_LEVERAGE_CURRENT,
    K_LEVERAGE_LIQUIDATION_PRICE,
    K_LEVERAGE_MARGIN_UTILIZATION,
    K_LEVERAGE_COLLATERAL_USED,
    K_LEVERAGE_MAX_POSITION_NOTIONAL,
    K_RISK_DAILY_REALIZED_PNL,
    K_RISK_UNREALIZED_PNL,
    K_RISK_LARGEST_LOSS_STREAK,
    K_RISK_EQUITY_CURVE,
)


@pytest.fixture
def mock_redis_state():
    """Create a mock RedisState for testing."""
    with patch('redis_state.aioredis.from_url') as mock_from_url:
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        
        state = RedisState("redis://localhost:6379/0")
        state._client = mock_client
        
        return state


class TestLeverageConfigKeys:
    """Test leverage configuration key storage and retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_set_leverage_trading_capital(self, mock_redis_state):
        """Test trading capital get/set."""
        mock_redis_state._client.get.return_value = "5000.0"
        
        result = await mock_redis_state.get_leverage_trading_capital()
        assert result == 5000.0
        
        await mock_redis_state.set_leverage_trading_capital(2500.0)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_TRADING_CAPITAL, "2500.0")
    
    @pytest.mark.asyncio
    async def test_get_set_leverage_multiplier(self, mock_redis_state):
        """Test leverage multiplier get/set."""
        mock_redis_state._client.get.return_value = "10"
        
        result = await mock_redis_state.get_leverage_multiplier()
        assert result == 10
        
        await mock_redis_state.set_leverage_multiplier(15)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_MULTIPLIER, "15")
    
    @pytest.mark.asyncio
    async def test_get_set_leverage_max_risk_pct(self, mock_redis_state):
        """Test max risk percentage get/set."""
        mock_redis_state._client.get.return_value = "3.5"
        
        result = await mock_redis_state.get_leverage_max_risk_pct()
        assert result == 3.5
        
        await mock_redis_state.set_leverage_max_risk_pct(4.0)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_MAX_RISK_PCT, "4.0")
    
    @pytest.mark.asyncio
    async def test_get_set_leverage_max_drawdown_pct(self, mock_redis_state):
        """Test max drawdown percentage get/set."""
        mock_redis_state._client.get.return_value = "15.0"
        
        result = await mock_redis_state.get_leverage_max_drawdown_pct()
        assert result == 15.0
        
        await mock_redis_state.set_leverage_max_drawdown_pct(20.0)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_MAX_DRAWDOWN_PCT, "20.0")
    
    @pytest.mark.asyncio
    async def test_get_set_leverage_margin_mode(self, mock_redis_state):
        """Test margin mode get/set."""
        mock_redis_state._client.get.return_value = "cross"
        
        result = await mock_redis_state.get_leverage_margin_mode()
        assert result == "cross"
        
        await mock_redis_state.set_leverage_margin_mode("isolated")
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_MARGIN_MODE, "isolated")
    
    @pytest.mark.asyncio
    async def test_set_leverage_margin_mode_invalid(self, mock_redis_state):
        """Invalid margin mode raises error."""
        with pytest.raises(ValueError):
            await mock_redis_state.set_leverage_margin_mode("invalid")
    
    @pytest.mark.asyncio
    async def test_get_leverage_config_dict(self, mock_redis_state):
        """Test get_leverage_config returns complete dict."""
        mock_redis_state._client.get.side_effect = lambda key: {
            K_LEVERAGE_TRADING_CAPITAL: "1000.0",
            K_LEVERAGE_MULTIPLIER: "5",
            K_LEVERAGE_MAX_RISK_PCT: "2.0",
            K_LEVERAGE_MAX_DRAWDOWN_PCT: "10.0",
            K_LEVERAGE_MARGIN_MODE: "isolated",
            K_LEVERAGE_CONFIG_UPDATED: "2026-02-24T10:00:00Z",
        }.get(key)
        
        config = await mock_redis_state.get_leverage_config()
        
        assert config["trading_capital"] == 1000.0
        assert config["leverage"] == 5
        assert config["max_risk_pct"] == 2.0
        assert config["max_drawdown_pct"] == 10.0
        assert config["margin_mode"] == "isolated"


class TestLeverageStateKeys:
    """Test leverage state storage and retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_set_leverage_current(self, mock_redis_state):
        """Test current leverage get/set."""
        mock_redis_state._client.get.return_value = "7"
        
        result = await mock_redis_state.get_leverage_current()
        assert result == 7
        
        await mock_redis_state.set_leverage_current(8)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_CURRENT, "8")
    
    @pytest.mark.asyncio
    async def test_get_set_liquidation_price(self, mock_redis_state):
        """Test liquidation price get/set."""
        mock_redis_state._client.get.return_value = "45000.50"
        
        result = await mock_redis_state.get_leverage_liquidation_price()
        assert result == 45000.50
        
        await mock_redis_state.set_leverage_liquidation_price(46000.0)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_LIQUIDATION_PRICE, "46000.0")
    
    @pytest.mark.asyncio
    async def test_get_set_margin_utilization(self, mock_redis_state):
        """Test margin utilization percentage get/set."""
        mock_redis_state._client.get.return_value = "65.5"
        
        result = await mock_redis_state.get_leverage_margin_utilization()
        assert result == 65.5
        
        await mock_redis_state.set_leverage_margin_utilization(75.0)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_MARGIN_UTILIZATION, "75.0")
    
    @pytest.mark.asyncio
    async def test_get_set_collateral_used(self, mock_redis_state):
        """Test collateral used get/set."""
        mock_redis_state._client.get.return_value = "800.0"
        
        result = await mock_redis_state.get_leverage_collateral_used()
        assert result == 800.0
        
        await mock_redis_state.set_leverage_collateral_used(900.0)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_COLLATERAL_USED, "900.0")
    
    @pytest.mark.asyncio
    async def test_get_set_max_position_notional(self, mock_redis_state):
        """Test max position notional get/set."""
        mock_redis_state._client.get.return_value = "5000.0"
        
        result = await mock_redis_state.get_leverage_max_position_notional()
        assert result == 5000.0
        
        await mock_redis_state.set_leverage_max_position_notional(6000.0)
        mock_redis_state._client.set.assert_called_with(K_LEVERAGE_MAX_POSITION_NOTIONAL, "6000.0")
    
    @pytest.mark.asyncio
    async def test_get_leverage_state_dict(self, mock_redis_state):
        """Test get_leverage_state returns complete dict."""
        mock_redis_state._client.get.side_effect = lambda key: {
            K_LEVERAGE_CURRENT: "5",
            K_LEVERAGE_LIQUIDATION_PRICE: "45000.0",
            K_LEVERAGE_MARGIN_UTILIZATION: "60.0",
            K_LEVERAGE_COLLATERAL_USED: "1000.0",
            K_LEVERAGE_MAX_POSITION_NOTIONAL: "5000.0",
        }.get(key)
        
        state = await mock_redis_state.get_leverage_state()
        
        assert state["current_leverage"] == 5
        assert state["liquidation_price"] == 45000.0
        assert state["margin_utilization_pct"] == 60.0
        assert state["collateral_used_usdt"] == 1000.0
        assert state["max_position_notional"] == 5000.0


class TestRiskTrackingKeys:
    """Test risk tracking storage and retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_set_daily_realized_pnl(self, mock_redis_state):
        """Test daily realized PnL get/set."""
        mock_redis_state._client.get.return_value = "125.50"
        
        result = await mock_redis_state.get_risk_daily_realized_pnl()
        assert result == 125.50
        
        await mock_redis_state.set_risk_daily_realized_pnl(150.25)
        mock_redis_state._client.set.assert_called_with(K_RISK_DAILY_REALIZED_PNL, "150.25")
    
    @pytest.mark.asyncio
    async def test_get_set_unrealized_pnl(self, mock_redis_state):
        """Test unrealized PnL get/set."""
        mock_redis_state._client.get.return_value = "-50.0"
        
        result = await mock_redis_state.get_risk_unrealized_pnl()
        assert result == -50.0
        
        await mock_redis_state.set_risk_unrealized_pnl(200.0)
        mock_redis_state._client.set.assert_called_with(K_RISK_UNREALIZED_PNL, "200.0")
    
    @pytest.mark.asyncio
    async def test_get_set_largest_loss_streak(self, mock_redis_state):
        """Test largest loss streak get/set."""
        mock_redis_state._client.get.return_value = "3"
        
        result = await mock_redis_state.get_risk_largest_loss_streak()
        assert result == 3
        
        await mock_redis_state.set_risk_largest_loss_streak(5)
        mock_redis_state._client.set.assert_called_with(K_RISK_LARGEST_LOSS_STREAK, "5")
    
    @pytest.mark.asyncio
    async def test_get_set_equity_curve(self, mock_redis_state):
        """Test equity curve get/set."""
        import json
        curve_data = [
            {"timestamp": "2026-02-24T10:00:00Z", "equity": 10000},
            {"timestamp": "2026-02-24T11:00:00Z", "equity": 10150},
            {"timestamp": "2026-02-24T12:00:00Z", "equity": 10200},
        ]
        mock_redis_state._client.get.return_value = json.dumps(curve_data)
        
        result = await mock_redis_state.get_risk_equity_curve()
        assert isinstance(result, list)
        assert len(result) == 3
        
        await mock_redis_state.set_risk_equity_curve(curve_data)
        mock_redis_state._client.set.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_risk_tracking_dict(self, mock_redis_state):
        """Test get_risk_tracking returns complete dict."""
        mock_redis_state._client.get.side_effect = lambda key: {
            K_RISK_DAILY_REALIZED_PNL: "100.0",
            K_RISK_UNREALIZED_PNL: "50.0",
            K_RISK_LARGEST_LOSS_STREAK: "2",
            K_RISK_EQUITY_CURVE: None,
        }.get(key)
        
        tracking = await mock_redis_state.get_risk_tracking()
        
        assert tracking["daily_realized_pnl"] == 100.0
        assert tracking["unrealized_pnl"] == 50.0
        assert tracking["largest_loss_streak"] == 2
        assert tracking["equity_curve"] == []


class TestDefaultValues:
    """Test default values when Redis keys are missing."""
    
    @pytest.mark.asyncio
    async def test_default_leverage_values(self, mock_redis_state):
        """Missing leverage keys return sensible defaults."""
        mock_redis_state._client.get.return_value = None
        
        assert await mock_redis_state.get_leverage_trading_capital() == 1000.0
        assert await mock_redis_state.get_leverage_multiplier() == 5
        assert await mock_redis_state.get_leverage_max_risk_pct() == 2.0
        assert await mock_redis_state.get_leverage_max_drawdown_pct() == 10.0
        assert await mock_redis_state.get_leverage_margin_mode() == "isolated"
    
    @pytest.mark.asyncio
    async def test_default_leverage_state_values(self, mock_redis_state):
        """Missing leverage state keys return sensible defaults."""
        mock_redis_state._client.get.return_value = None
        
        assert await mock_redis_state.get_leverage_current() == 1
        assert await mock_redis_state.get_leverage_liquidation_price() == 0.0
        assert await mock_redis_state.get_leverage_margin_utilization() == 0.0
        assert await mock_redis_state.get_leverage_collateral_used() == 0.0
        assert await mock_redis_state.get_leverage_max_position_notional() == 0.0
    
    @pytest.mark.asyncio
    async def test_default_risk_tracking_values(self, mock_redis_state):
        """Missing risk tracking keys return sensible defaults."""
        mock_redis_state._client.get.return_value = None
        
        assert await mock_redis_state.get_risk_daily_realized_pnl() == 0.0
        assert await mock_redis_state.get_risk_unrealized_pnl() == 0.0
        assert await mock_redis_state.get_risk_largest_loss_streak() == 0
        assert await mock_redis_state.get_risk_equity_curve() == []


class TestInvalidValueHandling:
    """Test handling of invalid values from Redis."""
    
    @pytest.mark.asyncio
    async def test_invalid_float_handling(self, mock_redis_state):
        """Invalid float values return default."""
        mock_redis_state._client.get.return_value = "not_a_number"
        
        assert await mock_redis_state.get_leverage_trading_capital() == 1000.0
        assert await mock_redis_state.get_leverage_max_risk_pct() == 2.0
    
    @pytest.mark.asyncio
    async def test_invalid_int_handling(self, mock_redis_state):
        """Invalid int values return default."""
        mock_redis_state._client.get.return_value = "not_an_int"
        
        assert await mock_redis_state.get_leverage_multiplier() == 5
        assert await mock_redis_state.get_leverage_current() == 1
    
    @pytest.mark.asyncio
    async def test_invalid_margin_mode_returns_default(self, mock_redis_state):
        """Invalid margin mode returns default."""
        mock_redis_state._client.get.return_value = "invalid_mode"
        
        assert await mock_redis_state.get_leverage_margin_mode() == "isolated"


class TestRedisSnapshotWithLeverage:
    """Test RedisSnapshot includes all leverage fields."""
    
    def test_snapshot_has_leverage_config_fields(self):
        """RedisSnapshot includes leverage config fields."""
        snapshot = RedisSnapshot(
            automation_enabled=True,
            leverage_trading_capital=2000.0,
            leverage_multiplier=10,
            leverage_max_risk_pct=3.0,
            leverage_max_drawdown_pct=15.0,
            leverage_margin_mode="cross"
        )
        
        assert snapshot.leverage_trading_capital == 2000.0
        assert snapshot.leverage_multiplier == 10
        assert snapshot.leverage_max_risk_pct == 3.0
        assert snapshot.leverage_max_drawdown_pct == 15.0
        assert snapshot.leverage_margin_mode == "cross"
    
    def test_snapshot_has_leverage_state_fields(self):
        """RedisSnapshot includes leverage state fields."""
        snapshot = RedisSnapshot(
            automation_enabled=True,
            leverage_current=5,
            leverage_liquidation_price=45000.0,
            leverage_margin_utilization_pct=65.5,
            leverage_collateral_used_usdt=800.0,
            leverage_max_position_notional=5000.0
        )
        
        assert snapshot.leverage_current == 5
        assert snapshot.leverage_liquidation_price == 45000.0
        assert snapshot.leverage_margin_utilization_pct == 65.5
        assert snapshot.leverage_collateral_used_usdt == 800.0
        assert snapshot.leverage_max_position_notional == 5000.0
    
    def test_snapshot_has_risk_tracking_fields(self):
        """RedisSnapshot includes risk tracking fields."""
        snapshot = RedisSnapshot(
            automation_enabled=True,
            risk_daily_realized_pnl=150.0,
            risk_unrealized_pnl=50.0,
            risk_largest_loss_streak=3,
            risk_equity_curve=[{"time": "10:00", "equity": 10000}]
        )
        
        assert snapshot.risk_daily_realized_pnl == 150.0
        assert snapshot.risk_unrealized_pnl == 50.0
        assert snapshot.risk_largest_loss_streak == 3
        assert len(snapshot.risk_equity_curve) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
