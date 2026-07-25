"""
MCP tool: log_decision.
Implements 09_MCP_Architecture.md §2.9.
"""

from typing import Dict, Any, List
from src.shared.types import DecisionLog, ToolTrace
from src.storage.writer import AsyncStorageWriter


def execute_log_decision(
    cycle_id: str,
    run_id: str,
    sim_time: str,
    rationale: str,
    action_or_incident: Dict[str, Any],
    outcome: str,
    trace: List[Dict[str, Any]],
    storage_writer: AsyncStorageWriter,
) -> Dict[str, Any]:
    """
    Enqueues DecisionLog asynchronously to Storage.
    Always returns logged: True immediately (non-blocking fire-and-forget).
    """
    tool_traces = [
        ToolTrace(
            tool=t.get("tool", "unknown"),
            args=t.get("args", {}),
            result_summary=str(t.get("result_summary", "")),
        )
        for t in trace
    ]

    dlog = DecisionLog(
        run_id=run_id,
        cycle_id=cycle_id,
        sim_time=sim_time,
        rationale=rationale,
        action_or_incident=action_or_incident,
        outcome=outcome,
        trace=tool_traces,
    )

    storage_writer.enqueue_decision_log(dlog)
    return {"logged": True, "cycle_id": cycle_id}
