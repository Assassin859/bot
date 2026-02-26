"""Tests for RiskMonitor behaviour and alert generation"""

import pytest
import asyncio

from risk_monitor import RiskMonitor, AlertLevel


@pytest.mark.asyncio
async def test_margin_utilization_checks():
    rm = RiskMonitor()

    # safe zone
    res = await rm.check_margin_utilization(30)
    assert res["safe"]
    assert res["alerts"] == []

    # high utilization warning
    res = await rm.check_margin_utilization(60)
    assert res["safe"]
    assert any("High margin" in a["message"] for a in res["alerts"])

    # danger zone
    res = await rm.check_margin_utilization(85)
    assert res["safe"]
    assert any("LIQUIDATION DANGER" in a["message"] for a in res["alerts"])

    # critical / auto-close
    res = await rm.check_margin_utilization(95, auto_close_threshold_pct=90)
    assert not res["safe"]
    assert res["action"] == "EMERGENCY_CLOSE_ALL_POSITIONS"


@pytest.mark.asyncio
async def test_daily_loss_limit_checks():
    rm = RiskMonitor()
    # below threshold
    r = await rm.check_daily_loss_limit(10, max_daily_loss=25)
    assert r["safe"]
    assert r["alerts"] == []

    # warning zone
    r = await rm.check_daily_loss_limit(20, max_daily_loss=25)
    assert r["safe"]
    assert any("Approaching daily loss" in a["message"] for a in r["alerts"])

    # exceeded limit
    r = await rm.check_daily_loss_limit(30, max_daily_loss=25)
    assert not r["safe"]
    assert r["action"] == "HALT_ALL_TRADING"


@pytest.mark.asyncio
async def test_position_limits():
    rm = RiskMonitor()

    r = await rm.check_position_limits(1, max_positions=2)
    assert r["safe"]
    assert r["alerts"] == []

    r = await rm.check_position_limits(2, max_positions=2)
    assert r["safe"]
    assert any("Max positions reached" in a["message"] for a in r["alerts"])

    r = await rm.check_position_limits(3, max_positions=2)
    assert not r["safe"]
    assert r["action"] == "CLOSE_EXCESS_POSITIONS"


@pytest.mark.asyncio
async def test_drawdown_calculation_and_alert():
    rm = RiskMonitor()
    history = [100, 110, 105, 120, 90, 95]
    res = await rm.calculate_max_drawdown(history)
    assert res["max_drawdown_pct"] > 0
    assert res["current_drawdown_pct"] >= 0
    # since drawdown exceed 20% (peak 120 -> 90 = 25%), should have alert
    assert any(a.level == AlertLevel.WARNING for a in rm.alerts)

    # empty history
    res2 = await rm.calculate_max_drawdown([])
    assert res2["max_drawdown_pct"] == 0


@pytest.mark.asyncio
async def test_generate_risk_report_comprehensive():
    rm = RiskMonitor()
    report = await rm.generate_risk_report(
        account_balance=1000,
        account_equity=1100,
        margin_utilization=40,
        daily_loss=5,
        max_daily_loss=25,
        open_positions=1,
        equity_history=[1000, 1050, 1025],
    )
    assert report["overall_safe"]
    assert "checks" in report
    assert "margin" in report["checks"]
    assert isinstance(report["alerts"], list)

    recent = await rm.get_recent_alerts()
    assert isinstance(recent, list)
    await rm.clear_alerts()
    assert await rm.get_recent_alerts() == []
