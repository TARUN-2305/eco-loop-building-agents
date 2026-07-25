"""
MCP tool: get_history.
Implements 09_MCP_Architecture.md §2.8 and 15_Performance.md §3.
"""

from typing import Dict, Any, Optional
from src.storage import queries


def execute_get_history(
    conn: Any,
    run_id: str,
    query_type: str = "similar_conditions",
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes bounded history query against Storage.
    Supports query_type: 'similar_conditions', 'recent_incidents', 'daily_summary'.
    Returns graceful no_comparable_history on cold start.
    """
    params = params or {}

    if query_type == "similar_conditions":
        target_temp = float(params.get("target_air_temp_c", 23.0))
        records = queries.get_similar_days(conn, run_id, target_temp_c=target_temp, limit=5)
        if not records:
            return {"isError": True, "reason": "no_comparable_history"}
        return {"query_type": query_type, "results": records}

    elif query_type == "recent_incidents":
        records = queries.get_recent_incidents(conn, run_id, limit=10)
        return {"query_type": query_type, "results": records}

    elif query_type == "daily_summary":
        summary = queries.get_run_summary(conn, run_id)
        if not summary:
            return {"isError": True, "reason": "no_comparable_history"}
        return {"query_type": query_type, "results": summary}

    else:
        return {"isError": True, "reason": "unknown_query_type", "detail": f"Unsupported query_type '{query_type}'"}
