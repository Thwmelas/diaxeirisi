"""Rule-based fallback for the LLM Decision-Making Module.

This fallback is used when a real LLM is not connected or when the LLM
returns invalid output. It keeps the demo deterministic and safe.
"""
from __future__ import annotations
from typing import Any, Dict, Optional


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def rule_based_decision(message: Dict[str, Any]) -> Dict[str, Any]:
    obj = str(message.get("object", "unknown")).lower().strip()
    direction = str(message.get("direction", "unknown")).lower().strip()
    distance = _to_float(message.get("distance"))
    confidence = _to_float(message.get("confidence"))

    # If YOLO sends confidence and it is low, ask for verification.
    # If confidence is missing, we do not treat it as low confidence.
    if confidence is not None and confidence < 0.50:
        return {
            "risk_level": "low",
            "action": "verify_detection",
            "recommendation": "Detection confidence is low. Request confirmation from nearby drones.",
            "broadcast": True,
            "target_drone": "all",
        }

    # If distance exists, use it for safety decisions.
    if distance is not None:
        if distance <= 5:
            return {
                "risk_level": "high",
                "action": "emergency_stop",
                "recommendation": f"Critical object detected at {direction}. Stop immediately and hold position.",
                "broadcast": True,
                "target_drone": "all",
            }
        if distance <= 10:
            return {
                "risk_level": "high",
                "action": "avoid_obstacle",
                "recommendation": f"Obstacle close at {direction}. Reduce speed and change course.",
                "broadcast": True,
                "target_drone": "all",
            }

    # Object-based decision when distance is not available from the current pipeline.
    if obj in {"fire", "smoke"}:
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

    if obj in {"tree", "building", "car", "vehicle", "boat", "airplane", "drone"}:
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
