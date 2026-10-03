"""Decision schema and validation for LLM output.

Only decisions that match this schema are accepted from the LLM; anything else
raises InvalidDecision and the module falls back to the rules.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

RISK_LEVELS = ("low", "medium", "high")
RISK_ORDER = {level: i for i, level in enumerate(RISK_LEVELS)}

# Same actions as the rule-based fallback, plus hover_and_monitor which the LLM
# can use when several drones confirm the same event.
ACTIONS = {
    "emergency_stop": "Stop immediately and hold position (object extremely close).",
    "avoid_obstacle": "Reduce speed and change course around a close object.",
    "notify_swarm": "Alert the swarm about an important event (fire, smoke...).",
    "track_person": "Keep a safe distance from a person and keep them in view.",
    "hover_and_monitor": "Hold position near a confirmed event and keep observing it.",
    "verify_detection": "Detection is uncertain; ask nearby drones to confirm.",
    "update_awareness_map": "Record a static/moving object on the shared map.",
    "continue_mission": "Nothing critical, continue the mission.",
}

REQUIRED_FIELDS = ("risk_level", "action", "recommendation", "broadcast", "target_drone")

# Sent to Ollama as "format": the model is constrained to produce this shape.
DECISION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {"type": "string", "enum": list(RISK_LEVELS)},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "recommendation": {"type": "string"},
        "broadcast": {"type": "boolean"},
        "target_drone": {"type": "string"},
    },
    "required": list(REQUIRED_FIELDS),
}

def decision_schema(allowed_actions=None):
    """JSON schema for one request, restricting the action enum to allowed_actions."""
    schema = json.loads(json.dumps(DECISION_JSON_SCHEMA))
    if allowed_actions:
        schema["properties"]["action"]["enum"] = list(allowed_actions)
    return schema


_TARGET_RE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


class InvalidDecision(ValueError):
    """LLM output could not be turned into a valid decision."""


def extract_json(raw: Any) -> Dict[str, Any]:
    """Parse JSON from LLM text, tolerating ```json fences or text around it."""
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidDecision("LLM response is empty or not a string")
    text = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise InvalidDecision("No JSON object found in LLM response")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise InvalidDecision(f"Malformed JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidDecision("LLM response is not a JSON object")
    return data


def _to_bool(value: Any) -> bool:
    # bool("false") is True in Python, so strings must be handled explicitly.
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise InvalidDecision(f"broadcast must be true/false, got {value!r}")


def validate_decision(data: Dict[str, Any]) -> Dict[str, Any]:
    for name in REQUIRED_FIELDS:
        if name not in data:
            raise InvalidDecision(f"Missing required field: {name}")

    risk = str(data["risk_level"]).strip().lower()
    if risk not in RISK_LEVELS:
        raise InvalidDecision(f"Invalid risk_level: {data['risk_level']!r}")

    action = str(data["action"]).strip().lower().replace(" ", "_").replace("-", "_")
    if action not in ACTIONS:
        raise InvalidDecision(f"Invalid action: {data['action']!r}")

    recommendation = str(data["recommendation"]).strip()
    if not recommendation:
        raise InvalidDecision("Empty recommendation")

    target = str(data["target_drone"]).strip() or "none"
    if not _TARGET_RE.match(target):
        raise InvalidDecision(f"Invalid target_drone: {data['target_drone']!r}")

    return {
        "risk_level": risk,
        "action": action,
        "recommendation": recommendation[:200],
        "broadcast": _to_bool(data["broadcast"]),
        "target_drone": target,
    }


def parse_and_validate(raw: Any) -> Dict[str, Any]:
    return validate_decision(extract_json(raw))
