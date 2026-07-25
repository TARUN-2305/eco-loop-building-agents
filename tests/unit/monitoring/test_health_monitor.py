"""
Unit tests for HealthMonitor degraded mode transitions (RR-3).
"""

import pytest
from src.monitoring.health import HealthMonitor


def test_health_monitor_degraded_mode_trigger():
    monitor = HealthMonitor(degraded_threshold_consecutive=3)
    assert not monitor.degraded_mode_active

    # 1 failure
    monitor.record_cycle_failure("Error 1")
    assert monitor.consecutive_llm_failures == 1
    assert not monitor.degraded_mode_active

    # 2 failure
    monitor.record_cycle_failure("Error 2")
    assert monitor.consecutive_llm_failures == 2
    assert not monitor.degraded_mode_active

    # 3 consecutive failure -> Activates degraded mode
    monitor.record_cycle_failure("Error 3")
    assert monitor.consecutive_llm_failures == 3
    assert monitor.degraded_mode_active
    assert monitor.get_health_status()["status"] == "degraded"

    # Success resets failure counter and exits degraded mode
    monitor.record_cycle_success(latency_ms=150.0)
    assert monitor.consecutive_llm_failures == 0
    assert not monitor.degraded_mode_active
    assert monitor.get_health_status()["status"] == "nominal"
