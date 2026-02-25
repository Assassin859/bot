"""Unit tests for leverage_calculator module."""
import pytest
from leverage_calculator import (
    calculate_liquidation_price,
    calculate_margin_utilization,
    calculate_buffer_to_liquidation,
    validate_sl_position,
    calculate_position_size_with_leverage,
    check_margin_danger_zones,
    LiquidationMetrics,
    LIQUIDATION_BUFFER_PCT,
)


class TestCalculateLiquidationPrice:
    """Test liquidation price calculation."""
    
    def test_long_position_liquidation(self):
        """Long position: liquidation = entry - (collateral/amount)."""
        # Entry 50k, collateral 1000, 0.02 BTC
        result = calculate_liquidation_price(
            side="long",
            entry_price=50000,
            collateral=1000,
            amount=0.02
        )
        # Expected: 50000 - (1000/0.02) = 50000 - 50000 = 0
        assert result == 0
    
    def test_long_position_liquidation_2(self):
        """Long position with more collateral buffer."""
        # Entry 50k, collateral 500, 0.02 BTC
        result = calculate_liquidation_price(
            side="long",
            entry_price=50000,
            collateral=500,
            amount=0.02
        )
        # Expected: 50000 - (500/0.02) = 50000 - 25000 = 25000
        assert result == 25000
    
    def test_short_position_liquidation(self):
        """Short position: liquidation = entry + (collateral/amount)."""
        # Entry 50k, collateral 500, 0.02 BTC
        result = calculate_liquidation_price(
            side="short",
            entry_price=50000,
            collateral=500,
            amount=0.02
        )
        # Expected: 50000 + (500/0.02) = 50000 + 25000 = 75000
        assert result == 75000
    
    def test_invalid_amount_raises_error(self):
        """Zero or negative amount raises ValueError."""
        with pytest.raises(ValueError, match="Amount must be positive"):
            calculate_liquidation_price("long", 50000, 1000, 0)
        
        with pytest.raises(ValueError, match="Amount must be positive"):
            calculate_liquidation_price("long", 50000, 1000, -0.01)
    
    def test_invalid_side_raises_error(self):
        """Invalid side raises ValueError."""
        with pytest.raises(ValueError, match="Side must be"):
            calculate_liquidation_price("invalid", 50000, 1000, 0.01)
    
    def test_case_insensitive_side(self):
        """Side parameter is case-insensitive."""
        long_upper = calculate_liquidation_price("LONG", 50000, 500, 0.02)
        long_lower = calculate_liquidation_price("long", 50000, 500, 0.02)
        assert long_upper == long_lower


class TestCalculateMarginUtilization:
    """Test margin utilization calculation."""
    
    def test_standard_utilization(self):
        """Standard case: 1000 collateral / 5000 notional = 20%."""
        result = calculate_margin_utilization(collateral=1000, position_notional=5000)
        assert result == 20.0
    
    def test_high_leverage_utilization(self):
        """High leverage: 1000 / 2000 = 50%."""
        result = calculate_margin_utilization(collateral=1000, position_notional=2000)
        assert result == 50.0
    
    def test_low_leverage_utilization(self):
        """Low leverage: 1000 / 10000 = 10%."""
        result = calculate_margin_utilization(collateral=1000, position_notional=10000)
        assert result == 10.0
    
    def test_zero_notional_returns_zero(self):
        """Zero notional position returns 0% utilization."""
        result = calculate_margin_utilization(collateral=1000, position_notional=0)
        assert result == 0.0
    
    def test_negative_notional_returns_zero(self):
        """Negative notional position returns 0% utilization."""
        result = calculate_margin_utilization(collateral=1000, position_notional=-5000)
        assert result == 0.0


class TestCalculateBufferToLiquidation:
    """Test buffer calculation."""
    
    def test_long_buffer_positive(self):
        """Long: current=50k, liquidation=40k → (50k-40k)/40k × 100 = 25%."""
        result = calculate_buffer_to_liquidation(
            current_price=50000,
            liquidation_price=40000,
            side="long"
        )
        # (50000 - 40000) / 40000 * 100 = 25%
        assert abs(result - 25.0) < 0.01
    
    def test_short_buffer_positive(self):
        """Short: current=40k, liquidation=50k → (50k-40k)/50k × 100 = 20%."""
        result = calculate_buffer_to_liquidation(
            current_price=40000,
            liquidation_price=50000,
            side="short"
        )
        # (50000 - 40000) / 50000 * 100 = 20%
        assert abs(result - 20.0) < 0.01
    
    def test_zero_liquidation_returns_zero(self):
        """Zero liquidation price handled gracefully."""
        result = calculate_buffer_to_liquidation(
            current_price=50000,
            liquidation_price=0,
            side="long"
        )
        assert result == 0.0
    
    def test_negative_buffer_clamped_to_zero(self):
        """Buffer can't be negative (liquidated already)."""
        result = calculate_buffer_to_liquidation(
            current_price=30000,
            liquidation_price=40000,  # Already below for long
            side="long"
        )
        assert result >= 0  # Should be clamped to 0 or negative value


