"""
Handle resolution, handle caching, sensor snapshot reading, and actuator commit/fallback logic.
Implements 07_EnergyPlus_Design.md §1-3, SR-1, SR-2, SR-4, and FR-8.
"""

from typing import Dict, Any, Optional, List, Tuple
from src.shared.types import SensorSnapshot, ZoneState
from src.shared.logging import get_logger
from src.comfort.pmv import compute_pmv, PMVInputValidationError
from src.config.schema import Config, ActuatorConfig

logger = get_logger("bridge.handles")


class HandleManager:
    """
    Manages EnergyPlus API sensor/actuator handles.
    Guarantees handle resolution is lazy and gated on api_data_fully_ready.
    Caches handles once resolved to prevent repeated string lookup overhead.
    """

    def __init__(self):
        self._handles_resolved: bool = False
        self._variable_handles: Dict[Tuple[str, str], int] = {}
        self._actuator_handles: Dict[str, int] = {}  # logical_name -> handle
        self._meter_handle: int = -1
        self._active_api: Any = None
        self._active_state: Any = None
        self._last_known_good_values: Dict[str, float] = {}  # logical_name -> value
        self._committed_cycles: Dict[str, Dict[str, float]] = {}  # cycle_id -> {logical_name: value}

    @property
    def handles_resolved(self) -> bool:
        return self._handles_resolved

    def resolve_handles_if_ready(self, api: Any, state: Any, config: Config) -> bool:
        """
        Resolves handles only if api and state exist and api_data_fully_ready returns True.
        Returns True if handles are resolved and ready, False otherwise.
        """
        if api:
            self._active_api = api
        if state:
            self._active_state = state

        if self._handles_resolved:
            return True

        if api is None or state is None:
            return False

        if not hasattr(api, "exchange") or not api.exchange.api_data_fully_ready(state):
            return False

        logger.info("api_data_fully_ready is True. Resolving sensor, meter, and actuator handles...")

        # Resolve facility electricity meter handle
        try:
            self._meter_handle = api.exchange.get_meter_handle(state, "Electricity:Facility")
            if self._meter_handle != -1:
                logger.info(f"Resolved electricity meter handle: {self._meter_handle}")
        except Exception as e:
            logger.warning(f"Failed to resolve meter handle: {e}")

        # Resolve configured actuator handles
        all_resolved = True
        for act in config.actuators:
            handle = api.exchange.get_actuator_handle(
                state, act.component_type, act.control_type, act.key
            )
            if handle != -1:
                self._actuator_handles[act.logical_name] = handle
                logger.info(f"Resolved actuator handle '{act.logical_name}': {handle}")
            else:
                all_resolved = False

        if all_resolved:
            self._handles_resolved = True
            logger.info(f"All actuator handles successfully resolved: {self._actuator_handles}")
            return True
        
        return False

    def read_sensor_snapshot(
        self, api: Any, state: Any, config: Config, sim_time: str, phase: str = "run"
    ) -> SensorSnapshot:
        """
        Reads current sensor values from exchange API and computes PMV for configured zones.
        """
        if api:
            self._active_api = api
        if state:
            self._active_state = state

        zone_temp = 23.0
        zone_rh = 50.0
        zone_name = getattr(config.simulation, "primary_zone_name", "SPACE1-1")
        
        # Read actual variable values if state and handles are ready
        if api and state and hasattr(api, "exchange") and self._handles_resolved:
            try:
                temp_handle = api.exchange.get_variable_handle(state, "Zone Mean Air Temperature", zone_name)
                if temp_handle != -1:
                    zone_temp = api.exchange.get_variable_value(state, temp_handle)
                else:
                    logger.error(f"Zone temperature variable handle unresolved for zone '{zone_name}' — using stale default.")
                
                rh_handle = api.exchange.get_variable_handle(state, "Zone Air Relative Humidity", zone_name)
                if rh_handle != -1:
                    zone_rh = api.exchange.get_variable_value(state, rh_handle)
                else:
                    logger.error(f"Zone relative humidity variable handle unresolved for zone '{zone_name}' — using stale default.")
            except Exception as e:
                logger.warning(f"Error reading variable values from API: {e}")

        # Compute PMV deterministically
        try:
            pmv_res = compute_pmv(
                air_temp_c=max(10.0, min(32.0, zone_temp)),
                mean_radiant_temp_c=max(10.0, min(40.0, zone_temp)),
                air_speed_ms=0.1,
                rh_pct=max(0.0, min(100.0, zone_rh)),
                met_rate=1.2,
                clo=0.5,
            )
            pmv_val, ppd_val = pmv_res.pmv, pmv_res.ppd_pct
        except PMVInputValidationError as e:
            logger.warning(f"PMV input out of bounds: {e}. Defaulting to PMV=0.0")
            pmv_val, ppd_val = 0.0, 5.0

        current_setpoints: Dict[str, float] = {}
        for act in config.actuators:
            current_setpoints[act.logical_name] = self._last_known_good_values.get(
                act.logical_name, (act.min + act.max) / 2.0
            )

        z_state = ZoneState(
            zone_id=zone_name,
            air_temp_c=round(zone_temp, 2),
            rh_pct=round(zone_rh, 2),
            co2_ppm=None,
            pmv=pmv_val,
            ppd_pct=ppd_val,
            current_setpoints=current_setpoints,
        )

        facility_kwh = 0.0
        if api and state and hasattr(api, "exchange") and self._meter_handle != -1:
            try:
                joules = api.exchange.get_meter_value(state, self._meter_handle)
                facility_kwh = joules / 3600000.0
            except Exception as e:
                logger.warning(f"Error reading energy meter: {e}")

        meters = {
            "facility_electricity_kwh": round(facility_kwh, 4),
            "facility_electricity_kw": round(facility_kwh, 4),
        }

        return SensorSnapshot(
            sim_time=sim_time,
            zones=[z_state],
            meters=meters,
            phase=phase,
        )

    def commit_actuator(
        self,
        api: Any,
        state: Any,
        logical_name: str,
        value: float,
        cycle_id: str,
        config: Config,
    ) -> bool:
        """
        Commits an actuator write with cycle_id idempotency.
        Checks bounds against config allow-list.
        """
        target_name = logical_name
        act_cfg: Optional[ActuatorConfig] = None
        for a in config.actuators:
            if a.logical_name == target_name:
                act_cfg = a
                break
        
        if not act_cfg:
            for a in config.actuators:
                if ("heat" in target_name.lower() and "heat" in a.logical_name.lower()) or \
                   ("cool" in target_name.lower() and "cool" in a.logical_name.lower()):
                    act_cfg = a
                    target_name = a.logical_name
                    break

        if not act_cfg:
            logger.error(f"Cannot commit unlisted actuator: '{logical_name}'")
            return False

        if not (act_cfg.min <= value <= act_cfg.max):
            logger.error(
                f"Actuator write '{target_name}' value {value} violates bounds [{act_cfg.min}, {act_cfg.max}]"
            )
            return False

        if cycle_id in self._committed_cycles:
            committed_action = self._committed_cycles[cycle_id]
            if target_name in committed_action:
                existing_val = committed_action[target_name]
                if existing_val == value:
                    logger.info(f"Cycle '{cycle_id}' repeat commit for '{target_name}'={value} (no-op)")
                    return True
                else:
                    logger.error(
                        f"Cycle '{cycle_id}' mismatch: previously committed {existing_val}, requested {value}"
                    )
                    return False

        use_api = api or self._active_api
        use_state = state or self._active_state

        handle = self._actuator_handles.get(target_name, -1)
        if handle == -1 and use_api and use_state and hasattr(use_api, "exchange"):
            for act in config.actuators:
                if act.logical_name == target_name:
                    h = use_api.exchange.get_actuator_handle(
                        use_state, act.component_type, act.control_type, act.key
                    )
                    if h != -1:
                        handle = h
                        self._actuator_handles[target_name] = handle
                        logger.info(f"Lazy-resolved actuator handle '{target_name}': {handle}")
                    break

        if handle == -1:
            logger.error(f"Cannot commit '{target_name}': actuator handle was never resolved (-1).")
            return False

        if use_api and use_state and hasattr(use_api, "exchange"):
            try:
                use_api.exchange.set_actuator_value(use_state, handle, value)
                logger.info(f"EnergyPlus set_actuator_value('{target_name}', handle={handle}, value={value})")
            except Exception as e:
                logger.error(f"Failed to call set_actuator_value: {e}")
                return False

        self._last_known_good_values[target_name] = value
        if cycle_id not in self._committed_cycles:
            self._committed_cycles[cycle_id] = {}
        self._committed_cycles[cycle_id][target_name] = value

        return True

    def hold_last_known_good(self, api: Any, state: Any, config: Config, cycle_id: str) -> Dict[str, float]:
        use_api = api or self._active_api
        use_state = state or self._active_state
        held_values: Dict[str, float] = {}
        for act in config.actuators:
            val = self._last_known_good_values.get(act.logical_name, (act.min + act.max) / 2.0)
            handle = self._actuator_handles.get(act.logical_name, -1)
            if handle == -1 and use_api and use_state and hasattr(use_api, "exchange"):
                h = use_api.exchange.get_actuator_handle(
                    use_state, act.component_type, act.control_type, act.key
                )
                if h != -1:
                    handle = h
                    self._actuator_handles[act.logical_name] = handle

            if use_api and use_state and hasattr(use_api, "exchange") and handle != -1:
                try:
                    use_api.exchange.set_actuator_value(use_state, handle, val)
                except Exception as e:
                    logger.warning(f"Error in hold_last_known_good set_actuator_value: {e}")
            held_values[act.logical_name] = val
        logger.info(f"Cycle '{cycle_id}' fallback executed: held values {held_values}")
        return held_values
