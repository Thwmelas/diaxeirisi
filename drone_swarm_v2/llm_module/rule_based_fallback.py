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

HAZARDS = {"fire", "smoke"}
OBSTACLES = {"tree", "building", "car", "vehicle", "truck", "bus", "boat", "airplane", "drone"}


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def rule_based_decision(message: Dict[str, Any]) -> Dict[str, Any]:
    obj = str(message.get("object") or "unknown").lower().strip()
    direction = str(message.get("direction") or "unknown").lower().strip()
    distance = _to_float(message.get("distance"))
    confidence = _to_float(message.get("confidence"))

    # 1. Collision risk first: a close object is dangerous whatever YOLO's confidence.
    if distance is not None:
        if distance <= EMERGENCY_DISTANCE_M:
            return {
                "risk_level": "high",
                "action": "emergency_stop",
                "recommendation": f"Critical object detected at {direction}. Stop immediately and hold position.",
                "broadcast": True,
                "target_drone": "all",
            }
        if distance <= CLOSE_DISTANCE_M:
            return {
                "risk_level": "high",
                "action": "avoid_obstacle",
                "recommendation": f"Obstacle close at {direction}. Reduce speed and change course.",
                "broadcast": True,
                "target_drone": "all",
            }

    # 2. If YOLO sends confidence and it is low, ask for verification.
    #    Missing confidence is NOT treated as low confidence.
    if confidence is not None and confidence < LOW_CONFIDENCE:
        return {
            "risk_level": "low",
            "action": "verify_detection",
            "recommendation": "Detection confidence is low. Request confirmation from nearby drones.",
            "broadcast": True,
            "target_drone": "all",
        }

    # 3. Object-based decision (the current MQTT pipeline has no distance).
    if obj in HAZARDS:
        return {
            "risk_level": "high",
            "action": "notify_swarm",
            "recommendation": f"{obj} detected. Notify the swarm and send one drone to inspect the area.",
            "broadcast": True,
            "target_drone": "all",
        }

    if obj == "person":
        return {
            "risk_level": "high",
            "action": "track_person",
            "recommendation": "Person detected. Keep safe distance and notify nearby drones.",
            "broadcast": True,
            "target_drone": "all",
        }

    if obj in OBSTACLES:
        return {
            "risk_level": "medium",
            "action": "update_awareness_map",
            "recommendation": f"{obj} detected. Update shared map and maintain safe distance.",
            "broadcast": True,
            "target_drone": "all",
        }

    return {
        "risk_level": "low",
        "action": "continue_mission",
        "recommendation": "No critical risk detected. Continue mission and monitor surroundings.",
        "broadcast": False,
        "target_drone": "none",
    }