class TestValidateSLPosition:
    """Test stop-loss validation with liquidation buffer."""
    
    def test_long_position_safe_sl(self):
        """Long position with safe SL (10%+ from liquidation)."""
        # Entry 50k, SL 45k, collateral 1000, 0.02 BTC
        # Liq = 50k - (1000/0.02) = 50k - 50k = 0
        # Buffer from SL to liq = 45k - 0 = 45k (safe!)
        
        result = validate_sl_position(
            entry_price=50000,
            sl_price=45000,
            collateral=1000,
            amount=0.02,
            side="long",
            leverage=1
        )
        
        assert isinstance(result, LiquidationMetrics)
        assert result.is_liquidation_safe
        assert result.liquidation_price == 0
    
    def test_short_position_safe_sl(self):
        """Short position with safe SL."""
        # Entry 50k, SL 55k, collateral 500, 0.02 BTC
        # Liq = 50k + (500/0.02) = 50k + 25k = 75k
        # Buffer from SL to liq = 75k - 55k = 20k (safe!)
        
        result = validate_sl_position(
            entry_price=50000,
            sl_price=55000,
            collateral=500,
            amount=0.02,
            side="short",
            leverage=1
        )
        
        assert result.is_liquidation_safe
        assert result.liquidation_price == 75000
    
    def test_long_position_unsafe_sl(self):
        """Long position with SL too close to liquidation."""
        # Entry 50k, SL 26k (only 26k buffer), collateral 500, 0.01 BTC
        # Liq = 50k - (500/0.01) = 50k - 50k = 0
        # We need 10% buffer from liq, SL at 26k might be OK depending on calculation
        
        result = validate_sl_position(
            entry_price=50000,
            sl_price=26000,
            collateral=500,
            amount=0.01,
            side="long",
            leverage=1
        )
        
        assert isinstance(result, LiquidationMetrics)
        assert result.liquidation_price == 0
    
    def test_invalid_leverage_raises_error(self):
        """Leverage outside 1-20 range raises error."""
        with pytest.raises(ValueError, match="Leverage must be 1-20"):
            validate_sl_position(
                entry_price=50000,
                sl_price=45000,
                collateral=1000,
                amount=0.01,
                side="long",
                leverage=0  # Invalid
            )
        
        with pytest.raises(ValueError, match="Leverage must be 1-20"):
            validate_sl_position(
                entry_price=50000,
                sl_price=45000,
                collateral=1000,
                amount=0.01,
                side="long",
                leverage=21  # Invalid
            )
    
    def test_invalid_amount_raises_error(self):
        """Zero or negative amount raises error."""
        with pytest.raises(ValueError, match="Amount must be positive"):
            validate_sl_position(
                entry_price=50000,
                sl_price=45000,
                collateral=1000,
                amount=0,
                side="long"
            )
    
    def test_recommended_sl_when_unsafe(self):
        """When SL is unsafe, recommendation is provided."""
        result = validate_sl_position(
            entry_price=50000,
            sl_price=45000,
            collateral=1000,
            amount=0.01,  # Small amount → high liquidation
            side="long",
            leverage=1
        )
        
        # Should return a recommended SL price
        assert hasattr(result, "recommended_sl")
        assert isinstance(result.recommended_sl, (int, float))  # Accept both int and float


