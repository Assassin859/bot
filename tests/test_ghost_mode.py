"""Ghost mode engine tests - Generate signals without execution"""

import pytest
import asyncio
from datetime import datetime

from ghost_engine import GhostEngine, Signal, SignalType, SignalMetrics


@pytest.mark.asyncio
async def test_ghost_engine_initializes():
    """Verify ghost engine initializes correctly"""
    engine = GhostEngine()

    assert len(engine.signals) == 0
    assert len(engine.closed_signals) == 0


@pytest.mark.asyncio
async def test_ghost_generate_buy_signal():
    """Verify buy signal generated"""
    engine = GhostEngine()

    success, signal_id = await engine.generate_signal(
        symbol="BTC/USDT",
        signal_type="buy",
        price=45000.0,
        confidence=0.8,
        reasoning="Price broke above resistance",
    )

    assert success is True
    assert signal_id != ""
    assert len(engine.signals) == 1

    signal = engine.signals[0]
    assert signal.symbol == "BTC/USDT"
    assert signal.signal_type == SignalType.BUY
    assert signal.price == 45000.0
    assert signal.confidence == 0.8


@pytest.mark.asyncio
async def test_ghost_generate_sell_signal():
    """Verify sell signal generated"""
    engine = GhostEngine()

    success, signal_id = await engine.generate_signal(
        symbol="ETH/USDT",
        signal_type="sell",
        price=2800.0,
        confidence=0.6,
    )

    assert success is True
    assert len(engine.signals) == 1
    assert engine.signals[0].signal_type == SignalType.SELL


@pytest.mark.asyncio
async def test_ghost_invalid_signal_type_rejected():
    """Verify invalid signal type rejected"""
    engine = GhostEngine()

    success, signal_id = await engine.generate_signal(
        symbol="BTC/USDT",
        signal_type="invalid",
        price=45000.0,
    )

    assert success is False
    assert signal_id == "INVALID_SIGNAL_TYPE"
    assert len(engine.signals) == 0


@pytest.mark.asyncio
async def test_ghost_invalid_confidence_rejected():
    """Verify invalid confidence rejected"""
    engine = GhostEngine()

    success, signal_id = await engine.generate_signal(
        symbol="BTC/USDT",
        signal_type="buy",
        price=45000.0,
        confidence=1.5,  # Invalid: > 1.0
    )

    assert success is False
    assert signal_id == "INVALID_CONFIDENCE"


@pytest.mark.asyncio
async def test_ghost_trace_buy_signal_profitable():
    """Verify buy signal traced and marked profitable"""
    engine = GhostEngine()

    # Generate signal at $45,000
    _, signal_id = await engine.generate_signal(
        symbol="BTC/USDT",
        signal_type="buy",
        price=45000.0,
    )

    # Trace signal at higher price (profitable)
    success, details = await engine.trace_signal(
        signal_id=signal_id,
        close_price=45500.0,
    )

    assert success is True
    assert details["hypothetical_pnl"] == pytest.approx(500.0)
    assert details["is_profitable"] is True
    assert len(engine.signals) == 0
    assert len(engine.closed_signals) == 1


@pytest.mark.asyncio
async def test_ghost_trace_buy_signal_unprofitable():
    """Verify buy signal traced and marked unprofitable"""
    engine = GhostEngine()

    # Generate signal at $45,000
    _, signal_id = await engine.generate_signal(
        symbol="BTC/USDT",
        signal_type="buy",
        price=45000.0,
    )

    # Trace signal at lower price (unprofitable)
    success, details = await engine.trace_signal(
        signal_id=signal_id,
        close_price=44500.0,
    )

    assert success is True
    assert details["hypothetical_pnl"] == pytest.approx(-500.0)
    assert details["is_profitable"] is False


@pytest.mark.asyncio
async def test_ghost_trace_sell_signal_profitable():
    """Verify sell signal traced and marked profitable"""
    engine = GhostEngine()

    # Generate sell signal at $2800
    _, signal_id = await engine.generate_signal(
        symbol="ETH/USDT",
        signal_type="sell",
        price=2800.0,
    )

    # Trace signal at lower price (profitable for short)
    success, details = await engine.trace_signal(
        signal_id=signal_id,
        close_price=2700.0,
    )

    assert success is True
    assert details["hypothetical_pnl"] == pytest.approx(100.0)
    assert details["is_profitable"] is True


@pytest.mark.asyncio
async def test_ghost_accuracy_rate_calculation():
    """Verify accuracy rate calculated correctly"""
    engine = GhostEngine()

    # Generate 3 signals
    _, sid1 = await engine.generate_signal("BTC/USDT", "buy", 40000.0)
    _, sid2 = await engine.generate_signal("BTC/USDT", "buy", 41000.0)
    _, sid3 = await engine.generate_signal("BTC/USDT", "buy", 42000.0)

    # Trace: 2 profitable, 1 unprofitable
    await engine.trace_signal(sid1, 41000.0)  # +1000 (profitable)
    await engine.trace_signal(sid2, 40500.0)  # -500 (unprofitable)
    await engine.trace_signal(sid3, 43000.0)  # +1000 (profitable)

    accuracy = await engine.get_accuracy_rate()
    assert accuracy == pytest.approx(66.67, abs=0.1)  # 2 out of 3


