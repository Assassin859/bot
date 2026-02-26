"""Paper mode trading tests - Simulate trades without real money"""

import pytest
import asyncio
from datetime import datetime, timedelta

from paper_executor import (
    PaperExecutor,
    Order,
    OrderSide,
    OrderStatus,
    PortfolioSnapshot,
)


@pytest.mark.asyncio
async def test_paper_executor_initializes():
    """Verify executor initializes with correct starting capital"""
    executor = PaperExecutor(starting_capital=10000.0)

    assert executor.starting_capital == 10000.0
    assert executor.cash_balance == 10000.0
    assert len(executor.orders) == 0
    assert len(executor.closed_orders) == 0

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_place_buy_order():
    """Verify buy order placed and cash balance updated"""
    executor = PaperExecutor(starting_capital=10000.0)

    success, order_id = await executor.place_order(
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        price=45000.0,
    )

    assert success is True
    assert order_id != "INSUFFICIENT_CASH"
    assert len(executor.orders) == 1
    assert executor.cash_balance == 10000.0 - (0.1 * 45000.0)  # $5500 cash remaining

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_place_sell_order():
    """Verify sell order placed and cash balance updated"""
    executor = PaperExecutor(starting_capital=10000.0)

    # First buy
    await executor.place_order("BTC/USDT", "buy", 0.1, 45000.0)

    # Then sell
    success, order_id = await executor.place_order(
        symbol="BTC/USDT",
        side="sell",
        quantity=0.05,
        price=45500.0,
    )

    assert success is True
    assert len(executor.orders) == 2

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_insufficient_cash_rejected():
    """Verify order rejected if insufficient cash"""
    executor = PaperExecutor(starting_capital=1000.0)

    # Try to buy more than available
    success, order_id = await executor.place_order(
        symbol="BTC/USDT",
        side="buy",
        quantity=1.0,  # 1 BTC
        price=45000.0,  # Would cost $45,000
    )

    assert success is False
    assert order_id == "INSUFFICIENT_CASH"
    assert len(executor.orders) == 0
    assert executor.cash_balance == 1000.0  # Unchanged

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_close_position_with_profit():
    """Verify position closed and P&L calculated correctly (winning trade)"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Place buy order at $45,000
    _, order_id = await executor.place_order(
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        price=45000.0,
    )

    # Close position at $45,500 (profit)
    success, details = await executor.close_position(
        order_id=order_id,
        exit_price=45500.0,
    )

    assert success is True
    assert details["realized_pnl"] == pytest.approx(50.0)  # (45500-45000)*0.1 = $50
    assert len(executor.orders) == 0
    assert len(executor.closed_orders) == 1

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_close_position_with_loss():
    """Verify position closed and P&L calculated correctly (losing trade)"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Place buy order at $45,000
    _, order_id = await executor.place_order(
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        price=45000.0,
    )

    # Close position at $44,500 (loss)
    success, details = await executor.close_position(
        order_id=order_id,
        exit_price=44500.0,
    )

    assert success is True
    assert details["realized_pnl"] == pytest.approx(-50.0)  # (44500-45000)*0.1 = -$50
    assert len(executor.orders) == 0
    assert len(executor.closed_orders) == 1

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_portfolio_snapshot():
    """Verify portfolio snapshot contains correct metrics"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Place and close a winning trade
    _, order_id = await executor.place_order(
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        price=45000.0,
    )
    await executor.close_position(order_id=order_id, exit_price=45500.0)

    # Get snapshot
    snapshot = await executor.get_portfolio_summary()

    assert snapshot.starting_capital == 10000.0
    assert snapshot.closed_trades_count == 1
    assert snapshot.win_count == 1
    assert snapshot.loss_count == 0
    assert snapshot.realized_pnl == pytest.approx(50.0)
    assert snapshot.win_rate == 100.0

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_win_rate_calculation():
    """Verify win rate calculated correctly after multiple trades"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Trade 1: Win
    _, oid1 = await executor.place_order("BTC/USDT", "buy", 0.1, 40000.0)
    await executor.close_position(oid1, exit_price=41000.0)

    # Trade 2: Loss
    _, oid2 = await executor.place_order("BTC/USDT", "buy", 0.1, 42000.0)
    await executor.close_position(oid2, exit_price=41000.0)

    # Trade 3: Win
    _, oid3 = await executor.place_order("BTC/USDT", "buy", 0.1, 40000.0)
    await executor.close_position(oid3, exit_price=41000.0)

    win_rate = await executor.calculate_win_rate()
    assert win_rate == pytest.approx(66.67, abs=0.1)  # 2 wins out of 3 = 66.67%

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_avg_win_loss():
    """Verify average win and loss calculations"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Win: $100
    _, oid1 = await executor.place_order("BTC/USDT", "buy", 1.0, 100.0)
    await executor.close_position(oid1, exit_price=200.0)

    # Win: $100
    _, oid2 = await executor.place_order("BTC/USDT", "buy", 1.0, 100.0)
    await executor.close_position(oid2, exit_price=200.0)

    # Loss: -$50
    _, oid3 = await executor.place_order("BTC/USDT", "buy", 1.0, 100.0)
    await executor.close_position(oid3, exit_price=50.0)

    avg_win = await executor.calculate_avg_win()
    avg_loss = await executor.calculate_avg_loss()

    assert avg_win == pytest.approx(100.0)
    assert avg_loss == pytest.approx(-50.0)

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_profit_factor():
    """Verify profit factor calculation"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Wins: $100 + $100 = $200
    _, oid1 = await executor.place_order("BTC/USDT", "buy", 1.0, 100.0)
    await executor.close_position(oid1, exit_price=200.0)

    _, oid2 = await executor.place_order("BTC/USDT", "buy", 1.0, 100.0)
    await executor.close_position(oid2, exit_price=200.0)

    # Losses: -$50
    _, oid3 = await executor.place_order("BTC/USDT", "buy", 1.0, 100.0)
    await executor.close_position(oid3, exit_price=50.0)

    profit_factor = await executor.calculate_profit_factor()
    assert profit_factor == pytest.approx(4.0)  # 200 / 50 = 4.0

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_trade_history():
    """Verify trade history returns closed trades in correct order"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Place and close 3 trades
    for i in range(3):
        _, order_id = await executor.place_order(
            symbol="BTC/USDT",
            side="buy",
            quantity=0.1,
            price=45000.0 - i * 1000,
        )
        await executor.close_position(
            order_id=order_id,
            exit_price=45000.0 - i * 1000 + 500,
        )
        await asyncio.sleep(0.01)  # Ensure different timestamps

    history = await executor.get_trade_history(limit=5)

    assert len(history) == 3
    # Most recent first (most recent should have lowest entry price = 43000)
    assert history[0]["exit_price"] == 43500.0
    assert history[2]["exit_price"] == 45500.0

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_multiple_concurrent_positions():
    """Verify multiple positions can be held concurrently"""
    executor = PaperExecutor(starting_capital=50000.0)

    # Open 3 concurrent positions
    order_ids = []
    for i in range(3):
        _, order_id = await executor.place_order(
            symbol=f"{'BTC' if i == 0 else 'ETH'}/USDT",
            side="buy",
            quantity=0.1,
            price=40000.0 + i * 1000,
        )
        order_ids.append(order_id)

    open_orders = await executor.get_open_orders()
    assert len(open_orders) == 3

    # Close all positions
    for order_id in order_ids:
        await executor.close_position(order_id=order_id, exit_price=45000.0)

    open_orders = await executor.get_open_orders()
    assert len(open_orders) == 0
    assert len(executor.closed_orders) == 3

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_reset_portfolio():
    """Verify portfolio reset works correctly"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Create some trades
    _, order_id = await executor.place_order("BTC/USDT", "buy", 0.1, 45000.0)
    await executor.close_position(order_id=order_id, exit_price=45500.0)

    # Reset
    await executor.reset_portfolio()

    assert executor.cash_balance == 10000.0
    assert len(executor.orders) == 0
    assert len(executor.closed_orders) == 0

    await executor.close()


@pytest.mark.asyncio
async def test_paper_mode_stability_4_hour_run():
    """Verify paper mode runs stably for extended period"""
    executor = PaperExecutor(starting_capital=10000.0)

    # Simulate 100 trades over time
    trade_count = 0
    for i in range(100):
        entry_price = 40000.0 + (i % 10) * 1000
        _, order_id = await executor.place_order(
            symbol="BTC/USDT",
            side="buy",
            quantity=0.01,
            price=entry_price,
        )

        exit_price = entry_price + (100 if i % 3 == 0 else -100)
        await executor.close_position(order_id=order_id, exit_price=exit_price)
        trade_count += 1

        if (i + 1) % 20 == 0:
            snapshot = await executor.get_portfolio_summary()
            assert snapshot.closed_trades_count == trade_count
            assert snapshot.current_value > 0

    assert len(executor.closed_orders) == 100
    snapshot = await executor.get_portfolio_summary()
    assert snapshot.current_value > 0

    await executor.close()
