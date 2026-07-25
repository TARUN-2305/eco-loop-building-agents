"""
EnergyPlus Bridge lifecycle and process orchestration module.
Implements 05_Runtime_Execution.md §1, 07_EnergyPlus_Design.md §1-2, and ADR-002.
No module outside src/bridge/ imports pyenergyplus.
Enforces strict native dependency validation.
"""

import os
import sys
from dataclasses import dataclass
from typing import Callable, Optional, Any, Dict
from src.shared.logging import get_logger
from src.config.schema import Config
from src.shared.types import SensorSnapshot
from src.bridge.handles import HandleManager
from src.bridge.callbacks import CallbackHandler

logger = get_logger("bridge.lifecycle")


class EnergyPlusDependencyError(RuntimeError):
    """Raised when native NREL EnergyPlus C-API bindings (pyenergyplus) are missing."""
    pass


@dataclass(frozen=True)
class RunResult:
    status: str  # "completed" or "incomplete"
    total_timesteps: int
    error_message: Optional[str] = None


class EnergyPlusBridge:
    """
    Primary interface to the running EnergyPlus process via pyenergyplus.api.
    Encapsulates state creation, callback registration, variable requests, and run execution.
    """

    def __init__(self, config: Config):
        self.config = config
        self.handle_manager = HandleManager()
        self.callback_handler: Optional[CallbackHandler] = None
        self._api: Optional[Any] = None
        self._state: Optional[Any] = None

    @property
    def handle_manager_ref(self) -> HandleManager:
        return self.handle_manager

    def run(
        self,
        on_decision_cycle_fn: Optional[Callable[[SensorSnapshot, str], Dict[str, Any]]] = None,
        telemetry_sink_fn: Optional[Callable[[SensorSnapshot], None]] = None,
        pyenergyplus_api_override: Optional[Any] = None,
    ) -> RunResult:
        """
        Runs an EnergyPlus simulation according to the loaded Config.
        Accepts optional pyenergyplus_api_override for explicit testing.
        """
        logger.info(
            f"Starting EnergyPlus Bridge run: mode='{self.config.simulation.run_mode}', "
            f"idf='{self.config.simulation.idf_path}', epw='{self.config.simulation.epw_path}'"
        )

        # 1. Initialize API reference with strict dependency detection
        if pyenergyplus_api_override is not None:
            self._api = pyenergyplus_api_override
        else:
            try:
                from pyenergyplus.api import EnergyPlusAPI
                self._api = EnergyPlusAPI()
            except ImportError:
                # Attempt auto-locating EnergyPlus installation directory
                candidate_paths = [
                    r"C:\EnergyPlusV26-1-0\EnergyPlus-26.1.0-6f2e40d102-Windows-x86_64",
                    r"C:\EnergyPlusV26-2-0\api\python",
                    r"C:\EnergyPlusV26-1-0\api\python",
                    r"C:\EnergyPlusV24-2-0\api\python",
                    r"C:\Program Files\EnergyPlusV26-2-0\api\python",
                    "/usr/local/EnergyPlus-26-2-0/api/python",
                    "/usr/local/EnergyPlus-24-2-0/api/python",
                ]
                located = False
                for p in candidate_paths:
                    if os.path.exists(p) and p not in sys.path:
                        sys.path.append(p)
                        located = True
                        break

                if located:
                    try:
                        from pyenergyplus.api import EnergyPlusAPI
                        self._api = EnergyPlusAPI()
                    except ImportError:
                        pass

                if self._api is None:
                    err_msg = (
                        "EnergyPlus native C-API Python bindings (pyenergyplus) were not found on this system.\n"
                        "To execute real EnergyPlus simulations:\n"
                        "1. Download and install NREL EnergyPlus v26.2.0 from: https://github.com/NREL/EnergyPlus/releases\n"
                        "2. Set the PYTHONPATH environment variable:\n"
                        "   PowerShell: $env:PYTHONPATH='C:\\EnergyPlusV26-2-0\\api\\python;' + $env:PYTHONPATH\n"
                        "   Linux/macOS: export PYTHONPATH=/usr/local/EnergyPlus-26-2-0/api/python:$PYTHONPATH\n"
                    )
                    logger.error(err_msg)
                    raise EnergyPlusDependencyError(err_msg)

        # Instantiate callback handler
        self.callback_handler = CallbackHandler(
            config=self.config,
            handle_manager=self.handle_manager,
            on_decision_cycle_fn=on_decision_cycle_fn,
            telemetry_sink_fn=telemetry_sink_fn,
        )

        # 2. Create new state
        self._state = self._api.state_manager.new_state()

        # 3. Setup-time variable requests (must occur before run_energyplus)
        try:
            zone_name = self.config.simulation.primary_zone_name
            self._api.exchange.request_variable(self._state, "Zone Mean Air Temperature", zone_name)
            self._api.exchange.request_variable(self._state, "Zone Air Relative Humidity", zone_name)
        except Exception as e:
            logger.warning(f"Error requesting variables during setup: {e}")

        # 4. Register callbacks
        def _setup_cb(state: Any) -> None:
            if self.callback_handler:
                self.callback_handler.handle_manager.resolve_handles_if_ready(self._api, state, self.config)

        def _zone_timestep_cb(state: Any) -> None:
            if self.callback_handler:
                self.callback_handler.on_zone_timestep_end(state, self._api)

        def _hvac_predictor_cb(state: Any) -> None:
            if self.callback_handler:
                self.callback_handler.on_hvac_predictor_end(state, self._api)

        try:
            self._api.runtime.callback_begin_zone_timestep_before_init_heat_balance(
                self._state, _setup_cb
            )
            self._api.runtime.callback_end_zone_timestep_after_zone_reporting(
                self._state, _zone_timestep_cb
            )
            self._api.runtime.callback_after_predictor_after_hvac_managers(
                self._state, _hvac_predictor_cb
            )
        except Exception as e:
            logger.error(f"Failed to register EnergyPlus callbacks: {e}")
            return RunResult(status="incomplete", total_timesteps=0, error_message=str(e))

        # 5. Build CLI argument list for run_energyplus using absolute paths
        idf_abs = os.path.abspath(self.config.simulation.idf_path)
        epw_abs = os.path.abspath(self.config.simulation.epw_path)
        ep_args = [
            "-d", "out",
            "-w", epw_abs,
            idf_abs,
        ]

        logger.info(f"Invoking api.runtime.run_energyplus(state, args={ep_args})")

        # 6. Execute simulation
        try:
            exit_code = self._api.runtime.run_energyplus(self._state, ep_args)
            if exit_code == 0:
                logger.info("EnergyPlus simulation completed cleanly with exit code 0.")
                return RunResult(
                    status="completed",
                    total_timesteps=self.callback_handler._timestep_count if self.callback_handler else 0,
                )
            else:
                logger.error(f"EnergyPlus simulation exited with non-zero exit code: {exit_code}")
                return RunResult(
                    status="incomplete",
                    total_timesteps=self.callback_handler._timestep_count if self.callback_handler else 0,
                    error_message=f"Exit code {exit_code}",
                )
        except Exception as e:
            logger.error(f"Fatal error during EnergyPlus execution: {e}")
            return RunResult(status="incomplete", total_timesteps=0, error_message=str(e))
        finally:
            if self._state and hasattr(self._api.state_manager, "delete_state"):
                self._api.state_manager.delete_state(self._state)
