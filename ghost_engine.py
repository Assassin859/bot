"""Ghost mode engine: Generate trading signals without executing orders.

This module provides a GhostEngine that:
- Generates buy/sell signals based on market conditions
- Tracks hypothetical trades without execution
- Calculates signal accuracy and quality metrics
- Measures what profits/losses WOULD have been if signals were executed
"""

from __future__ import annotations

import asyncio
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

from logging_utils import log_event


class SignalType(Enum):
    """Signal type enum"""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    """Represents a trading signal"""
    signal_id: str
    timestamp: datetime
    signal_type: SignalType
    symbol: str
    price: float
    confidence: float  # 0.0 to 1.0
    reasoning: str

    # Hypothetical execution tracking
    executed_price: Optional[float] = None
    executed_at: Optional[datetime] = None
    close_price: Optional[float] = None
    close_at: Optional[datetime] = None
    hypothetical_pnl: float = 0.0
    is_profitable: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type.value,
            "symbol": self.symbol,
            "price": self.price,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "executed_price": self.executed_price,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "close_price": self.close_price,
            "close_at": self.close_at.isoformat() if self.close_at else None,
            "hypothetical_pnl": self.hypothetical_pnl,
            "is_profitable": self.is_profitable,
        }


@dataclass
class SignalMetrics:
    """Metrics for signal quality"""
    total_signals: int = 0
    profitable_signals: int = 0
    unprofitable_signals: int = 0
    accuracy_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "total_signals": self.total_signals,
            "profitable_signals": self.profitable_signals,
            "unprofitable_signals": self.unprofitable_signals,
            "accuracy_rate": self.accuracy_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
        }


class GhostEngine:
    """Generate trading signals without executing orders"""

    def __init__(self):
        """Initialize ghost engine"""
        self.signals: List[Signal] = []
        self.closed_signals: List[Signal] = []
        self._lock = asyncio.Lock()

    async def generate_signal(
        self,
        symbol: str,
        signal_type: str,
        price: float,
        confidence: float = 0.5,
        reasoning: str = "",
    ) -> Tuple[bool, str]:
        """
        Generate a trading signal.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            signal_type: "buy" or "sell"
            price: Signal price
            confidence: Confidence level (0.0-1.0)
            reasoning: Explanation of the signal

        Returns:
            (success: bool, signal_id: str)
        """
        async with self._lock:
            # Validate signal
            if signal_type not in ("buy", "sell"):
                return False, "INVALID_SIGNAL_TYPE"

            if confidence < 0.0 or confidence > 1.0:
                return False, "INVALID_CONFIDENCE"

            # Create signal
            signal_id = str(uuid.uuid4())[:12]
            signal = Signal(
                signal_id=signal_id,
                timestamp=datetime.utcnow(),
                signal_type=SignalType(signal_type),
                symbol=symbol,
                price=price,
                confidence=confidence,
                reasoning=reasoning,
            )

            # Store signal
            self.signals.append(signal)

            log_event("INFO", {
                "msg": "Ghost signal generated",
                "signal_id": signal_id,
                "symbol": symbol,
                "type": signal_type,
                "price": price,
                "confidence": confidence,
            })

            return True, signal_id

    async def trace_signal(
        self,
        signal_id: str,
        close_price: float,
    ) -> Tuple[bool, Dict]:
        """
        Trace the outcome of a signal (close the hypothetical position).

        Args:
            signal_id: Signal ID to close
            close_price: Exit price

        Returns:
            (success: bool, signal_details: Dict)
        """
        async with self._lock:
            # Find signal
            signal = None
            for sig in self.signals:
                if sig.signal_id == signal_id:
                    signal = sig
                    break

            if not signal:
                return False, {"error": "Signal not found"}

            # Trace hypothetical execution
            if signal.signal_type == SignalType.BUY:
                pnl = close_price - signal.price
                is_profitable = pnl > 0
            else:  # SELL
                pnl = signal.price - close_price
                is_profitable = pnl > 0

            # Update signal
            signal.close_price = close_price
            signal.close_at = datetime.utcnow()
            signal.hypothetical_pnl = pnl
            signal.is_profitable = is_profitable

            # Move to closed signals
            self.signals.remove(signal)
            self.closed_signals.append(signal)

            details = {
                "signal_id": signal_id,
                "symbol": signal.symbol,
                "type": signal.signal_type.value,
                "entry_price": signal.price,
                "close_price": close_price,
                "hypothetical_pnl": pnl,
                "is_profitable": is_profitable,
            }

            log_event("INFO", {
                "msg": "Ghost signal traced",
                **details,
            })

            return True, details

    async def get_active_signals(self) -> List[Dict]:
        """Get all active (untested) signals"""
        async with self._lock:
            return [signal.to_dict() for signal in self.signals]

    async def get_signal_history(self, limit: int = 50) -> List[Dict]:
        """
        Get recently traced (closed) signals.

        Args:
            limit: Maximum number of signals to return

        Returns:
            List of closed signal dictionaries (most recent first)
        """
        async with self._lock:
            return [
                signal.to_dict()
                for signal in sorted(
                    self.closed_signals,
                    key=lambda s: s.close_at or datetime.utcnow(),
                    reverse=True,
                )[:limit]
            ]

    async def calculate_metrics(self) -> SignalMetrics:
        """
        Calculate comprehensive signal quality metrics.

        Returns:
            SignalMetrics with all calculated values
        """
        async with self._lock:
            if not self.closed_signals:
                return SignalMetrics()

            total = len(self.closed_signals)
            profitable = sum(
                1 for s in self.closed_signals if s.is_profitable and s.hypothetical_pnl > 0
            )
            unprofitable = sum(
                1 for s in self.closed_signals if not s.is_profitable
            )

            # Calculate accuracy
            accuracy_rate = (profitable / total * 100) if total > 0 else 0.0

            # Calculate wins and losses
            wins = [s.hypothetical_pnl for s in self.closed_signals if s.hypothetical_pnl > 0]
            losses = [
                s.hypothetical_pnl for s in self.closed_signals if s.hypothetical_pnl < 0
            ]

            avg_win = sum(wins) / len(wins) if wins else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0

            # Calculate profit factor
            total_wins = sum(wins)
            total_losses = abs(sum(losses)) if losses else 0.0
            profit_factor = (
                (total_wins / total_losses) if total_losses > 0 else float("inf")
            )
            if total_wins == 0:
                profit_factor = 0.0

            # Calculate expectancy
            expectancy = ((profitable * avg_win) + (unprofitable * avg_loss)) / total if total > 0 else 0.0

            # Calculate max drawdown
            cumulative_pnl = 0.0
            peak = 0.0
            max_dd = 0.0
            for signal in self.closed_signals:
                cumulative_pnl += signal.hypothetical_pnl
                if cumulative_pnl > peak:
                    peak = cumulative_pnl
                dd = peak - cumulative_pnl
                if dd > max_dd:
                    max_dd = dd

            # Sharpe ratio (simplified: mean / std dev of returns)
            # For now, use a simplified calculation
            pnls = [s.hypothetical_pnl for s in self.closed_signals]
            if pnls:
                mean_pnl = sum(pnls) / len(pnls)
                variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
                std_dev = variance ** 0.5
                sharpe_ratio = mean_pnl / std_dev if std_dev > 0 else 0.0
            else:
                sharpe_ratio = 0.0

            metrics = SignalMetrics(
                total_signals=total,
                profitable_signals=profitable,
                unprofitable_signals=unprofitable,
                accuracy_rate=accuracy_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                profit_factor=profit_factor,
                expectancy=expectancy,
                max_drawdown=max_dd,
                sharpe_ratio=sharpe_ratio,
            )

            return metrics

    async def get_accuracy_rate(self) -> float:
        """Calculate percentage of profitable signals"""
        async with self._lock:
            if not self.closed_signals:
                return 0.0
            profitable = sum(1 for s in self.closed_signals if s.is_profitable)
            return (profitable / len(self.closed_signals)) * 100

    async def get_total_pnl(self) -> float:
        """Get cumulative P&L from all signals"""
        async with self._lock:
            return sum(s.hypothetical_pnl for s in self.closed_signals)

    async def get_win_rate(self) -> float:
        """Get win rate (alias for accuracy)"""
        return await self.get_accuracy_rate()

    async def reset_signals(self):
        """Reset signal history (for testing)"""
        async with self._lock:
            self.signals.clear()
            self.closed_signals.clear()

            log_event("INFO", {
                "msg": "Ghost engine signals reset",
            })
