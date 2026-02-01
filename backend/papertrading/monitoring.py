"""
Monitoring and Alerting for Paper Trading.

Provides:
1. Metrics collection
2. Health checks
3. Alerting
4. Daily reports
"""

import asyncio
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Callable
from enum import Enum

from pydantic import BaseModel


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("paper_trading")


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Alert(BaseModel):
    """An alert notification."""

    alert_id: str
    severity: AlertSeverity
    title: str
    message: str
    timestamp: str
    metadata: Dict[str, Any] = {}
    acknowledged: bool = False


class Metric(BaseModel):
    """A metric data point."""

    name: str
    value: float
    timestamp: str
    tags: Dict[str, str] = {}


class HealthStatus(BaseModel):
    """Health check status."""

    component: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: Optional[str] = None
    last_check: str


class SystemHealth(BaseModel):
    """Overall system health."""

    status: str
    components: List[HealthStatus]
    timestamp: str


class MetricsCollector:
    """Collects and stores metrics."""

    def __init__(self, max_points: int = 10000):
        """
        Initialize collector.

        Args:
            max_points: Maximum metric points to keep in memory
        """
        self.max_points = max_points
        self._metrics: List[Metric] = []

    def record(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> Metric:
        """
        Record a metric.

        Args:
            name: Metric name
            value: Metric value
            tags: Optional tags

        Returns:
            Recorded metric
        """
        metric = Metric(
            name=name,
            value=value,
            timestamp=datetime.utcnow().isoformat(),
            tags=tags or {},
        )
        self._metrics.append(metric)

        # Trim if needed
        if len(self._metrics) > self.max_points:
            self._metrics = self._metrics[-self.max_points:]

        logger.debug(f"Metric recorded: {name}={value}")
        return metric

    def get_metrics(
        self,
        name: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[Metric]:
        """
        Get metrics with optional filters.

        Args:
            name: Filter by metric name
            since: Filter by timestamp

        Returns:
            List of matching metrics
        """
        result = self._metrics

        if name:
            result = [m for m in result if m.name == name]

        if since:
            since_str = since.isoformat()
            result = [m for m in result if m.timestamp >= since_str]

        return result

    def get_latest(self, name: str) -> Optional[Metric]:
        """Get latest value for a metric."""
        metrics = self.get_metrics(name)
        return metrics[-1] if metrics else None


class AlertManager:
    """Manages alerts and notifications."""

    def __init__(
        self,
        notify_fn: Optional[Callable[[Alert], None]] = None,
    ):
        """
        Initialize alert manager.

        Args:
            notify_fn: Function to call when alert is raised
        """
        self.notify_fn = notify_fn or self._default_notify
        self._alerts: List[Alert] = []
        self._alert_counter = 0

    def _default_notify(self, alert: Alert) -> None:
        """Default notification: log the alert."""
        log_fn = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.critical,
        }[alert.severity]
        log_fn(f"ALERT [{alert.severity}]: {alert.title} - {alert.message}")

    def raise_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """
        Raise a new alert.

        Args:
            severity: Alert severity
            title: Alert title
            message: Alert message
            metadata: Additional metadata

        Returns:
            Created alert
        """
        self._alert_counter += 1
        alert = Alert(
            alert_id=f"alert_{self._alert_counter:06d}",
            severity=severity,
            title=title,
            message=message,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata or {},
        )
        self._alerts.append(alert)

        # Notify
        self.notify_fn(alert)

        return alert

    def get_active_alerts(self) -> List[Alert]:
        """Get all unacknowledged alerts."""
        return [a for a in self._alerts if not a.acknowledged]

    def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False


class HealthChecker:
    """Performs health checks on system components."""

    def __init__(self):
        """Initialize health checker."""
        self._checks: Dict[str, Callable] = {}

    def register_check(
        self,
        component: str,
        check_fn: Callable[[], bool],
    ) -> None:
        """
        Register a health check.

        Args:
            component: Component name
            check_fn: Function that returns True if healthy
        """
        self._checks[component] = check_fn

    async def check_all(self) -> SystemHealth:
        """
        Run all health checks.

        Returns:
            SystemHealth with all component statuses
        """
        statuses = []
        overall = "healthy"

        for component, check_fn in self._checks.items():
            try:
                is_healthy = check_fn()
                status = "healthy" if is_healthy else "unhealthy"
                message = None
            except Exception as e:
                status = "unhealthy"
                message = str(e)

            if status != "healthy":
                overall = "degraded"

            statuses.append(
                HealthStatus(
                    component=component,
                    status=status,
                    message=message,
                    last_check=datetime.utcnow().isoformat(),
                )
            )

        return SystemHealth(
            status=overall,
            components=statuses,
            timestamp=datetime.utcnow().isoformat(),
        )


class DailyReporter:
    """Generates daily paper trading reports."""

    def __init__(
        self,
        metrics: MetricsCollector,
        alerts: AlertManager,
    ):
        """
        Initialize reporter.

        Args:
            metrics: Metrics collector
            alerts: Alert manager
        """
        self.metrics = metrics
        self.alerts = alerts

    def generate_daily_report(
        self,
        report_date: date,
    ) -> Dict[str, Any]:
        """
        Generate daily report.

        Args:
            report_date: Date for the report

        Returns:
            Report data
        """
        start = datetime.combine(report_date, datetime.min.time())
        end = start + timedelta(days=1)

        # Get metrics for the day
        all_metrics = self.metrics.get_metrics(since=start)
        day_metrics = [m for m in all_metrics if m.timestamp < end.isoformat()]

        # Aggregate metrics
        signals_analyzed = len([m for m in day_metrics if m.name == "signal_analyzed"])
        trade_signals = len([m for m in day_metrics if m.name == "trade_signal"])
        no_trade_signals = len([m for m in day_metrics if m.name == "no_trade_signal"])

        cost_metrics = [m for m in day_metrics if m.name == "llm_cost"]
        total_cost = sum(m.value for m in cost_metrics)

        latency_metrics = [m for m in day_metrics if m.name == "analysis_latency"]
        avg_latency = (
            sum(m.value for m in latency_metrics) / len(latency_metrics)
            if latency_metrics
            else 0
        )

        # Get alerts for the day
        all_alerts = self.alerts._alerts
        day_alerts = [
            a for a in all_alerts
            if a.timestamp >= start.isoformat() and a.timestamp < end.isoformat()
        ]

        return {
            "report_date": str(report_date),
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "signals_analyzed": signals_analyzed,
                "trade_signals": trade_signals,
                "no_trade_signals": no_trade_signals,
                "total_llm_cost": total_cost,
                "avg_latency_ms": avg_latency,
            },
            "alerts": {
                "total": len(day_alerts),
                "critical": len([a for a in day_alerts if a.severity == AlertSeverity.CRITICAL]),
                "warning": len([a for a in day_alerts if a.severity == AlertSeverity.WARNING]),
                "info": len([a for a in day_alerts if a.severity == AlertSeverity.INFO]),
            },
            "positions": {
                # TODO: Get from order book
                "opened": 0,
                "closed": 0,
                "active": 0,
            },
        }


# Global instances
_metrics: Optional[MetricsCollector] = None
_alerts: Optional[AlertManager] = None
_health: Optional[HealthChecker] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def get_alerts() -> AlertManager:
    """Get global alert manager."""
    global _alerts
    if _alerts is None:
        _alerts = AlertManager()
    return _alerts


def get_health_checker() -> HealthChecker:
    """Get global health checker."""
    global _health
    if _health is None:
        _health = HealthChecker()
    return _health


# Convenience functions
def record_metric(name: str, value: float, **tags) -> None:
    """Record a metric."""
    get_metrics().record(name, value, tags)


def raise_alert(
    severity: AlertSeverity,
    title: str,
    message: str,
    **metadata,
) -> Alert:
    """Raise an alert."""
    return get_alerts().raise_alert(severity, title, message, metadata)
