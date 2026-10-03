"""Safety layer: the LLM may ESCALATE a decision, never WEAKEN a hard rule.

Compares the LLM decision with the deterministic rules and corrects it where
it is less safe. Every correction is reported so it can be logged and counted.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from rule_based_fallback import (
    CLOSE_DISTANCE_M, EMERGENCY_DISTANCE_M, HAZARDS, LOW_CONFIDENCE, _to_float, rule_based_decision,
)
from schema import RISK_ORDER


def apply_safety_override(message: Dict[str, Any], decision: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    rules = rule_based_decision(message)
    final = dict(decision)
    overrides: List[str] = []

    distance = _to_float(message.get("distance"))
    confidence = _to_float(message.get("confidence"))
    obj = str(message.get("object") or "unknown").lower().strip()

    # A. Imminent collision.
    if distance is not None and distance <= CLOSE_DISTANCE_M:
        allowed = {"emergency_stop"} if distance <= EMERGENCY_DISTANCE_M else {"emergency_stop", "avoid_obstacle"}
        if final["action"] not in allowed:
            final["action"] = rules["action"]
            final["recommendation"] = rules["recommendation"]
            overrides.append("collision_action")

    # B. Fire/smoke that is not explicitly low-confidence must be broadcast.
    if obj in HAZARDS and (confidence is None or confidence >= LOW_CONFIDENCE):
        if not final["broadcast"]:
            final["broadcast"] = True
            overrides.append("hazard_broadcast")

    # C. Never lower risk than the rules for this message.
    if RISK_ORDER[final["risk_level"]] < RISK_ORDER[rules["risk_level"]]:
        final["risk_level"] = rules["risk_level"]
        overrides.append("risk_floor")

    # D. If the rules broadcast to everyone, the LLM may not silence it.
    if rules["broadcast"] and not final["broadcast"] and rules["risk_level"] == "high":
        final["broadcast"] = True
        overrides.append("broadcast_floor")

    if final["broadcast"] and final["target_drone"] == "none":
        final["target_drone"] = "all"
        overrides.append("target_fixed")

    return final, overrides
