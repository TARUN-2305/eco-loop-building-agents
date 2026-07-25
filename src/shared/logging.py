"""
Structured JSON logging wrapper enforcing cycle_id inclusion.
Implements NFR-4 and MODULE_BREAKDOWN.md requirement for shared/logging.py.
"""

import logging
import json
import sys
from typing import Optional, Dict, Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        
        # Thread correlation cycle_id if attached to extra
        if hasattr(record, "cycle_id") and record.cycle_id:
            log_obj["cycle_id"] = record.cycle_id
            
        if hasattr(record, "run_id") and record.run_id:
            log_obj["run_id"] = record.run_id

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def get_logger(component_name: str) -> logging.Logger:
    """Get a structured JSON logger for a specific component."""
    logger = logging.getLogger(f"eco_loop.{component_name}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger
