"""LLM Decision-Making Module for AI-Enabled Drone Swarm Project."""
from __future__ import annotations
import json, re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from rule_based_fallback import rule_based_decision

Decision = Dict[str, Any]
DroneMessage = Dict[str, Any]

@dataclass
class LLMDecisionMaker:
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
            raw = self.llm_client(prompt)
            parsed = self.parse_llm_json(raw)
            validated = self.validate_decision(parsed)
            return self._with_metadata(validated, "llm")
        except Exception as exc:
            fallback = rule_based_decision(normalized)
            fallback["fallback_reason"] = str(exc)
            return self._with_metadata(fallback, "rule_based_fallback")

    def build_prompt(self, message: DroneMessage) -> str:
        history_text = json.dumps(self.history[-self.max_history_items:], indent=2)
        return f"""
You are an AI decision-making module for a drone swarm.
Return ONLY valid JSON. No markdown, no explanations.
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
        required = ["risk_level", "action", "recommendation", "broadcast", "target_drone"]
        for key in required:
            if key not in decision:
                raise ValueError(f"Missing required field: {key}")
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
        normalized = dict(message)
        normalized.setdefault("drone_id", "unknown_drone")
        normalized.setdefault("object", "unknown")
        normalized.setdefault("distance", 999)
        normalized.setdefault("direction", "unknown")
        normalized.setdefault("confidence", 0.0)
        normalized.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        try: normalized["distance"] = float(normalized["distance"])
        except (TypeError, ValueError): normalized["distance"] = 999.0
        try: normalized["confidence"] = float(normalized["confidence"])
        except (TypeError, ValueError): normalized["confidence"] = 0.0
        normalized["object"] = str(normalized["object"]).lower().strip()
        normalized["direction"] = str(normalized["direction"]).lower().strip()
        return normalized

    def _update_history(self, message: DroneMessage) -> None:
        self.history.append(message)
        self.history = self.history[-self.max_history_items:]

    def _with_metadata(self, decision: Decision, source: str) -> Decision:
        decision["decision_source"] = source
        decision["decision_time"] = datetime.now(timezone.utc).isoformat()
        decision["module_id"] = self.drone_id
        return decision

def interpret_drone_message(message: DroneMessage, use_llm: bool = False, llm_client: Optional[Any] = None) -> Decision:
    return LLMDecisionMaker(use_llm=use_llm, llm_client=llm_client).interpret(message)
