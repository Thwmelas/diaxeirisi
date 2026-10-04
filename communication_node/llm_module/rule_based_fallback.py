"""Rule-based fallback for the LLM Decision-Making Module.

Used when a real LLM is not connected or returns invalid output, and as the
reference for the safety layer (safety.py). Keeps the demo deterministic and safe.

Order of checks matters: distance (collision) is checked BEFORE confidence,
so a very close object is never ignored just because YOLO was unsure.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

EMERGENCY_DISTANCE_M = 5.0
CLOSE_DISTANCE_M = 10.0
LOW_CONFIDENCE = 0.50
CROWD_SIZE = 5          # this many people or more = a crowd

HAZARDS = {"fire", "smoke"}
OBSTACLES = {"tree", "building", "car", "vehicle", "truck", "bus", "heavy_vehicle", "light_vehicle",
             "motorcycle", "bicycle", "boat", "plane", "airplane", "drone"}

# YOLO class names -> one canonical name (the team's model merged some classes).
ALIASES = {
    "heavy_vehicles": "heavy_vehicle", "heavy vehicles": "heavy_vehicle", "heavy vehicle": "heavy_vehicle",
    "light_vehicles": "light_vehicle", "light vehicles": "light_vehicle", "light vehicle": "light_vehicle",
    "buildings": "building", "trees": "tree", "cars": "car", "boats": "boat", "planes": "plane",
    "persons": "person", "people": "person", "pedestrian": "person",
}

# Human-readable (singular, plural) names for descriptions.
LABELS = {"person": ("person", "people"), "heavy_vehicle": ("heavy vehicle", "heavy vehicles"),
          "light_vehicle": ("light vehicle", "light vehicles"), "bus": ("bus", "buses")}


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def object_name(value: Any) -> str:
    name = str(value or "unknown").lower().strip()
    name = ALIASES.get(name, name)
    return name.replace(" ", "_").replace("-", "_")


def object_count(message: Dict[str, Any]) -> int:
    try:
        return max(1, int(message.get("count") or 1))
    except (TypeError, ValueError):
        return 1


def describe(message: Dict[str, Any]) -> str:
    """One factual English sentence built ONLY from the report fields."""
    obj, count = object_name(message.get("object")), object_count(message)
    if obj == "unknown":
        return "The drone does not detect any recognisable object."
    singular, plural = LABELS.get(obj, (obj.replace("_", " "), obj.replace("_", " ") + "s"))
    if count == 1:
        what = ("an " if singular[0] in "aeiou" else "a ") + singular
    elif obj == "person" and count >= CROWD_SIZE:
        what = f"a crowd of about {count} people"
    else:
        what = f"{count} {plural}"
    text = f"The drone sees {what}"
    confidence = _to_float(message.get("confidence"))
    if confidence is not None and confidence < LOW_CONFIDENCE:
        text = f"The drone possibly sees {what}"
    direction = str(message.get("direction") or "unknown").lower()
    if direction in ("left", "right"):
        text += f" on the {direction}"
    elif direction in ("front", "back", "above", "below"):
        text += {"front": " in front", "back": " behind", "above": " above", "below": " below"}[direction]
    distance = _to_float(message.get("distance"))
    if distance is not None:
        text += f", about {distance:g} m away"
    return text + "."


def _decision(risk, action, recommendation, broadcast, target, message):
    return {"description": describe(message), "risk_level": risk, "action": action,
            "recommendation": recommendation, "broadcast": broadcast, "target_drone": target}


def rule_based_decision(message: Dict[str, Any]) -> Dict[str, Any]:
    obj = object_name(message.get("object"))
    direction = str(message.get("direction") or "unknown").lower().strip()
    distance = _to_float(message.get("distance"))
    confidence = _to_float(message.get("confidence"))
    count = object_count(message)

    # 1. Collision risk first: a close object is dangerous whatever YOLO's confidence.
    if distance is not None:
        if distance <= EMERGENCY_DISTANCE_M:
            return _decision("high", "emergency_stop",
                             f"Critical object detected at {direction}. Stop immediately and hold position.",
                             True, "all", message)
        if distance <= CLOSE_DISTANCE_M:
            return _decision("high", "avoid_obstacle",
                             f"Obstacle close at {direction}. Reduce speed and change course.",
                             True, "all", message)

    # 2. If YOLO sends confidence and it is low, ask for verification.
    #    Missing confidence is NOT treated as low confidence.
    if confidence is not None and confidence < LOW_CONFIDENCE:
        return _decision("low", "verify_detection",
                         "Detection confidence is low. Request confirmation from nearby drones.",
                         True, "all", message)

    # 3. Object-based decision (videos have no depth, so usually no distance).
    if obj in HAZARDS:
        return _decision("high", "notify_swarm",
                         f"{obj} detected. Notify the swarm and send one drone to inspect the area.",
                         True, "all", message)

    if obj == "person":
        if count >= CROWD_SIZE:
            return _decision("high", "hover_and_monitor",
                             f"Crowd of {count} people. Hold position, monitor and keep safe altitude.",
                             True, "all", message)
        return _decision("high", "track_person",
                         "Person detected. Keep safe distance and notify nearby drones.",
                         True, "all", message)

    if obj in OBSTACLES:
        label = obj.replace("_", " ")
        return _decision("medium", "update_awareness_map",
                         f"{label} detected. Update shared map and maintain safe distance.",
                         True, "all", message)

    return _decision("low", "continue_mission",
                     "No critical risk detected. Continue mission and monitor surroundings.",
                     False, "none", message)
