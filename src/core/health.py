"""
Health Checks - System Health Monitoring
=========================================

Health check endpoints and system status monitoring.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

import asyncio
import psutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from .logging_config import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    last_check: datetime = field(default_factory=datetime.now)
    details: Dict[str, any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    """Overall system health."""
    status: HealthStatus
    components: List[ComponentHealth] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    uptime_seconds: float = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "last_check": c.last_check.isoformat(),
                    "details": c.details,
                }
                for c in self.components
            ],
        }


class HealthChecker:
    """System health checker."""

    def __init__(self):
        self.start_time = time.time()
        self._checks: Dict[str, callable] = {}

        # Register default checks
        self.register_check("system_resources", self._check_system_resources)
        self.register_check("memory", self._check_memory)

    def register_check(self, name: str, check_fn: callable) -> None:
        """Register a health check."""
        self._checks[name] = check_fn
        logger.debug("health_check_registered", name=name)

    async def check_health(self) -> SystemHealth:
        """Run all health checks."""
        components = []
        overall_status = HealthStatus.HEALTHY

        for name, check_fn in self._checks.items():
            try:
                component = await check_fn()
                components.append(component)

                # Determine overall status
                if component.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif component.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED

            except Exception as e:
                logger.error("health_check_failed", name=name, error=str(e))
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}",
                ))
                overall_status = HealthStatus.UNHEALTHY

        uptime = time.time() - self.start_time

        return SystemHealth(
            status=overall_status,
            components=components,
            uptime_seconds=uptime,
        )

    async def _check_system_resources(self) -> ComponentHealth:
        """Check system resource usage."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        disk_usage = psutil.disk_usage('/').percent

        # Thresholds
        cpu_warn = 80
        cpu_critical = 95
        disk_warn = 85
        disk_critical = 95

        if cpu_percent > cpu_critical or disk_usage > disk_critical:
            status = HealthStatus.UNHEALTHY
            message = "Critical resource usage"
        elif cpu_percent > cpu_warn or disk_usage > disk_warn:
            status = HealthStatus.DEGRADED
            message = "High resource usage"
        else:
            status = HealthStatus.HEALTHY
            message = "Resources OK"

        return ComponentHealth(
            name="system_resources",
            status=status,
            message=message,
            details={
                "cpu_percent": cpu_percent,
                "disk_usage_percent": disk_usage,
            },
        )

    async def _check_memory(self) -> ComponentHealth:
        """Check memory usage."""
        memory = psutil.virtual_memory()
        mem_percent = memory.percent

        # Thresholds
        mem_warn = 85
        mem_critical = 95

        if mem_percent > mem_critical:
            status = HealthStatus.UNHEALTHY
            message = "Critical memory usage"
        elif mem_percent > mem_warn:
            status = HealthStatus.DEGRADED
            message = "High memory usage"
        else:
            status = HealthStatus.HEALTHY
            message = "Memory OK"

        return ComponentHealth(
            name="memory",
            status=status,
            message=message,
            details={
                "percent": mem_percent,
                "total_mb": memory.total / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
            },
        )


# Global health checker instance
health_checker = HealthChecker()
