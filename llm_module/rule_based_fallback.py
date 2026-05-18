"""Safe deterministic fallback for LLM Decision-Making Module."""
from __future__ import annotations
from typing import Any, Dict

def rule_based_decision(message: Dict[str, Any]) -> Dict[str, Any]:
    obj = str(message.get("object", "unknown")).lower().strip()
    direction = str(message.get("direction", "unknown")).lower().strip()
    try: distance = float(message.get("distance", 999))
    except (TypeError, ValueError): distance = 999.0
    try: confidence = float(message.get("confidence", 0.0))
    except (TypeError, ValueError): confidence = 0.0

    if confidence < 0.50:
        return {"risk_level": "low", "action": "verify_detection", "recommendation": "Detection confidence is low. Request confirmation from nearby drones.", "broadcast": True, "target_drone": "all"}
    if distance <= 5:
        return {"risk_level": "high", "action": "emergency_stop", "recommendation": f"Critical object detected at {direction}. Stop immediately and hold position.", "broadcast": True, "target_drone": "all"}
    if distance <= 10:
        return {"risk_level": "high", "action": "avoid_obstacle", "recommendation": f"Obstacle close at {direction}. Reduce speed and change course.", "broadcast": True, "target_drone": "all"}
    if obj in {"person", "fire", "smoke"}:
        return {"risk_level": "high", "action": "notify_swarm", "recommendation": f"{obj} detected. Notify swarm and assign one drone to inspect.", "broadcast": True, "target_drone": "all"}
    if obj in {"tree", "building", "car", "vehicle", "boat", "airplane", "drone"}:
        return {"risk_level": "medium", "action": "update_awareness_map", "recommendation": f"{obj} detected. Update shared map and maintain safe distance.", "broadcast": True, "target_drone": "all"}
    return {"risk_level": "low", "action": "continue_mission", "recommendation": "No critical risk detected. Continue mission and monitor surroundings.", "broadcast": False, "target_drone": "none"}
