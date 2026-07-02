"""LLM Decision-Making Module for AI-Enabled Drone Swarm Project.

The module receives MQTT/YOLO alerts as Python dictionaries and returns
a structured JSON-compatible decision.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from rule_based_fallback import rule_based_decision

Decision = Dict[str, Any]
DroneMessage = Dict[str, Any]


@dataclass
class LLMDecisionMaker:
    """Interprets drone messages and produces decisions.

    use_llm=False is used for the live student demo so the output is stable.
    If a real LLM client is connected later, set use_llm=True and provide
    llm_client(prompt) -> response_text.
    """

    drone_id: str = "llm_module"
    use_llm: bool = False
    llm_client: Optional[Any] = None
    keep_history: bool = True
    max_history_items: int = 5
    history: List[DroneMessage] = field(default_factory=list)

    def interpret(self, message: DroneMessage) -> Decision:
        normalized = self._normalize_message(message)

        if self.keep_history:
            self._update_history(normalized)

        if not self.use_llm or self.llm_client is None:
            return self._with_metadata(rule_based_decision(normalized), "rule_based_fallback")

        prompt = self.build_prompt(normalized)
        try:
            raw_response = self.llm_client(prompt)
            parsed = self.parse_llm_json(raw_response)
            validated = self.validate_decision(parsed)
            return self._with_metadata(validated, "llm")
        except Exception as exc:
            fallback = rule_based_decision(normalized)
            fallback["fallback_reason"] = str(exc)
            return self._with_metadata(fallback, "rule_based_fallback")

    def build_prompt(self, message: DroneMessage) -> str:
        history_text = json.dumps(self.history[-self.max_history_items :], indent=2)
        return f"""
You are an AI decision-making module for a drone swarm.
Return ONLY valid JSON. No markdown, no explanations.

Mission context:
- YOLO detects objects from drone camera frames.
- MQTT transfers only processed JSON messages, not raw images.
- The decision output must be usable by the rest of the swarm.

Recent swarm message history:
{history_text}

Current drone message:
{json.dumps(message, indent=2)}

Return exactly this JSON schema:
{{
  "risk_level": "low | medium | high",
  "action": "short_action_name",
  "recommendation": "short actionable command",
  "broadcast": true,
  "target_drone": "all | drone_id | none"
}}
""".strip()

    @staticmethod
    def parse_llm_json(raw_response: str) -> Decision:
        if not isinstance(raw_response, str):
            raise ValueError("LLM response is not a string")

        raw_response = raw_response.strip()
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", raw_response, flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in LLM response")
        return json.loads(match.group(0))

    @staticmethod
    def validate_decision(decision: Decision) -> Decision:
        required_fields = ["risk_level", "action", "recommendation", "broadcast", "target_drone"]
        for field_name in required_fields:
            if field_name not in decision:
                raise ValueError(f"Missing required field: {field_name}")

        risk = str(decision["risk_level"]).lower().strip()
        if risk not in {"low", "medium", "high"}:
            raise ValueError(f"Invalid risk_level: {decision['risk_level']}")

        decision["risk_level"] = risk
        decision["action"] = str(decision["action"]).strip()
        decision["recommendation"] = str(decision["recommendation"]).strip()
        decision["broadcast"] = bool(decision["broadcast"])
        decision["target_drone"] = str(decision["target_drone"]).strip()
        return decision

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

        Older test cases may also send distance, direction and confidence.
        This function supports both formats.
        """
        normalized = dict(message)
        normalized.setdefault("drone_id", "unknown_drone")
        normalized.setdefault("object", "unknown")
        normalized.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        normalized["object"] = str(normalized.get("object", "unknown")).lower().strip()

        # Keep confidence optional. Missing confidence is not the same as low confidence.
        if "confidence" in normalized:
            try:
                normalized["confidence"] = float(normalized["confidence"])
            except (TypeError, ValueError):
                normalized["confidence"] = None
        else:
            normalized["confidence"] = None

        # Distance is optional in the current Gazebo/MQTT pipeline.
        if "distance" in normalized:
            try:
                normalized["distance"] = float(normalized["distance"])
            except (TypeError, ValueError):
                normalized["distance"] = None
        else:
            normalized["distance"] = None

        location = normalized.get("location")
        bbox = normalized.get("bbox")

        # If location looks like YOLO bbox [x1, y1, x2, y2], also expose it as bbox.
        if bbox is None and isinstance(location, list) and len(location) == 4:
            bbox = location
            normalized["bbox"] = bbox

        # Direction can be explicitly provided or estimated from bbox center.
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

    def _update_history(self, message: DroneMessage) -> None:
        self.history.append(message)
        self.history = self.history[-self.max_history_items :]

    def _with_metadata(self, decision: Decision, source: str) -> Decision:
        decision["decision_source"] = source
        decision["decision_time"] = datetime.now(timezone.utc).isoformat()
        decision["module_id"] = self.drone_id
        return decision


def interpret_drone_message(
    message: DroneMessage,
    use_llm: bool = False,
    llm_client: Optional[Any] = None,
) -> Decision:
    return LLMDecisionMaker(use_llm=use_llm, llm_client=llm_client).interpret(message)


if __name__ == "__main__":
    sample = {
        "drone_id": "drone_1",
        "object": "fire",
        "location": [120, 80, 420, 500],
        "size": [300, 420],
        "velocity": [0, 0, 0],
    }
    print(json.dumps(interpret_drone_message(sample), indent=2))
