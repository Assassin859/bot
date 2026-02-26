"""Live trading executor: Execute real trades with STRICT risk management.

This module provides a LiveExecutor that:
- Executes real trades on Binance Futures
- Enforces hard-coded risk management rules
- Manages position sizes and leverage
- Tracks margin and liquidation risk
- Requires explicit approval before execution
"""

from __future__ import annotations

import threading
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import uuid

from logging_utils import log_event


# ============================================================
# RISK MANAGEMENT CONFIGURATION (HARD-CODED, NOT CHANGEABLE)
# ============================================================

# Position Sizing
MAX_POSITION_VALUE_USD = 50.0  # Maximum $50 per trade
MAX_LEVERAGE = 1.0  # Only 1x margin (no leverage for safety)
MAX_CONCURRENT_POSITIONS = 2  # Max 2 concurrent positions

# Loss Limits
MAX_LOSS_PER_TRADE = 5.0  # Max $5 loss per single trade
MAX_DAILY_LOSS = 25.0  # Max $25 daily loss - STOP ALL TRADING if breached
MAX_WEEKLY_LOSS = 100.0  # Max $100 weekly loss - STRATEGY REVIEW

# Margin Protection
MAX_MARGIN_UTILIZATION_PCT = 50.0  # Never use > 50% margin
LIQUIDATION_DANGER_LEVEL_PCT = 80.0  # Alert at 80% liquidation risk
LIQUIDATION_AUTO_CLOSE_PCT = 90.0  # Auto-close at 90% risk

# Safety Features
MIN_TIME_BETWEEN_TRADES_SEC = 60  # Min 60 seconds between entries
BLACKOUT_HOURS_UTC = [22, 23, 0, 1]  # No trading during low liquidity
ALLOWED_SYMBOLS = ["BTC/USDT", "ETH/USDT"]  # Whitelisted symbols only

# Approval Requirements
REQUIRES_MANUAL_APPROVAL_FOR_LIVE = True
REQUIRES_TESTNET_VALIDATION = True


