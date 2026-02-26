"""Live mode executor tests – verify risk checks and order flow"""

import pytest
import asyncio
from datetime import datetime, timedelta

from live_executor import LiveExecutor, MAX_POSITION_VALUE_USD, MAX_DAILY_LOSS
from live_executor import ApprovalStatus, ExecutionStatus, RiskCheck


@pytest.mark.asyncio
async def test_live_executor_initializes():
    executor = LiveExecutor(account_balance_usd=500.0)
    assert executor.account_balance_usd == 500.0
    assert executor.approval_status == ApprovalStatus.NOT_APPROVED
    assert executor.daily_realized_pnl == 0.0
    assert executor.weekly_realized_pnl == 0.0
    assert executor.open_positions == {}
    await executor.request_live_approval()  # cleanup


@pytest.mark.asyncio
async def test_request_live_approval_requires_confirmation():
    executor = LiveExecutor()
    ok, msg = await executor.request_live_approval(user_confirmation=False)
    assert ok is False
    assert "confirmation" in msg.lower()

    ok2, msg2 = await executor.request_live_approval(user_confirmation=True)
    assert ok2 is True
    assert executor.approval_status == ApprovalStatus.LIVE_APPROVED


@pytest.mark.asyncio
async def test_validate_trade_rejections():
    executor = LiveExecutor()
    # not approved
    check = await executor.validate_trade_allowed("BTC/USDT", 0.001, 100.0)
    assert check.is_allowed is False
    assert check.reason == "NOT_APPROVED"

    # approve
    await executor.request_live_approval(user_confirmation=True)
    # symbol not whitelisted
    check = await executor.validate_trade_allowed("DOGE/USDT", 1, 10)
    assert not check.is_allowed
    assert check.reason == "SYMBOL_NOT_WHITELISTED"

    # too large size
    check = await executor.validate_trade_allowed("BTC/USDT", 10, 10000)
    assert not check.is_allowed
    assert check.reason == "POSITION_SIZE_EXCEEDS_LIMIT"

    # simulate daily loss breach
    executor.daily_realized_pnl = -MAX_DAILY_LOSS - 1
    check = await executor.validate_trade_allowed("BTC/USDT", 0.001, 100)
    assert not check.is_allowed
    assert check.reason == "DAILY_LOSS_LIMIT_EXCEEDED"

    # concurrency limit
    executor.daily_realized_pnl = 0.0
    executor.open_positions = {"o1": {}, "o2": {}}
    check = await executor.validate_trade_allowed("BTC/USDT", 0.001, 100)
    assert not check.is_allowed
    assert check.reason == "MAX_CONCURRENT_POSITIONS_REACHED"


@pytest.mark.asyncio
async def test_place_and_close_order_flow():
    executor = LiveExecutor()
    await executor.request_live_approval(user_confirmation=True)

    success, oid, details = await executor.place_order("BTC/USDT", "buy", 0.001, 10000)
    assert success
    assert oid.startswith("LIVE-")
    assert oid in executor.open_positions

    # closing with profit
    ok, closed = await executor.close_position(oid, 10500)
    assert ok
    assert closed["realized_pnl"] == pytest.approx((10500 - 10000) * 0.001)
    assert oid not in executor.open_positions
    assert len(executor.closed_positions) == 1

    # emergency close empty
    result = await executor.emergency_close_all()
    assert result["positions_closed"] == 0


@pytest.mark.asyncio
async def test_margin_safety_and_summary():
    executor = LiveExecutor()
    summary = await executor.get_summary()
    assert summary["account_balance"] == executor.account_balance_usd
    assert summary["approval_status"] == executor.approval_status.value

    status = await executor.check_margin_safety(95.0)
    assert status["safe"] is False
    assert status["action_taken"] == "EMERGENCY_CLOSE_ALL"

    status2 = await executor.check_margin_safety(85.0)
    assert "Liquidation" in status2["alerts"][0]

    status3 = await executor.check_margin_safety(55.0)
    # the low-threshold alert uses a generic exceeds message
    assert any("margin utilization exceeds" in a.lower() for a in status3["alerts"])


@pytest.mark.asyncio
async def test_daily_loss_limit_affects_place_order():
    executor = LiveExecutor()
    await executor.request_live_approval(user_confirmation=True)
    # simulate prior loss
    executor.daily_realized_pnl = -MAX_DAILY_LOSS - 10
    ok, oid, details = await executor.place_order("BTC/USDT", "buy", 0.001, 100)
    assert ok is False
    assert details.get("daily_loss", 0) > MAX_DAILY_LOSS
