"""
Callback registration and lifecycle hook handlers for EnergyPlus Runtime API.
Implements 07_EnergyPlus_Design.md §2, 05_Runtime_Execution.md §3, EDGE-1, EDGE-2.
"""

from typing import Callable, Optional, Any, Dict
import uuid
from src.shared.types import SensorSnapshot
from src.shared.logging import get_logger
from src.config.schema import Config
from src.bridge.handles import HandleManager

logger = get_logger("bridge.callbacks")


class CallbackHandler:
    """
    Handles EnergyPlus API runtime callback points.
    Distinguishes zone-timestep sensor reading from decision-cadence boundaries.
    Gates decision cycles off during warmup and sizing environments.
    """

    def __init__(
        self,
        config: Config,
        handle_manager: HandleManager,
        on_decision_cycle_fn: Optional[Callable[[SensorSnapshot, str], Dict[str, Any]]] = None,
        telemetry_sink_fn: Optional[Callable[[SensorSnapshot], None]] = None,
    ):
        self.config = config
        self.handle_manager = handle_manager
        self.on_decision_cycle_fn = on_decision_cycle_fn
        self.telemetry_sink_fn = telemetry_sink_fn
        self._timestep_count: int = 0
        self._last_decision_timestep: int = -1

    def on_zone_timestep_end(self, state: Any, api: Any) -> None:
        """
        Registered at callback_end_zone_timestep_after_zone_reporting.
        Fires every zone timestep.
        Reads sensors, computes PMV, sends telemetry, and checks cadence boundary.
        """
        try:
            # Check handle resolution readiness
            self.handle_manager.resolve_handles_if_ready(api, state, self.config)

            # Detect warmup phase (EDGE-1)
            is_warmup = False
            if api and state and hasattr(api, "exchange"):
                try:
                    is_warmup = bool(api.exchange.warmup_flag(state))
                except Exception:
                    is_warmup = False

            phase = "warmup" if is_warmup else "run"

            # Construct simulation timestamp string
            sim_time = f"Timestep_{self._timestep_count}"
            if api and state and hasattr(api, "exchange") and self.handle_manager.handles_resolved:
                try:
                    day = api.exchange.day_of_year(state)
                    hour = api.exchange.current_time(state)
                    sim_time = f"Day_{day}_Hour_{hour:.2f}"
                except Exception:
                    pass

            # Read SensorSnapshot
            snapshot = self.handle_manager.read_sensor_snapshot(
                api, state, self.config, sim_time=sim_time, phase=phase
            )

            # Sink snapshot asynchronously to Storage
            if self.telemetry_sink_fn:
                try:
                    self.telemetry_sink_fn(snapshot)
                except Exception as e:
                    logger.error(f"Error calling telemetry sink: {e}")

            # Do NOT fire decision cycles during warmup or baseline run mode
            if is_warmup or self.config.simulation.run_mode == "baseline":
                self._timestep_count += 1
                return

            # Check decision cadence boundary (e.g. interval_minutes = 15)
            cadence_timesteps = max(1, self.config.decision_cadence.interval_minutes // 15)
            
            if (self._timestep_count - self._last_decision_timestep) >= cadence_timesteps:
                self._last_decision_timestep = self._timestep_count
                cycle_id = f"cycle_{uuid.uuid4().hex[:8]}"

                if self.on_decision_cycle_fn:
                    try:
                        result = self.on_decision_cycle_fn(snapshot, cycle_id)
                        outcome = result.get("outcome", "fallback")
                    except Exception as e:
                        logger.error(f"Uncaught exception in decision cycle '{cycle_id}': {e}. Triggering fallback.")
                        self.handle_manager.hold_last_known_good(api, state, self.config, cycle_id)

            self._timestep_count += 1

        except Exception as e:
            logger.error(f"Unhandled exception in on_zone_timestep_end callback: {e}")

    def on_hvac_predictor_end(self, state: Any, api: Any) -> None:
        pass
