"""Unit tests for config module with leverage support."""
import pytest
from config import (
    LeverageConfig,
    validate_leverage_config,
    DEFAULT_LEVERAGE,
    MAX_LEVERAGE,
    MIN_LEVERAGE,
    DEFAULT_TRADING_CAPITAL,
    DEFAULT_MAX_RISK_PCT,
    DEFAULT_MAX_DRAWDOWN_PCT,
    LIQUIDATION_BUFFER_PCT,
    MARGIN_DANGER_ZONE_PCT,
    MARGIN_FORCE_CLOSE_PCT,
)


class TestLeverageConfigCreation:
    """Test LeverageConfig dataclass creation."""
    
    def test_create_default_config(self):
        """Create LeverageConfig with defaults."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        assert config.trading_capital == 1000
        assert config.leverage == 5
        assert config.max_risk_pct == 2.0
        assert config.max_drawdown_pct == 10.0
        assert config.margin_mode == "isolated"
    
    def test_create_config_with_cross_margin(self):
        """Create LeverageConfig with cross margin mode."""
        config = LeverageConfig(
            trading_capital=5000,
            leverage=10,
            max_risk_pct=3.0,
            max_drawdown_pct=20.0,
            margin_mode="cross"
        )
        
        assert config.margin_mode == "cross"
    
    def test_create_max_leverage_config(self):
        """Create config with maximum leverage."""
        config = LeverageConfig(
            trading_capital=10000,
            leverage=20,
            max_risk_pct=5.0,
            max_drawdown_pct=25.0
        )
        
        assert config.leverage == 20
    
    def test_create_min_leverage_config(self):
        """Create config with minimum leverage (1x)."""
        config = LeverageConfig(
            trading_capital=500,
            leverage=1,
            max_risk_pct=1.0,
            max_drawdown_pct=5.0
        )
        
        assert config.leverage == 1


class TestValidateLeverageConfig:
    """Test leverage configuration validation."""
    
    def test_valid_config_passes(self):
        """Valid configuration passes validation."""
        config = LeverageConfig(
            trading_capital=2000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
        assert "valid" in message.lower()
    
    def test_invalid_trading_capital_zero(self):
        """Zero trading capital fails validation."""
        config = LeverageConfig(
            trading_capital=0,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "trading capital" in message.lower()
    
    def test_invalid_trading_capital_negative(self):
        """Negative trading capital fails validation."""
        config = LeverageConfig(
            trading_capital=-1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
    
    def test_invalid_trading_capital_too_large(self):
        """Trading capital > 100k fails validation."""
        config = LeverageConfig(
            trading_capital=100001,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "100000" in message
    
    def test_valid_trading_capital_boundary_low(self):
        """Trading capital at low but valid boundary passes."""
        config = LeverageConfig(
            trading_capital=1.0,  # Must be > 0, and 1 is > 0
            leverage=1,
            max_risk_pct=1.0,
            max_drawdown_pct=5.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_valid_trading_capital_boundary_high(self):
        """Trading capital at high boundary passes."""
        config = LeverageConfig(
            trading_capital=100000,
            leverage=1,
            max_risk_pct=1.0,
            max_drawdown_pct=5.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_invalid_leverage_too_low(self):
        """Leverage < 1 fails validation."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=0,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "leverage" in message.lower()
    
    def test_invalid_leverage_too_high(self):
        """Leverage > 20 fails validation."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=21,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "20" in message
    
    def test_valid_leverage_boundary_low(self):
        """Leverage = 1 passes."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=1,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_valid_leverage_boundary_high(self):
        """Leverage = 20 passes."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=20,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_invalid_risk_pct_too_low(self):
        """Risk % <= 0.5 fails validation."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=0.4,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "risk" in message.lower()
    
    def test_invalid_risk_pct_too_high(self):
        """Risk % > 10 fails validation."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=10.1,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "risk" in message.lower()
    
    def test_valid_risk_pct_boundary_low(self):
        """Risk % just above minimum boundary passes."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=0.51,  # Must be > 0.5
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_valid_risk_pct_boundary_high(self):
        """Risk % = 10 passes."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=10.0,
            max_drawdown_pct=10.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_invalid_drawdown_pct_too_low(self):
        """Drawdown % < 5 fails validation."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=4.9
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "drawdown" in message.lower()
    
    def test_invalid_drawdown_pct_too_high(self):
        """Drawdown % > 50 fails validation."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=50.1
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "drawdown" in message.lower()
    
    def test_valid_drawdown_pct_boundary_low(self):
        """Drawdown % = 5 passes."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=5.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_valid_drawdown_pct_boundary_high(self):
        """Drawdown % = 50 passes."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=50.0
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is True
    
    def test_invalid_margin_mode(self):
        """Invalid margin mode fails validation."""
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0,
            margin_mode="invalid"  # type: ignore
        )
        
        is_valid, message = validate_leverage_config(config)
        assert is_valid is False
        assert "margin mode" in message.lower()


class TestConstantsPresent:
    """Test that all expected constants are defined."""
    
    def test_leverage_constants(self):
        """All leverage constants are defined."""
        assert DEFAULT_LEVERAGE == 5
        assert MAX_LEVERAGE == 20
        assert MIN_LEVERAGE == 1
    
    def test_capital_constants(self):
        """Capital constants are defined."""
        assert DEFAULT_TRADING_CAPITAL == 1000.0
        assert DEFAULT_MAX_RISK_PCT == 2.0
        assert DEFAULT_MAX_DRAWDOWN_PCT == 10.0
    
    def test_safety_constants(self):
        """Safety constants are defined."""
        assert LIQUIDATION_BUFFER_PCT == 10.0
        assert MARGIN_DANGER_ZONE_PCT == 90.0
        assert MARGIN_FORCE_CLOSE_PCT == 95.0
    
    def test_constant_relationships(self):
        """Constants have expected relationships."""
        assert MIN_LEVERAGE < DEFAULT_LEVERAGE < MAX_LEVERAGE
        assert MARGIN_DANGER_ZONE_PCT < MARGIN_FORCE_CLOSE_PCT
        assert LIQUIDATION_BUFFER_PCT > 0


class TestConfigIntegration:
    """Test integration of config with leverage components."""
    
    def test_config_with_leverage_calculator(self):
        """LeverageConfig can be used with leverage_calculator."""
        from leverage_calculator import calculate_liquidation_price
        
        config = LeverageConfig(
            trading_capital=1000,
            leverage=5,
            max_risk_pct=2.0,
            max_drawdown_pct=10.0
        )
        
        # Should be able to calculate liquidation
        liq = calculate_liquidation_price(
            side="long",
            entry_price=50000,
            collateral=config.trading_capital,
            amount=0.02
        )
        assert isinstance(liq, float)
    
    def test_config_persists_across_validations(self):
        """Config remains unchanged after validation."""
        config = LeverageConfig(
            trading_capital=2500,
            leverage=4,
            max_risk_pct=3.0,
            max_drawdown_pct=15.0
        )
        
        # Validate doesn't modify config
        validate_leverage_config(config)
        
        assert config.trading_capital == 2500
        assert config.leverage == 4
        assert config.max_risk_pct == 3.0
        assert config.max_drawdown_pct == 15.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
