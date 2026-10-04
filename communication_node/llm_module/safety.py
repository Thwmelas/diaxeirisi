"""Safety layer / guardrails around the LLM.

1. Allowed actions per message: the LLM can only choose actions that make
   sense for this input (emergency_stop only if an object is close,
   track_person only for a person...). The same set is sent to Ollama as the
   JSON-schema enum, so the model cannot even generate the others.
2. The LLM may never WEAKEN a hard rule (lower risk, silence a fire alert...).
3. The LLM may ESCALATE risk above the rules only with evidence: another drone
   recently reported the same kind of object nearby. Even then, only fire,
   smoke and people can reach "high"; ordinary objects (vehicles, trees...)
   stop at "medium".
4. When the risk is reset to the rules, the reaction (action, broadcast,
   target) is reset too, so we never publish e.g. "low risk + notify_swarm".
The LLM's description of the scene is always kept.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from rule_based_fallback import (
    CLOSE_DISTANCE_M, EMERGENCY_DISTANCE_M, HAZARDS, LOW_CONFIDENCE, _to_float, object_name, rule_based_decision,
)
from schema import ACTIONS, RISK_ORDER
from swarm_context import distance_between, parse_time

COLLISION_ACTIONS = {"emergency_stop", "avoid_obstacle"}
ALERT_ACTIONS = {"notify_swarm", "hover_and_monitor", "track_person"}
CAN_BE_HIGH = HAZARDS | {"person"}
EVIDENCE_RADIUS_M = 50.0
EVIDENCE_MAX_AGE_S = 60.0


def allowed_actions(message: Dict[str, Any]) -> List[str]:
    """Actions that are consistent with this message (order kept from ACTIONS)."""
    distance = _to_float(message.get("distance"))
    confidence = _to_float(message.get("confidence"))
    obj = object_name(message.get("object"))

    if distance is not None and distance <= EMERGENCY_DISTANCE_M:
        allowed: Set[str] = {"emergency_stop"}
    elif distance is not None and distance <= CLOSE_DISTANCE_M:
        allowed = {"emergency_stop", "avoid_obstacle"}
    else:
        allowed = set(ACTIONS) - COLLISION_ACTIONS
        if obj != "person":
            allowed.discard("track_person")
        if obj in HAZARDS and (confidence is None or confidence >= LOW_CONFIDENCE):
            allowed -= {"continue_mission", "update_awareness_map"}
    return [a for a in ACTIONS if a in allowed]


def _same_kind(a: str, b: str) -> bool:
    return a == b or (a in HAZARDS and b in HAZARDS)


def has_swarm_evidence(message: Dict[str, Any], history: Optional[Iterable[Dict[str, Any]]]) -> bool:
    """True if ANOTHER drone recently and reliably reported the same kind of object nearby."""
    if not history:
        return False
    obj, me = object_name(message.get("object")), message.get("drone_id")
    now = parse_time(message.get("timestamp"))
    for other in history:
        if other is message or other.get("drone_id") == me:
            continue
        if not _same_kind(obj, object_name(other.get("object"))):
            continue
        conf = _to_float(other.get("confidence"))
        if conf is not None and conf < LOW_CONFIDENCE:
            continue
        ts = parse_time(other.get("timestamp"))
        if now is not None and ts is not None and now - ts > EVIDENCE_MAX_AGE_S:
            continue
        gap = distance_between(message, other)
        if gap is not None and gap > EVIDENCE_RADIUS_M:
            continue
        return True
    return False


def _use_rules_reaction(final: Dict[str, Any], rules: Dict[str, Any]) -> None:
    for key in ("action", "recommendation", "broadcast", "target_drone"):
        final[key] = rules[key]


def apply_safety_override(
    message: Dict[str, Any],
    decision: Dict[str, Any],
    history: Optional[Iterable[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    rules = rule_based_decision(message)
    final = dict(decision)
    overrides: List[str] = []
    obj = object_name(message.get("object"))
    confidence = _to_float(message.get("confidence"))

    # 1. Action must be consistent with the input (in case the server ignored the schema).
    allowed = allowed_actions(message)
    if final["action"] not in allowed:
        final["action"] = rules["action"] if rules["action"] in allowed else allowed[0]
        final["recommendation"] = rules["recommendation"]
        overrides.append("action_not_allowed")

    # 2a. Never lower risk than the rules.
    if RISK_ORDER[final["risk_level"]] < RISK_ORDER[rules["risk_level"]]:
        final["risk_level"] = rules["risk_level"]
        overrides.append("risk_floor")

    # 2b. Confirmed fire/smoke, and every high-risk rule decision, must be broadcast.
    must_broadcast = (obj in HAZARDS and (confidence is None or confidence >= LOW_CONFIDENCE)) \
        or (rules["broadcast"] and rules["risk_level"] == "high")
    if must_broadcast and not final["broadcast"]:
        final["broadcast"] = True
        overrides.append("broadcast_required")

    # 3. Escalation above the rules needs evidence, and only some objects can be "high".
    if RISK_ORDER[final["risk_level"]] > RISK_ORDER[rules["risk_level"]]:
        if not has_swarm_evidence(message, history):
            final["risk_level"] = rules["risk_level"]
            _use_rules_reaction(final, rules)
            overrides.append("unsupported_escalation")
        elif final["risk_level"] == "high" and obj not in CAN_BE_HIGH:
            final["risk_level"] = "medium"
            if final["action"] in ALERT_ACTIONS:
                _use_rules_reaction(final, rules)
            overrides.append("escalation_capped")

    # 4. A low-risk decision must not alert the whole swarm (verify_detection may still ask others).
    if final["risk_level"] == "low" and final["action"] != "verify_detection" \
            and (final["action"] in ALERT_ACTIONS or final["broadcast"]):
        _use_rules_reaction(final, rules)
        if final["action"] != "verify_detection":
            final["broadcast"], final["target_drone"] = False, "none"
        overrides.append("low_risk_no_alert")

    if final["broadcast"] and final["target_drone"] == "none":
        final["target_drone"] = "all"
        overrides.append("target_fixed")

    return final, overrides
