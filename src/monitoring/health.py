"""
Monitoring module tracking health status and degraded mode transitions.
Implements RR-3, 03_Component_Design.md §11, and MODULE_BREAKDOWN.md.
"""

from typing import Dict, Any, Optional
from src.shared.logging import get_logger

logger = get_logger("monitoring.health")


class HealthMonitor:
    """
    Tracks cycle latency, fallback invocation count, and LLM reachability status.
    Triggers degraded mode after 3 consecutive LLM failures (RR-3).
    """

    def __init__(self, degraded_threshold_consecutive: int = 3):
        self.degraded_threshold = degraded_threshold_consecutive
        self.consecutive_llm_failures: int = 0
        self.total_cycles: int = 0
        self.fallback_cycles: int = 0
        self.degraded_mode_active: bool = False

    def record_cycle_success(self, latency_ms: float) -> None:
        """Records a successful clean cycle."""
        self.total_cycles += 1
        self.consecutive_llm_failures = 0
        if self.degraded_mode_active:
            logger.info("LLM connection restored. Exiting degraded mode.")
            self.degraded_mode_active = False

    def record_cycle_failure(self, reason: str, is_fallback: bool = True) -> None:
        """Records a failed/fallback cycle and updates degraded status."""
        self.total_cycles += 1
        if is_fallback:
            self.fallback_cycles += 1

        self.consecutive_llm_failures += 1
        logger.warning(
            f"Cycle failure recorded ({reason}). Consecutive failures: {self.consecutive_llm_failures}/{self.degraded_threshold}"
        )

        if self.consecutive_llm_failures >= self.degraded_threshold and not self.degraded_mode_active:
            self.degraded_mode_active = True
            logger.error(
                f"Degraded mode ACTIVATED after {self.consecutive_llm_failures} consecutive LLM failures (RR-3). "
                "Simulation will continue under fallback controller."
            )

    def get_health_status(self) -> Dict[str, Any]:
        """Returns current system health status."""
        fallback_pct = (self.fallback_cycles / self.total_cycles * 100.0) if self.total_cycles > 0 else 0.0
        return {
            "status": "degraded" if self.degraded_mode_active else "nominal",
            "total_cycles": self.total_cycles,
            "fallback_cycles": self.fallback_cycles,
            "fallback_pct": round(fallback_pct, 2),
            "consecutive_llm_failures": self.consecutive_llm_failures,
            "degraded_mode_active": self.degraded_mode_active,
        }
