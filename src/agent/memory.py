"""
Two-tier Memory implementation: rolling window + periodic reflection summary.
Implements 08_LLM_and_Agent_System.md §3, 03_Component_Design.md §5, and 15_Performance.md §3.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from src.shared.logging import get_logger

logger = get_logger("agent.memory")


@dataclass
class MemoryTurn:
    cycle_id: str
    sim_time: str
    action_or_incident: Dict[str, Any]
    outcome: str
    rationale: str


class TwoTierMemory:
    """
    Two-tier memory:
      - Tier 1: Rolling window of last K cycles verbatim.
      - Tier 2: End-of-day natural language reflection summary.
    Prevents prompt context length blowup (R-05).
    """

    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self._rolling_window: List[MemoryTurn] = []
        self._reflection_summary: str = "Initial run: no past day reflections available."

    def append_turn(self, turn: MemoryTurn) -> None:
        """Appends a turn to rolling window. Truncates to window_size."""
        self._rolling_window.append(turn)
        if len(self._rolling_window) > self.window_size:
            self._rolling_window.pop(0)

    def set_reflection_summary(self, summary_text: str) -> None:
        """Updates the natural language reflection summary (end-of-day)."""
        self._reflection_summary = summary_text.strip()
        logger.info("Updated daily reflection memory summary.")

    def get_prompt_context(self) -> str:
        """
        Formats memory context for insertion into LLM prompt.
        Includes daily reflection summary + rolling window turns.
        """
        lines = [f"=== DAILY REFLECTION SUMMARY ===\n{self._reflection_summary}\n"]
        lines.append("=== RECENT DECISION HISTORY (LAST FEW CYCLES) ===")

        if not self._rolling_window:
            lines.append("No recent cycles recorded.")
        else:
            for t in self._rolling_window:
                lines.append(
                    f"Cycle [{t.cycle_id}] at {t.sim_time}: Outcome={t.outcome}, "
                    f"Action={t.action_or_incident}, Rationale='{t.rationale}'"
                )

        return "\n".join(lines)
