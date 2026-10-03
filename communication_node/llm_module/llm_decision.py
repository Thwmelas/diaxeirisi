"""LLM Decision-Making Module for AI-Enabled Drone Swarm Project.

The module receives MQTT/YOLO alerts as Python dictionaries and returns
a structured JSON-compatible decision.

Pipeline:
    message -> normalize -> prompt (+ recent swarm history) -> LLM (Ollama)
            -> parse + validate -> safety layer -> decision
    If the LLM is disabled, unreachable, slow or returns invalid output,
    the rule-based fallback is used, so a valid decision is ALWAYS returned.

Public API (used by llm_decision_node.py and perception_node/drone_integration.py):
    LLMDecisionMaker(drone_id=..., use_llm=..., keep_history=...).interpret(message)
    interpret_drone_message(message)

Enable the LLM without changing code:
    export DRONE_USE_LLM=1         (and optionally OLLAMA_MODEL=qwen2.5:3b)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from rule_based_fallback import rule_based_decision
from safety import apply_safety_override
from schema import ACTIONS, DECISION_JSON_SCHEMA, parse_and_validate
from swarm_context import summarize_history

Decision = Dict[str, Any]
DroneMessage = Dict[str, Any]

PROMPT_FIELDS = ("drone_id", "timestamp", "object", "distance", "direction",
                 "confidence", "location", "size", "velocity")


def llm_enabled_from_env() -> bool:
    return os.getenv("DRONE_USE_LLM", "0").strip().lower() in ("1", "true", "yes", "on")


def default_llm_client():
    from llm_client import OllamaClient
    return OllamaClient(json_schema=DECISION_JSON_SCHEMA)


@dataclass
class LLMDecisionMaker:
    """Interprets drone messages and produces decisions.

    use_llm=False: rules only (stable output for the live demo).
    use_llm=True:  LLM with safety layer; if llm_client is not given, a local
                   Ollama client is created. llm_client(prompt) -> response_text.
    """

    drone_id: str = "llm_module"
    use_llm: bool = False
    llm_client: Optional[Any] = None
    keep_history: bool = True
    max_history_items: int = 10
    history: List[DroneMessage] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.use_llm and self.llm_client is None:
            self.llm_client = default_llm_client()

    def interpret(self, message: DroneMessage) -> Decision:
        normalized = self._normalize_message(message)

        if not self.use_llm or self.llm_client is None:
            self._remember(normalized)
            return self._with_metadata(rule_based_decision(normalized), "rule_based_fallback")

        # Prompt is built BEFORE adding the current message to history,
        # so the history section only contains earlier reports.
        prompt = self.build_prompt(normalized)
        self._remember(normalized)

        start = time.perf_counter()
        try:
            raw_response = self.llm_client(prompt)
            validated = self.validate_decision(self.parse_llm_json(raw_response))
        except Exception as exc:
            fallback = rule_based_decision(normalized)
            fallback["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:300]
            return self._with_metadata(fallback, "rule_based_fallback")
        latency_ms = round((time.perf_counter() - start) * 1000, 1)

        final, overrides = apply_safety_override(normalized, validated)
        if overrides:
            final["safety_overrides"] = overrides
        final["llm_latency_ms"] = latency_ms
        return self._with_metadata(final, "llm+safety" if overrides else "llm")

    def build_prompt(self, message: DroneMessage) -> str:
        actions = "\n".join(f"- {name}: {desc}" for name, desc in ACTIONS.items())
        current = {k: message.get(k) for k in PROMPT_FIELDS if message.get(k) is not None}
        history_text = summarize_history(self.history, message) if self.keep_history else "Not available."
        return f"""
You are the decision-making module of an autonomous drone swarm.
YOLO detects objects in drone camera frames; MQTT carries only processed JSON, not images.
Decide how the swarm should react to the current report. Return ONLY one JSON object.

Allowed actions:
{actions}

Guidelines:
- distance <= 5 m: risk "high", action "emergency_stop".
- distance <= 10 m: risk "high", action "avoid_obstacle" (or "emergency_stop").
- fire or smoke: risk "high", broadcast true.
- person: risk "high", usually "track_person".
- confidence < 0.50 means an uncertain detection: prefer "verify_detection",
  UNLESS other drones recently reported the same object nearby (that confirms it).
