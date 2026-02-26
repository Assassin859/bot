"""Risk monitoring system: Continuous surveillance of trading risks.

This module provides a RiskMonitor that:
- Monitors margin utilization
- Tracks drawdown and daily losses
- Enforces position limits
- Generates risk alerts
- Triggers automated safety actions
"""

from __future__ import annotations

import threading
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from logging_utils import log_event


class AlertLevel(Enum):
    """Risk alert level"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class RiskAlert:
    """A single risk alert"""
    timestamp: datetime
    level: AlertLevel
    category: str
    message: str
    details: Dict

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "category": self.category,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class RiskMetrics:
    """Complete risk metrics snapshot"""
    margin_utilization_pct: float = 0.0
    liquidation_risk_pct: float = 0.0
    daily_drawdown_pct: float = 0.0
    open_positions: int = 0
    max_open_positions: int = 2
    daily_loss: float = 0.0
    max_daily_loss: float = 25.0
    weekly_loss: float = 0.0
    max_weekly_loss: float = 100.0
    account_equity: float = 0.0
    account_balance: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


class RiskMonitor:
    """Continuous risk monitoring and alerting"""

    def __init__(self):
        """Initialize risk monitor"""
        self.alerts: List[RiskAlert] = []
        self.metrics_history: List[RiskMetrics] = []
        self._lock = threading.Lock()

    async def check_margin_utilization(
        self,
        current_utilization_pct: float,
        auto_close_threshold_pct: float = 90.0,
    ) -> Dict:
        """
        Check margin utilization and generate alerts.

        Args:
            current_utilization_pct: Current margin utilization percentage
            auto_close_threshold_pct: Threshold for auto-close action

        Returns:
            Dict with check results and recommended actions
        """
        with self._lock:
            result = {
                "safe": True,
                "alerts": [],
                "action": None,
            }

            # Critical: Auto-close all positions
            if current_utilization_pct > auto_close_threshold_pct:
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.CRITICAL,
                    category="MARGIN",
                    message=f"🚨 LIQUIDATION IMMINENT: {current_utilization_pct:.1f}% margin used",
                    details={"utilization": current_utilization_pct},
                )
                self.alerts.append(alert)
                result["safe"] = False
                result["alerts"].append(alert.to_dict())
                result["action"] = "EMERGENCY_CLOSE_ALL_POSITIONS"
                return result

            # Warning: Liquidation danger zone
            if current_utilization_pct > 80.0:
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.CRITICAL,
                    category="MARGIN",
                    message=f"⚠️ LIQUIDATION DANGER ZONE: {current_utilization_pct:.1f}% margin used",
                    details={"utilization": current_utilization_pct},
                )
                self.alerts.append(alert)
                result["alerts"].append(alert.to_dict())
                result["action"] = "REDUCE_POSITIONS"

            # Warning: High margin utilization
            if current_utilization_pct > 50.0:
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.WARNING,
                    category="MARGIN",
                    message=f"⚠️ High margin utilization: {current_utilization_pct:.1f}%",
                    details={"utilization": current_utilization_pct},
                )
                self.alerts.append(alert)
                result["alerts"].append(alert.to_dict())

            return result

    async def check_daily_loss_limit(
        self,
        daily_loss: float,
        max_daily_loss: float = 25.0,
    ) -> Dict:
        """
        Check if daily loss limit exceeded.

        Args:
            daily_loss: Current daily loss (positive number)
            max_daily_loss: Maximum allowed daily loss

        Returns:
            Dict with check results
        """
        with self._lock:
            result = {
                "safe": True,
                "alerts": [],
                "action": None,
            }

            if daily_loss > max_daily_loss:
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.CRITICAL,
                    category="DAILY_LOSS",
                    message=f"🚨 DAILY LOSS LIMIT EXCEEDED: ${daily_loss:.2f} > ${max_daily_loss:.2f}",
                    details={
                        "daily_loss": daily_loss,
                        "max_daily_loss": max_daily_loss,
                    },
                )
                self.alerts.append(alert)
                result["safe"] = False
                result["alerts"].append(alert.to_dict())
                result["action"] = "HALT_ALL_TRADING"
                return result

            if daily_loss > max_daily_loss * 0.75:  # 75% of limit
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.WARNING,
                    category="DAILY_LOSS",
                    message=f"⚠️ Approaching daily loss limit: ${daily_loss:.2f}",
                    details={
                        "daily_loss": daily_loss,
                        "max_daily_loss": max_daily_loss,
                        "progress": (daily_loss / max_daily_loss) * 100,
                    },
                )
                self.alerts.append(alert)
                result["alerts"].append(alert.to_dict())

            return result

    async def check_position_limits(
        self,
        open_positions: int,
        max_positions: int = 2,
    ) -> Dict:
        """
        Check position count limits.

        Args:
            open_positions: Current number of open positions
            max_positions: Maximum allowed positions

        Returns:
            Dict with check results
        """
        with self._lock:
            result = {
                "safe": True,
                "alerts": [],
                "action": None,
            }

            if open_positions > max_positions:
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.CRITICAL,
                    category="POSITION_LIMIT",
                    message=f"🚨 POSITION LIMIT EXCEEDED: {open_positions} > {max_positions}",
                    details={
                        "open_positions": open_positions,
                        "max_positions": max_positions,
                    },
                )
                self.alerts.append(alert)
                result["safe"] = False
                result["alerts"].append(alert.to_dict())
                result["action"] = "CLOSE_EXCESS_POSITIONS"
                return result

            if open_positions == max_positions:
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.INFO,
                    category="POSITION_LIMIT",
                    message=f"ℹ️ Max positions reached: {open_positions}/{max_positions}",
                    details={
                        "open_positions": open_positions,
                        "max_positions": max_positions,
                    },
                )
                self.alerts.append(alert)
                result["alerts"].append(alert.to_dict())

            return result

    async def calculate_max_drawdown(self, equity_history: List[float]) -> Dict:
        """
        Calculate maximum drawdown from equity history.

        Args:
            equity_history: List of equity values over time

        Returns:
            Dict with drawdown metrics
        """
        with self._lock:
            if not equity_history or len(equity_history) < 2:
                return {
                    "max_drawdown_pct": 0.0,
                    "current_drawdown_pct": 0.0,
                }

            peak = equity_history[0]
            max_dd = 0.0
            max_dd_pct = 0.0

            for equity in equity_history:
                if equity > peak:
                    peak = equity
                dd = peak - equity
                dd_pct = (dd / peak * 100) if peak > 0 else 0.0

                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = dd_pct

            current_dd = peak - equity_history[-1]
            current_dd_pct = (current_dd / peak * 100) if peak > 0 else 0.0

            result = {
                "max_drawdown": max_dd,
                "max_drawdown_pct": max_dd_pct,
                "current_drawdown": current_dd,
                "current_drawdown_pct": current_dd_pct,
                "peak_equity": peak,
            }

            if max_dd_pct > 20.0:
                alert = RiskAlert(
                    timestamp=datetime.utcnow(),
                    level=AlertLevel.WARNING,
                    category="DRAWDOWN",
                    message=f"⚠️ Large drawdown: {max_dd_pct:.1f}%",
                    details=result,
                )
                self.alerts.append(alert)

            return result

    async def generate_risk_report(
        self,
        account_balance: float,
        account_equity: float,
        margin_utilization: float,
        daily_loss: float,
        max_daily_loss: float,
        open_positions: int,
        equity_history: List[float],
    ) -> Dict:
        """
        Generate comprehensive risk report.

        Args:
            account_balance: Current account balance
            account_equity: Current equity
            margin_utilization: Margin utilization percentage
            daily_loss: Current daily loss
            max_daily_loss: Max daily loss limit
            open_positions: Count of open positions
            equity_history: Historical equity values

        Returns:
            Comprehensive risk report
        """
        # Check all risk metrics
        margin_check = await self.check_margin_utilization(margin_utilization)
        daily_loss_check = await self.check_daily_loss_limit(daily_loss, max_daily_loss)
        position_check = await self.check_position_limits(open_positions)
        drawdown_metrics = await self.calculate_max_drawdown(equity_history)

        # Determine overall safety
        overall_safe = (
            margin_check["safe"]
            and daily_loss_check["safe"]
            and position_check["safe"]
        )

        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_safe": overall_safe,
            "account_balance": account_balance,
            "account_equity": account_equity,
            "metrics": {
                "margin_utilization": margin_utilization,
                "daily_loss": daily_loss,
                "daily_loss_limit": max_daily_loss,
                "open_positions": open_positions,
            },
            "checks": {
                "margin": margin_check,
                "daily_loss": daily_loss_check,
                "positions": position_check,
                "drawdown": drawdown_metrics,
            },
            "alerts": self.alerts[-10:],  # Last 10 alerts
        }

        log_event("INFO", {
            "msg": "Risk report generated",
            "overall_safe": overall_safe,
            "margin_utilization": margin_utilization,
            "daily_loss": daily_loss,
        })

        return report

    async def get_recent_alerts(self, limit: int = 20) -> List[Dict]:
        """Get recent risk alerts"""
        with self._lock:
            return [alert.to_dict() for alert in self.alerts[-limit:]]

    async def clear_alerts(self):
        """Clear alert history"""
        with self._lock:
            self.alerts.clear()

            log_event("INFO", {
                "msg": "Risk alerts cleared",
            })
