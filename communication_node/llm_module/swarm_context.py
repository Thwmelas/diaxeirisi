"""Swarm context: turn recent messages into a short summary for the LLM prompt.

The decision node receives messages from ALL drones (drones/+/obstacles), so the
LLM can see whether other drones reported the same thing nearby.
Locations from Gazebo are [x, y, z] in metres, so Euclidean distance is used.
A 4-value location is a YOLO bounding box and has no world position.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional


def parse_time(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def world_position(message: Dict[str, Any]) -> Optional[List[float]]:
    loc = message.get("location")
    if isinstance(loc, (list, tuple)) and len(loc) == 3:
        try:
            return [float(v) for v in loc]
        except (TypeError, ValueError):
            return None
    return None


def distance_between(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[float]:
    pa, pb = world_position(a), world_position(b)
    if pa is None or pb is None:
        return None
    return math.dist(pa[:2], pb[:2])  # ground distance, ignore altitude


def summarize_history(history: List[Dict[str, Any]], current: Dict[str, Any],
                      max_age_s: float = 60.0, limit: int = 8) -> str:
    """Most-recent-first summary of earlier messages (excluding the current one)."""
    now = parse_time(current.get("timestamp"))
    lines = []
    for msg in reversed(history):
        if msg is current:
            continue
        ts = parse_time(msg.get("timestamp"))
        age = None if (now is None or ts is None) else now - ts
        if age is not None and age > max_age_s:
            continue
        who = msg.get("drone_id", "?")
        if who == current.get("drone_id"):
            who += " (same drone)"
        line = f"- {who}: {msg.get('object', 'unknown')}"
        if msg.get("distance") is not None:
            line += f" at {msg['distance']:g} m"
        if msg.get("direction") not in (None, "unknown"):
            line += f" {msg['direction']}"
        if msg.get("confidence") is not None:
            line += f" (confidence {msg['confidence']:.2f})"
        gap = distance_between(current, msg)
        if gap is not None:
            line += f", {gap:.0f} m from the current report"
        if age is not None:
            line += f", {age:.0f} s ago"
        lines.append(line)
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else "No recent reports."