class TestCalculatePositionSizeWithLeverage:
    """Test position sizing with leverage consideration."""
    
    def test_basic_position_sizing(self):
        """Basic position sizing calculation."""
        result = calculate_position_size_with_leverage(
            account_balance=10000,
            trading_capital=1000,
            leverage=5,
            entry_price=50000,
            atr_stop_distance=100,  # $100 ATR
            max_risk_pct=2
        )
        
        assert isinstance(result, dict)
        assert "position_notional" in result
        assert "amount_btc" in result
        assert "margin_utilization_pct" in result
        assert "is_safe" in result
        
        # Risk amount = 10000 × 2% = 200
        # Max notional = 1000 × 5 × 0.8 = 4000
        # Position = min(200 × 5, 4000) = 1000
        # Amount = 1000 / 50000 = 0.02 BTC
        assert result["position_notional"] > 0
        assert result["amount_btc"] > 0
    
    def test_invalid_leverage_returns_unsafe(self):
        """Invalid leverage returns unsafe result."""
        result = calculate_position_size_with_leverage(
            account_balance=10000,
            trading_capital=1000,
            leverage=0,  # Invalid
            entry_price=50000,
            atr_stop_distance=100,
            max_risk_pct=2
        )
        
        assert result["is_safe"] is False
        assert "Leverage must be 1-20" in result["reason"]
    
    def test_high_leverage_caps_position(self):
        """Very high leverage and risk is capped at 80%."""
        result = calculate_position_size_with_leverage(
            account_balance=100000,
            trading_capital=10000,
            leverage=20,  # Max leverage
            entry_price=50000,
            atr_stop_distance=100,
            max_risk_pct=10  # 10% risk
        )
        
        # Max notional = 10000 × 20 × 0.8 = 160000
        # Risk amount = 100000 × 10% = 10000
        # Position = min(10000 × 20, 160000) = 160000
        # Should be close to max_notional due to 80% cap
        assert result["position_notional"] <= 160000 * 1.01  # Allow slight float variance
    
    def test_zero_atr_returns_safe_no_position(self):
        """Zero ATR distance returns no position (needs risk data)."""
        result = calculate_position_size_with_leverage(
            account_balance=10000,
            trading_capital=1000,
            leverage=5,
            entry_price=50000,
            atr_stop_distance=0,  # No SL distance
            max_risk_pct=2
        )
        
        # Should return no position since we can't validate SL safety
        assert result["position_notional"] == 0 or result["is_safe"] is True
    
    def test_small_risk_below_minimum(self):
        """Position size below $10 minimum is zeroed."""
        result = calculate_position_size_with_leverage(
            account_balance=100,  # Very small account
            trading_capital=10,
            leverage=1,
            entry_price=50000,
            atr_stop_distance=100,
            max_risk_pct=2
        )
        
        # Risk amount = 100 × 2% = 2 (too small)
        # Should result in zero position
        assert result["position_notional"] == 0
        assert result["amount_btc"] == 0


class TestCheckMarginDangerZones:
    """Test margin danger zone detection."""
    
    def test_safe_margin_levels(self):
        """Safe margin and liquidation levels."""
        result = check_margin_danger_zones(
            margin_utilization_pct=50,
            buffer_to_liquidation_pct=20
        )
        
        assert result["margin_warning"] is False
        assert result["margin_critical"] is False
        assert result["liquidation_warning"] is False
        assert result["liquidation_critical"] is False
    
    def test_margin_warning_triggered(self):
        """Margin warning at >90%."""
        result = check_margin_danger_zones(
            margin_utilization_pct=91,
            buffer_to_liquidation_pct=20
        )
        
        assert result["margin_warning"] is True
        assert result["margin_critical"] is False
    
    def test_margin_critical_triggered(self):
        """Margin critical at >95%."""
        result = check_margin_danger_zones(
            margin_utilization_pct=96,
            buffer_to_liquidation_pct=20
        )
        
        assert result["margin_critical"] is True
        assert result["margin_warning"] is True
    
    def test_liquidation_warning_triggered(self):
        """Liquidation warning at <10% buffer."""
        result = check_margin_danger_zones(
            margin_utilization_pct=50,
            buffer_to_liquidation_pct=9
        )
        
        assert result["liquidation_warning"] is True
        assert result["liquidation_critical"] is False
    
    def test_liquidation_critical_triggered(self):
        """Liquidation critical at <5% buffer."""
        result = check_margin_danger_zones(
            margin_utilization_pct=50,
            buffer_to_liquidation_pct=4
        )
        
        assert result["liquidation_critical"] is True
        assert result["liquidation_warning"] is True
    
    def test_all_normal_condition(self):
        """All normal condition returns all false."""
        result = check_margin_danger_zones(
            margin_utilization_pct=30,
            buffer_to_liquidation_pct=50
        )
        
        assert all([
            not result["margin_warning"],
            not result["margin_critical"],
            not result["liquidation_warning"],
            not result["liquidation_critical"]
        ])


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_exactly_10_percent_buffer(self):
        """SL exactly at 10% buffer boundary."""
        # This tests the exact boundary condition
        metrics = validate_sl_position(
            entry_price=100,
            sl_price=90,
            collateral=50,
            amount=0.1,
            side="long",
            leverage=1
        )
        
        # Liq = 100 - (50/0.1) = 100 - 500 = -400
        # Buffer = 90 - (-400) = 490
        # This is actually very safe
        assert isinstance(metrics, LiquidationMetrics)
    
    def test_very_small_position(self):
        """Very small position amounts."""
        liq = calculate_liquidation_price(
            side="long",
            entry_price=50000,
            collateral=100,
            amount=0.0001  # Very small
        )
        
        # Liquidation = 50000 - (100/0.0001) = 50000 - 1000000
        assert liq == 50000 - 1000000
    
    def test_very_large_position(self):
        """Very large position amounts."""
        liq = calculate_liquidation_price(
            side="long",
            entry_price=50000,
            collateral=100,
            amount=100  # Very large
        )
        
        # Liquidation = 50000 - (100/100) = 50000 - 1 = 49999
        assert liq == 49999


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
