"""Run: python test_scenarios.py"""
from __future__ import annotations
import json
from llm_decision import LLMDecisionMaker

TEST_SCENARIOS = [
    {"name": "Close tree obstacle", "message": {"drone_id": "drone_1", "object": "tree", "distance": 8, "direction": "front", "confidence": 0.89, "location": [34.5, -118.2, 15.0]}},
    {"name": "Person detected", "message": {"drone_id": "drone_2", "object": "person", "distance": 25, "direction": "left", "confidence": 0.94}},
    {"name": "Very close building", "message": {"drone_id": "drone_3", "object": "building", "distance": 4, "direction": "front", "confidence": 0.97}},
    {"name": "Low confidence car", "message": {"drone_id": "drone_1", "object": "car", "distance": 18, "direction": "right", "confidence": 0.42}},
    {"name": "Smoke detected", "message": {"drone_id": "drone_4", "object": "smoke", "distance": 40, "direction": "north", "confidence": 0.86}}
]

def main():
    dm = LLMDecisionMaker(drone_id="llm_decision_module", use_llm=False, keep_history=True)
    results=[]
    for scenario in TEST_SCENARIOS:
        results.append({"scenario": scenario["name"], "input": scenario["message"], "decision": dm.interpret(scenario["message"])})
    print(json.dumps(results, indent=2))

if __name__ == "__main__": main()
