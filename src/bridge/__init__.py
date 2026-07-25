"""
Bridge module exposing EnergyPlusBridge, HandleManager, CallbackHandler, and RunResult.
Sole importer of pyenergyplus per ARCHITECTURAL_GUARDRAILS.md.
"""

from src.bridge.lifecycle import EnergyPlusBridge, RunResult
from src.bridge.handles import HandleManager
from src.bridge.callbacks import CallbackHandler

__all__ = [
    "EnergyPlusBridge",
    "RunResult",
    "HandleManager",
    "CallbackHandler",
]