- Missing distance or confidence is normal (not every sensor sends them); do not treat it as danger.
- Use the recent reports: several drones reporting the same hazard close together
  confirms it and may justify "hover_and_monitor" or "notify_swarm".
- target_drone: "all" to alert everyone, a drone id (e.g. "drone_2") to address one drone, "none" if no message is needed.
- recommendation: one short imperative sentence, max 20 words.

Recent reports (most recent first):
{history_text}

Current report:
{json.dumps(current)}

Output format:
{{"risk_level": "low|medium|high", "action": "<allowed action>", "recommendation": "<short command>", "broadcast": true|false, "target_drone": "all|<drone_id>|none"}}
""".strip()

    @staticmethod
    def parse_llm_json(raw_response: str) -> Decision:
        from schema import extract_json
        return extract_json(raw_response)

    @staticmethod
    def validate_decision(decision: Decision) -> Decision:
        from schema import validate_decision
        return validate_decision(decision)

    def _normalize_message(self, message: DroneMessage) -> DroneMessage:
        """Normalize the real MQTT payload used by the team.

        Current MQTT publisher sends:
        {
          "drone_id": "drone_1",
          "object": "fire/tree/person/...",
          "location": [x1, y1, x2, y2] OR [x, y, z],
          "size": [width, height],
          "velocity": [0, 0, 0]
        }

        drone_integration.py and older test cases also send distance,
        direction and confidence. This function supports both formats.
        """
        normalized = dict(message)
        normalized["drone_id"] = str(normalized.get("drone_id") or "unknown_drone")
        normalized["object"] = str(normalized.get("object") or "unknown").lower().strip()
        if not normalized.get("timestamp"):
            normalized["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Optional numeric fields: missing/broken -> None (not the same as low/zero).
        for key in ("confidence", "distance"):
            try:
                normalized[key] = float(normalized[key]) if normalized.get(key) is not None else None
            except (TypeError, ValueError):
                normalized[key] = None

        location = normalized.get("location")
        bbox = normalized.get("bbox")
        if bbox is None and isinstance(location, list) and len(location) == 4:
            bbox = location
            normalized["bbox"] = bbox

        direction = normalized.get("direction")
        if not direction:
            direction = self._estimate_direction_from_bbox(bbox)
        normalized["direction"] = str(direction or "unknown").lower().strip()
        return normalized

    @staticmethod
    def _estimate_direction_from_bbox(bbox: Any, image_width: int = 1024) -> str:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return "unknown"
        try:
            x1, _, x2, _ = [float(v) for v in bbox]
            center_x = (x1 + x2) / 2
        except (TypeError, ValueError):
            return "unknown"
        if center_x < image_width * 0.4:
            return "left"
        if center_x > image_width * 0.6:
            return "right"
        return "front"

    def _remember(self, message: DroneMessage) -> None:
        if self.keep_history:
            self._update_history(message)

    def _update_history(self, message: DroneMessage) -> None:
        self.history.append(message)
        self.history = self.history[-self.max_history_items :]

    def _with_metadata(self, decision: Decision, source: str) -> Decision:
        decision["decision_source"] = source
        decision["decision_time"] = datetime.now(timezone.utc).isoformat()
        decision["module_id"] = self.drone_id
        return decision


# One shared decision maker per mode, so interpret_drone_message() keeps
# history between calls (e.g. inside the drone_integration.py loop).
_shared_makers: Dict[bool, LLMDecisionMaker] = {}


def interpret_drone_message(
    message: DroneMessage,
    use_llm: Optional[bool] = None,
    llm_client: Optional[Any] = None,
) -> Decision:
    """Convenience function. use_llm=None reads the DRONE_USE_LLM env variable."""
    if use_llm is None:
        use_llm = llm_enabled_from_env()
    if llm_client is not None:
        return LLMDecisionMaker(use_llm=use_llm, llm_client=llm_client).interpret(message)
    if use_llm not in _shared_makers:
        _shared_makers[use_llm] = LLMDecisionMaker(use_llm=use_llm)
    return _shared_makers[use_llm].interpret(message)


if __name__ == "__main__":
    sample = {
        "drone_id": "drone_1",
        "object": "fire",
        "location": [120, 80, 420, 500],
        "size": [300, 420],
        "velocity": [0, 0, 0],
    }
    print(json.dumps(interpret_drone_message(sample), indent=2))
