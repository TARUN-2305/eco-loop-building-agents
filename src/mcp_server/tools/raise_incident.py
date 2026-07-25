"""
MCP tool: raise_incident.
Implements 09_MCP_Architecture.md §2.10.
"""

from typing import Dict, Any, Optional
from src.shared.types import Incident
from src.storage.writer import AsyncStorageWriter
from src.bridge.handles import HandleManager
from src.config.schema import Config


def execute_raise_incident(
    cycle_id: str = "cycle_default",
    run_id: str = "run_default",
    reason: str = "incident_raised_by_agent",
    severity: str = "warning",
    storage_writer: Optional[AsyncStorageWriter] = None,
    handle_manager: Optional[HandleManager] = None,
    config: Optional[Config] = None,
    api: Any = None,
    state: Any = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Triggers fallback path at Bridge level and records incident asynchronously.
    """
    cid = cycle_id or kwargs.get("cycle", "cycle_default")
    rid = run_id or kwargs.get("run", "run_default")
    reas = reason or kwargs.get("message", "incident_raised_by_agent")
    sev = severity or kwargs.get("level", "warning")

    incident = Incident(
        cycle_id=cid,
        reason=reas,
        severity=sev,
    )
    if storage_writer:
        storage_writer.enqueue_incident(incident, rid)

    held_values = {}
    if handle_manager and config:
        held_values = handle_manager.hold_last_known_good(api, state, config, cycle_id)

    return {
        "acknowledged": True,
        "cycle_id": cycle_id,
        "fallback_values_held": held_values,
    }
