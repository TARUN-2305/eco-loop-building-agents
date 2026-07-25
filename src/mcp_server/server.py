"""
MCP Server implementation over stdio transport.
Registers exactly ten discrete tools per 09_MCP_Architecture.md §2 and SR-3.
Protocol revision: 2025-11-25.
"""

from typing import Dict, Any, List, Callable
from src.shared.logging import get_logger

# Import tool executions
from src.mcp_server.tools.get_zone_state import execute_get_zone_state
from src.mcp_server.tools.get_weather_forecast import execute_get_weather_forecast
from src.mcp_server.tools.get_utility_signal import execute_get_utility_signal
from src.mcp_server.tools.compute_pmv import execute_compute_pmv
from src.mcp_server.tools.propose_setpoints import execute_propose_setpoints
from src.mcp_server.tools.validate_action import execute_validate_action
from src.mcp_server.tools.apply_setpoints import execute_apply_setpoints
from src.mcp_server.tools.get_history import execute_get_history
from src.mcp_server.tools.log_decision import execute_log_decision
from src.mcp_server.tools.raise_incident import execute_raise_incident

logger = get_logger("mcp_server")

PROTOCOL_VERSION = "2025-11-25"

# The 10 fixed tools catalog (SR-3, ADR-011)
TOOL_CATALOG: Dict[str, str] = {
    "get_zone_state": "Read current indoor zone state and setpoints",
    "get_weather_forecast": "Read outdoor weather forecast horizon",
    "get_utility_signal": "Read utility grid carbon intensity and price signal",
    "compute_pmv": "Compute analytical Fanger PMV/PPD thermal comfort",
    "propose_setpoints": "Invoke deterministic setpoint optimizer solver",
    "validate_action": "Validate candidate setpoint action against hard safety bounds",
    "apply_setpoints": "Commit setpoint action to EnergyPlus via Bridge with server-side re-validation",
    "get_history": "Query historical telemetry, incidents, or similar days from Storage",
    "log_decision": "Enqueue DecisionLog asynchronously to Storage",
    "raise_incident": "Trigger fallback path and record incident",
}


class MCPServer:
    """
    Model Context Protocol Server over stdio transport.
    """

    def __init__(self):
        self.tools: Dict[str, Callable] = {
            "get_zone_state": execute_get_zone_state,
            "get_weather_forecast": execute_get_weather_forecast,
            "get_utility_signal": execute_get_utility_signal,
            "compute_pmv": execute_compute_pmv,
            "propose_setpoints": execute_propose_setpoints,
            "validate_action": execute_validate_action,
            "apply_setpoints": execute_apply_setpoints,
            "get_history": execute_get_history,
            "log_decision": execute_log_decision,
            "raise_incident": execute_raise_incident,
        }

    def list_tools(self) -> List[Dict[str, str]]:
        """Returns the list of registered tools. Exactly 10 tools."""
        return [{"name": name, "description": desc} for name, desc in TOOL_CATALOG.items()]

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], **context_kwargs) -> Dict[str, Any]:
        """
        Executes a registered tool by name with arguments and context kwargs.
        Handles protocol errors vs tool execution errors per MCP spec.
        """
        if tool_name not in self.tools:
            logger.error(f"MCP Protocol Error: Unknown tool requested: '{tool_name}'")
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method/Tool not found: '{tool_name}'"},
            }

        try:
            fn = self.tools[tool_name]
            result = fn(**arguments, **context_kwargs)
            return result
        except Exception as e:
            logger.error(f"Unexpected exception during execution of tool '{tool_name}': {e}")
            return {"isError": True, "reason": "execution_exception", "detail": str(e)}


def get_tool_catalog() -> Dict[str, str]:
    """Helper function for CI checks verifying tool catalog size."""
    return TOOL_CATALOG