@pytest.mark.asyncio
async def test_ghost_metrics_calculation():
    """Verify comprehensive signal metrics calculated"""
    engine = GhostEngine()

    # Generate and trace 5 signals
    for i in range(5):
        _, signal_id = await engine.generate_signal(
            "BTC/USDT",
            "buy",
            40000.0 + i * 1000,
        )
        # Alternate profitable/unprofitable
        close_price = (40000.0 + i * 1000 + 500) if i % 2 == 0 else (40000.0 + i * 1000 - 500)
        await engine.trace_signal(signal_id, close_price)

    metrics = await engine.calculate_metrics()

    assert metrics.total_signals == 5
    assert metrics.profitable_signals == 3  # Indices 0, 2, 4
    assert metrics.unprofitable_signals == 2  # Indices 1, 3
    assert metrics.accuracy_rate == pytest.approx(60.0)  # 3/5 = 60%
    assert metrics.avg_win == pytest.approx(500.0)
    assert metrics.avg_loss == pytest.approx(-500.0)


@pytest.mark.asyncio
async def test_ghost_total_pnl():
    """Verify cumulative P&L calculation"""
    engine = GhostEngine()

    # Win: +100
    _, sid1 = await engine.generate_signal("BTC/USDT", "buy", 100.0)
    await engine.trace_signal(sid1, 200.0)

    # Loss: -50
    _, sid2 = await engine.generate_signal("BTC/USDT", "buy", 100.0)
    await engine.trace_signal(sid2, 50.0)

    # Win: +200
    _, sid3 = await engine.generate_signal("BTC/USDT", "buy", 100.0)
    await engine.trace_signal(sid3, 300.0)

    total_pnl = await engine.get_total_pnl()
    assert total_pnl == pytest.approx(250.0)  # 100 - 50 + 200


@pytest.mark.asyncio
async def test_ghost_signal_history():
    """Verify signal history returns closed signals in order"""
    engine = GhostEngine()

    # Generate and trace 3 signals
    for i in range(3):
        _, signal_id = await engine.generate_signal("BTC/USDT", "buy", 40000.0 + i * 1000)
        await engine.trace_signal(signal_id, 41000.0 + i * 1000)
        await asyncio.sleep(0.01)

    history = await engine.get_signal_history(limit=5)

    assert len(history) == 3
    # Most recent first
    assert history[0]["close_price"] == pytest.approx(43000.0)
    assert history[2]["close_price"] == pytest.approx(41000.0)


@pytest.mark.asyncio
async def test_ghost_active_signals():
    """Verify active (untested) signals retrievable"""
    engine = GhostEngine()

    # Generate 3 signals without tracing
    for i in range(3):
        await engine.generate_signal("BTC/USDT", "buy", 40000.0 + i * 1000)

    active = await engine.get_active_signals()
    assert len(active) == 3

    # Trace one signal
    await engine.trace_signal(active[0]["signal_id"], 41000.0)

    # Should have 2 active now
    active2 = await engine.get_active_signals()
    assert len(active2) == 2


@pytest.mark.asyncio
async def test_ghost_profit_factor():
    """Verify profit factor calculation"""
    engine = GhostEngine()

    # Wins: 3 * 100 = 300
    for i in range(3):
        _, sid = await engine.generate_signal("BTC/USDT", "buy", 100.0)
        await engine.trace_signal(sid, 200.0)  # +100

    # Losses: 1 * 50 = 50
    _, sid = await engine.generate_signal("BTC/USDT", "buy", 100.0)
    await engine.trace_signal(sid, 50.0)  # -50

    metrics = await engine.calculate_metrics()
    # Profit factor = total wins / total losses = 300 / 50 = 6.0
    assert metrics.profit_factor == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_ghost_multiple_symbols():
    """Verify signals work with multiple symbols"""
    engine = GhostEngine()

    # Generate signals for different symbols
    _, bid = await engine.generate_signal("BTC/USDT", "buy", 45000.0)
    _, eid = await engine.generate_signal("ETH/USDT", "buy", 2800.0)
    _, aid = await engine.generate_signal("ADA/USDT", "buy", 0.50)

    assert len(engine.signals) == 3

    # Trace all signals
    await engine.trace_signal(bid, 46000.0)
    await engine.trace_signal(eid, 2900.0)
    await engine.trace_signal(aid, 0.55)

    history = await engine.get_signal_history()
    assert len(history) == 3
    symbols = {h["symbol"] for h in history}
    assert symbols == {"BTC/USDT", "ETH/USDT", "ADA/USDT"}


@pytest.mark.asyncio
async def test_ghost_engine_stability_24_hour():
    """Verify ghost engine stability over extended period"""
    engine = GhostEngine()

    # Simulate 200 signals
    signal_count = 0
    for i in range(200):
        _, signal_id = await engine.generate_signal(
            "BTC/USDT",
            "buy",
            40000.0 + (i % 10) * 1000,
            confidence=0.5 + (i % 50) / 100,
        )

        close_price = (40000.0 + (i % 10) * 1000 + 500) if i % 3 == 0 else (
            40000.0 + (i % 10) * 1000 - 500
        )
        await engine.trace_signal(signal_id, close_price)
        signal_count += 1

        if (i + 1) % 50 == 0:
            metrics = await engine.calculate_metrics()
            assert metrics.total_signals == signal_count
            assert metrics.accuracy_rate >= 0.0

    assert len(engine.closed_signals) == 200
    final_metrics = await engine.calculate_metrics()
    assert final_metrics.total_signals == 200


@pytest.mark.asyncio
async def test_ghost_reset_signals():
    """Verify signal history can be reset"""
    engine = GhostEngine()

    # Generate and trace some signals
    for i in range(5):
        _, signal_id = await engine.generate_signal("BTC/USDT", "buy", 40000.0)
        await engine.trace_signal(signal_id, 41000.0)

    assert len(engine.closed_signals) == 5

    # Reset
    await engine.reset_signals()

    assert len(engine.signals) == 0
    assert len(engine.closed_signals) == 0
    assert await engine.get_accuracy_rate() == 0.0
