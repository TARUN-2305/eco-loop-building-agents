"""
LLM Client wrapper supporting OpenAI-compatible and local serving endpoints (Ollama/vLLM).
Implements ADR-004, ADR-008, LR-2, NFR-5, and 08_LLM_and_Agent_System.md §5.
Enforces strict endpoint validation and clean JSON tool call decoding.
"""

import json
import re
import requests
from typing import Dict, Any, List, Optional
from src.shared.logging import get_logger
from src.config.schema import LLMConfig

logger = get_logger("agent.llm_client")

SYSTEM_PROMPT_PREFIX = """You are the Eco-Loop Supervisory Building Agent.
Your objective is to maintain thermal comfort inside the ASHRAE 55 band (PMV between -0.5 and +0.5) while minimizing facility electricity consumption.
You interact with the building strictly by invoking the registered MCP tools.

You MUST respond strictly in valid JSON format matching this schema:
{
  "thought": "Your step-by-step reasoning...",
  "tool_call": {
    "tool": "propose_setpoints" | "validate_action" | "apply_setpoints" | "get_weather_forecast" | "get_utility_signal" | "get_history" | "compute_pmv",
    "arguments": { ... }
  }
}

Rules:
1. Never guess setpoint arithmetic. Always invoke `propose_setpoints` with objective_weights: {"w_energy": 0.5, "w_comfort_penalty": 0.5} to generate candidate setpoints.
2. Always invoke `validate_action` with candidate setpoints before attempting `apply_setpoints`.
3. Explain your qualitative reasoning in "thought".
"""


class LLMConnectionError(RuntimeError):
    """Raised when LLM inference server is missing or unreachable."""
    pass


class LLMClient:
    """
    Client for LLM inference server.
    Supports structured JSON tool calling, static prefix KV-cache reuse, and deterministic sampling.
    """

    def __init__(self, config: LLMConfig, deterministic_sampling: bool = True):
        self.config = config
        self.deterministic_sampling = deterministic_sampling

    def complete(
        self,
        observation_context: str,
        memory_context: str,
        available_tools: List[Dict[str, str]],
        messages: Optional[List[Dict[str, str]]] = None,
        mock_response_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a completion call against the LLM inference endpoint.
        Returns typed completion response (text + tool_call).
        """
        if mock_response_override is not None:
            return mock_response_override

        if not self.config.endpoint:
            err_msg = "No 'llm.endpoint' configured. A valid REST endpoint (e.g. http://localhost:11434/v1) is required."
            logger.error(err_msg)
            raise LLMConnectionError(err_msg)

        if messages is None:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_PREFIX + f"\nTools Catalog:\n{json.dumps(available_tools)}"},
                {"role": "user", "content": f"{memory_context}\n\n=== CURRENT OBSERVATION ===\n{observation_context}"},
            ]

        prompt_payload = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": 0.0 if self.deterministic_sampling else 0.7,
            "seed": 42 if self.deterministic_sampling else None,
            "response_format": {"type": "json_object"},  # Constrained output decoding (ADR-008)
        }

        try:
            url = f"{self.config.endpoint.rstrip('/')}/chat/completions"
            resp = requests.post(url, json=prompt_payload, timeout=self.config.cycle_timeout_seconds)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                # 1. Clean markdown codeblocks
                if "```" in content:
                    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
                    if match:
                        content = match.group(1)

                # 2. Extract JSON substring if text precedes/follows
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx : end_idx + 1]
                    try:
                        return json.loads(json_str)
                    except Exception:
                        pass

                try:
                    return json.loads(content)
                except Exception:
                    logger.warning(f"Could not parse LLM output as JSON: '{content[:100]}...'. Returning raw thought.")
                    return {"thought": content, "tool_call": None}

            else:
                logger.error(f"LLM server HTTP error {resp.status_code}: {resp.text}")
                raise LLMConnectionError(f"LLM endpoint returned HTTP {resp.status_code}")
        except requests.exceptions.RequestException as req_err:
            err_msg = f"Failed to connect to LLM inference endpoint '{self.config.endpoint}': {req_err}"
            logger.error(err_msg)
            raise LLMConnectionError(err_msg)