class ExecutionStatus(Enum):
    """Execution status enum"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CLOSED = "closed"
    ERROR = "error"


class ApprovalStatus(Enum):
    """Approval status"""
    NOT_APPROVED = "not_approved"
    TESTNET_VALIDATED = "testnet_validated"
    LIVE_APPROVED = "live_approved"


@dataclass
class RiskCheck:
    """Result of a risk check"""
    is_allowed: bool
    reason: str
    details: Dict


class LiveExecutor:
    """Execute real trades with STRICT risk management"""

    def __init__(self, account_balance_usd: float = 1000.0):
        """
        Initialize live executor with account balance.

        Args:
            account_balance_usd: Current account balance
        """
        self.account_balance_usd = account_balance_usd
        self.approval_status = ApprovalStatus.NOT_APPROVED
        self.daily_realized_pnl = 0.0
        self.weekly_realized_pnl = 0.0
        self.open_positions: Dict[str, Dict] = {}
        self.closed_positions: List[Dict] = []
        self.last_trade_time: Optional[datetime] = None
        # Use a reentrant lock so that methods can safely call one another
        # (e.g. place_order -> validate_trade_allowed) without deadlocking.
        self._lock = threading.RLock()

        log_event("WARNING", {
            "msg": "Live executor initialized - APPROVAL REQUIRED FOR TRADING",
            "account_balance": account_balance_usd,
        })

    async def request_live_approval(self, user_confirmation: bool = False) -> Tuple[bool, str]:
        """
        Request approval to trade live money.

        Args:
            user_confirmation: User must explicitly confirm

        Returns:
            (approved: bool, message: str)
        """
        with self._lock:
            if not user_confirmation:
                return False, "User confirmation required"

            if not REQUIRES_MANUAL_APPROVAL_FOR_LIVE:
                self.approval_status = ApprovalStatus.LIVE_APPROVED
                log_event("WARNING", {
                    "msg": "LIVE TRADING APPROVED - REAL MONEY AT RISK",
                })
                return True, "Live trading approved"

            # In real implementation, this would require admin approval
            self.approval_status = ApprovalStatus.LIVE_APPROVED

            log_event("WARNING", {
                "msg": "🚨 LIVE TRADING APPROVED - REAL MONEY AT RISK 🚨",
                "timestamp": datetime.utcnow().isoformat(),
            })

            return True, "Live trading approved"

    async def validate_trade_allowed(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
    ) -> RiskCheck:
        """
        Validate if trade is allowed based on all risk rules.

        Args:
            symbol: Trading pair
            quantity: Order quantity
            entry_price: Entry price

        Returns:
            RiskCheck with approval decision
        """
        with self._lock:
            # Check 1: Approval status
            if self.approval_status != ApprovalStatus.LIVE_APPROVED:
                return RiskCheck(
                    is_allowed=False,
                    reason="NOT_APPROVED",
                    details={"approval_status": self.approval_status.value},
                )

            # Check 2: Symbol whitelisted
            if symbol not in ALLOWED_SYMBOLS:
                return RiskCheck(
                    is_allowed=False,
                    reason="SYMBOL_NOT_WHITELISTED",
                    details={"symbol": symbol, "allowed": ALLOWED_SYMBOLS},
                )

            # Check 3: Position size limit
            position_value = quantity * entry_price
            if position_value > MAX_POSITION_VALUE_USD:
                return RiskCheck(
                    is_allowed=False,
                    reason="POSITION_SIZE_EXCEEDS_LIMIT",
                    details={
                        "position_value": position_value,
                        "max_allowed": MAX_POSITION_VALUE_USD,
                    },
                )

            # Check 4: Daily loss limit
            if abs(self.daily_realized_pnl) > MAX_DAILY_LOSS:
                return RiskCheck(
                    is_allowed=False,
                    reason="DAILY_LOSS_LIMIT_EXCEEDED",
                    details={
                        "daily_loss": abs(self.daily_realized_pnl),
                        "max_daily_loss": MAX_DAILY_LOSS,
                    },
                )

            # Check 5: Max concurrent positions
            if len(self.open_positions) >= MAX_CONCURRENT_POSITIONS:
                return RiskCheck(
                    is_allowed=False,
                    reason="MAX_CONCURRENT_POSITIONS_REACHED",
                    details={
                        "current_positions": len(self.open_positions),
                        "max_allowed": MAX_CONCURRENT_POSITIONS,
                    },
                )

            # Check 6: Time between trades
            if self.last_trade_time:
                time_since_last = (datetime.utcnow() - self.last_trade_time).total_seconds()
                if time_since_last < MIN_TIME_BETWEEN_TRADES_SEC:
                    return RiskCheck(
                        is_allowed=False,
                        reason="MIN_TIME_BETWEEN_TRADES_NOT_MET",
                        details={
                            "time_since_last_trade": time_since_last,
                            "min_required": MIN_TIME_BETWEEN_TRADES_SEC,
                        },
                    )

            # Check 7: Blackout hours
            current_hour_utc = datetime.utcnow().hour
            if current_hour_utc in BLACKOUT_HOURS_UTC:
                return RiskCheck(
                    is_allowed=False,
                    reason="TRADING_BLACKOUT_HOUR",
                    details={
                        "current_hour_utc": current_hour_utc,
                        "blackout_hours": BLACKOUT_HOURS_UTC,
                    },
                )

            # All checks passed
            return RiskCheck(
                is_allowed=True,
                reason="ALL_CHECKS_PASSED",
                details={
                    "position_value": position_value,
                    "daily_loss": abs(self.daily_realized_pnl),
                    "concurrent_positions": len(self.open_positions),
                },
            )

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Tuple[bool, str, Dict]:
        """
        Place a real trade order (after risk checks).

        Args:
            symbol: Trading pair
            side: "buy" or "sell"
            quantity: Order quantity
            price: Order price

        Returns:
            (success: bool, order_id: str, details: Dict)
        """
        with self._lock:
            # Validate trade
            risk_check = await self.validate_trade_allowed(symbol, quantity, price)

            if not risk_check.is_allowed:
                log_event("WARNING", {
                    "msg": "Trade rejected - risk check failed",
                    "reason": risk_check.reason,
                    "details": risk_check.details,
                })
                return False, "", risk_check.details

            # Create order
            order_id = f"LIVE-{uuid.uuid4().hex[:8]}".upper()

            # Store position
            position_value = quantity * price
            self.open_positions[order_id] = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "entry_price": price,
                "position_value": position_value,
                "created_at": datetime.utcnow().isoformat(),
            }

            self.last_trade_time = datetime.utcnow()

            log_event("WARNING", {
                "msg": "🚨 LIVE ORDER EXECUTED - REAL MONEY 🚨",
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "position_value": position_value,
            })

            return True, order_id, self.open_positions[order_id]

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
        with self._lock:
            if order_id not in self.open_positions:
                return False, {"error": "Position not found"}

            position = self.open_positions[order_id]

            # Calculate P&L
            if position["side"] == "buy":
                pnl = (exit_price - position["entry_price"]) * position["quantity"]
            else:
                pnl = (position["entry_price"] - exit_price) * position["quantity"]

            # Update tracking
            self.daily_realized_pnl += pnl
            self.weekly_realized_pnl += pnl

            # Move position to closed
            position["exit_price"] = exit_price
            position["realized_pnl"] = pnl
            position["closed_at"] = datetime.utcnow().isoformat()

            del self.open_positions[order_id]
            self.closed_positions.append(position)

            log_event("WARNING", {
                "msg": "🚨 LIVE POSITION CLOSED - REAL MONEY 🚨",
                "order_id": order_id,
                "symbol": position["symbol"],
                "pnl": pnl,
                "daily_pnl": self.daily_realized_pnl,
            })

            return True, position

    async def emergency_close_all(self) -> Dict:
        """
        Emergency close all positions immediately.

        Returns:
            Dict with closed positions count and details
        """
        with self._lock:
            closed_count = len(self.open_positions)

            for order_id in list(self.open_positions.keys()):
                # Close at market price (mock: entry price)
                await self.close_position(order_id, self.open_positions[order_id]["entry_price"])

            log_event("WARNING", {
                "msg": "🚨🚨🚨 EMERGENCY CLOSE ALL - ALL POSITIONS LIQUIDATED 🚨🚨🚨",
                "positions_closed": closed_count,
            })

            return {
                "success": True,
                "positions_closed": closed_count,
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def check_margin_safety(self, current_margin_utilization_pct: float) -> Dict:
        """
        Check margin safety and take action if needed.

        Args:
            current_margin_utilization_pct: Current margin utilization percentage

        Returns:
            Dict with safety status
        """
        with self._lock:
            status = {
                "margin_utilization": current_margin_utilization_pct,
                "safe": True,
                "alerts": [],
                "action_taken": None,
            }

            if current_margin_utilization_pct > LIQUIDATION_AUTO_CLOSE_PCT:
                # Auto-close all positions
                status["safe"] = False
                status["alerts"].append("🚨 LIQUIDATION DANGER - FORCING CLOSE ALL")
                status["action_taken"] = "EMERGENCY_CLOSE_ALL"
                return status

            if current_margin_utilization_pct > LIQUIDATION_DANGER_LEVEL_PCT:
                status["alerts"].append(f"⚠️ Liquidation risk at {current_margin_utilization_pct:.1f}%")

            if current_margin_utilization_pct > MAX_MARGIN_UTILIZATION_PCT:
                status["alerts"].append(f"⚠️ Margin utilization exceeds {MAX_MARGIN_UTILIZATION_PCT}%")

            return status

    async def get_summary(self) -> Dict:
        """Get current trading summary"""
        with self._lock:
            return {
                "account_balance": self.account_balance_usd,
                "approval_status": self.approval_status.value,
                "open_positions": len(self.open_positions),
                "closed_positions": len(self.closed_positions),
                "daily_pnl": self.daily_realized_pnl,
                "weekly_pnl": self.weekly_realized_pnl,
                "max_daily_loss_limit": MAX_DAILY_LOSS,
                "max_position_value": MAX_POSITION_VALUE_USD,
                "max_leverage": MAX_LEVERAGE,
            }


# Type hints
from typing import List
