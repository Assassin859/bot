"""Paper trading executor: Simulate trades without real money.

This module provides a PaperExecutor that:
- Simulates order placement
- Tracks a simulated portfolio (starting capital, P&L, positions)
- Manages open orders and positions
- Calculates realized and unrealized P&L
- Logs all trades
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import uuid

from logging_utils import log_event


class OrderSide(Enum):
    """Order side enum"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status enum"""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    CLOSED = "closed"


@dataclass
class Order:
    """Represents a single paper trade order"""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_at: Optional[datetime] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for Redis storage"""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "exit_price": self.exit_price,
            "exit_at": self.exit_at.isoformat() if self.exit_at else None,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
        }


@dataclass
class PortfolioSnapshot:
    """Portfolio state at a point in time"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    starting_capital: float = 10000.0
    current_value: float = 10000.0
    cash_balance: float = 10000.0
    invested_value: float = 0.0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    open_positions_count: int = 0
    closed_trades_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


class PaperExecutor:
    """Simulate paper trades without real money"""

    def __init__(
        self,
        starting_capital: float = 10000.0,
    ):
        """
        Initialize paper executor with simulated portfolio.

        Args:
            starting_capital: Starting capital for paper trading ($10,000 default)
        """
        self.starting_capital = starting_capital
        self.cash_balance = starting_capital
        self.orders: Dict[str, Order] = {}
        self.closed_orders: List[Order] = []
        self._lock = asyncio.Lock()

    async def close(self):
        """Cleanup resources"""
        log_event("INFO", {
            "msg": "Paper executor closed",
        })

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Tuple[bool, str]:
        """
        Place a simulated order.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            side: "buy" or "sell"
            quantity: Order quantity
            price: Order price

        Returns:
            (success: bool, order_id: str)
        """
        async with self._lock:
            # Validate order
            order_side = OrderSide(side)
            order_value = quantity * price

            if order_side == OrderSide.BUY:
                if self.cash_balance < order_value:
                    log_event("WARNING", {
                        "msg": "Insufficient cash for order",
                        "required": order_value,
                        "available": self.cash_balance,
                    })
                    return False, "INSUFFICIENT_CASH"

            # Create order
            order_id = str(uuid.uuid4())[:12]
            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=order_side,
                quantity=quantity,
                entry_price=price,
                status=OrderStatus.FILLED,  # Immediately filled in paper
                filled_at=datetime.utcnow(),
            )

            # Update cash balance
            if order_side == OrderSide.BUY:
                self.cash_balance -= order_value
            else:
                self.cash_balance += order_value

            # Store order
            self.orders[order_id] = order

            log_event("INFO", {
                "msg": "Paper order placed",
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
            })

            return True, order_id

    async def close_position(
        self,
        order_id: str,
        exit_price: float,
    ) -> Tuple[bool, Dict]:
        """
        Close an open position.

        Args:
            order_id: Order ID to close
            exit_price: Exit price

        Returns:
            (success: bool, trade_details: Dict)
        """
        async with self._lock:
            if order_id not in self.orders:
                return False, {"error": "Order not found"}

            order = self.orders[order_id]

            if order.status == OrderStatus.CLOSED:
                return False, {"error": "Order already closed"}

            # Calculate P&L
            if order.side == OrderSide.BUY:
                pnl = (exit_price - order.entry_price) * order.quantity
            else:
                pnl = (order.entry_price - exit_price) * order.quantity

            # Update order
            order.exit_price = exit_price
            order.exit_at = datetime.utcnow()
            order.realized_pnl = pnl
            order.status = OrderStatus.CLOSED

            # Update cash balance (reverse the entry)
            exit_value = order.quantity * exit_price
            if order.side == OrderSide.BUY:
                self.cash_balance += exit_value
            else:
                self.cash_balance -= exit_value

            # Move to closed orders
            del self.orders[order_id]
            self.closed_orders.append(order)

            trade_details = {
                "order_id": order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "entry_price": order.entry_price,
                "exit_price": exit_price,
                "quantity": order.quantity,
                "realized_pnl": pnl,
                "duration_seconds": (
                    order.exit_at - order.created_at
                ).total_seconds(),
            }

            log_event("INFO", {
                "msg": "Paper position closed",
                **trade_details,
            })

            return True, trade_details

    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
        async with self._lock:
            return [order.to_dict() for order in self.orders.values()]

    async def get_portfolio_summary(self) -> PortfolioSnapshot:
        """
        Get current portfolio snapshot.

        Returns:
            PortfolioSnapshot with all metrics
        """
        async with self._lock:
            # Calculate open position values
            invested_value = 0.0
            unrealized_pnl = 0.0

            for order in self.orders.values():
                position_value = order.quantity * order.entry_price
                invested_value += position_value

                # Unrealized P&L (mock: use entry price as current)
                # In live: would fetch current market price
                unrealized_pnl += 0.0  # Placeholder

            # Calculate realized P&L from closed trades
            realized_pnl = sum(o.realized_pnl for o in self.closed_orders)

            # Calculate win rate
            wins = sum(1 for o in self.closed_orders if o.realized_pnl > 0)
            losses = sum(1 for o in self.closed_orders if o.realized_pnl < 0)
            total_trades = len(self.closed_orders)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

            current_value = self.cash_balance + invested_value + realized_pnl
            total_pnl = realized_pnl + unrealized_pnl

            snapshot = PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                starting_capital=self.starting_capital,
                current_value=current_value,
                cash_balance=self.cash_balance,
                invested_value=invested_value,
                total_pnl=total_pnl,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                open_positions_count=len(self.orders),
                closed_trades_count=total_trades,
                win_count=wins,
                loss_count=losses,
                win_rate=win_rate,
            )

            return snapshot

    async def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """
        Get recently closed trades.

        Args:
            limit: Maximum number of trades to return

        Returns:
            List of closed trade dictionaries (most recent first)
        """
        async with self._lock:
            return [
                order.to_dict()
                for order in sorted(
                    self.closed_orders,
                    key=lambda o: o.exit_at or datetime.utcnow(),
                    reverse=True,
                )[:limit]
            ]

    async def calculate_win_rate(self) -> float:
        """Calculate win rate percentage"""
        async with self._lock:
            if not self.closed_orders:
                return 0.0
            wins = sum(1 for o in self.closed_orders if o.realized_pnl > 0)
            return (wins / len(self.closed_orders)) * 100

    async def calculate_avg_win(self) -> float:
        """Calculate average profit per winning trade"""
        async with self._lock:
            wins = [o.realized_pnl for o in self.closed_orders if o.realized_pnl > 0]
            return sum(wins) / len(wins) if wins else 0.0

    async def calculate_avg_loss(self) -> float:
        """Calculate average loss per losing trade"""
        async with self._lock:
            losses = [o.realized_pnl for o in self.closed_orders if o.realized_pnl < 0]
            return sum(losses) / len(losses) if losses else 0.0

    async def calculate_profit_factor(self) -> float:
        """Calculate profit factor (total wins / total losses)"""
        async with self._lock:
            total_wins = sum(
                o.realized_pnl for o in self.closed_orders if o.realized_pnl > 0
            )
            total_losses = abs(
                sum(
                    o.realized_pnl for o in self.closed_orders if o.realized_pnl < 0
                )
            )
            if total_losses == 0:
                return float("inf") if total_wins > 0 else 0.0
            return total_wins / total_losses

    async def get_daily_pnl(self) -> float:
        """Get P&L for today's trades"""
        async with self._lock:
            today = datetime.utcnow().date()
            today_trades = [
                o.realized_pnl
                for o in self.closed_orders
                if o.exit_at and o.exit_at.date() == today
            ]
            return sum(today_trades)

    async def reset_portfolio(self):
        """Reset portfolio to starting state (for testing)"""
        async with self._lock:
            self.cash_balance = self.starting_capital
            self.orders.clear()
            self.closed_orders.clear()

            log_event("INFO", {
                "msg": "Paper executor portfolio reset",
            })
