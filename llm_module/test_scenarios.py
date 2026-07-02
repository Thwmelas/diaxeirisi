"""Run local tests for the LLM decision module.

Usage:
    cd communication_node/llm_module
    python3 test_scenarios.py
"""
from __future__ import annotations

import json
from llm_decision import LLMDecisionMaker

TEST_SCENARIOS = [
    {
        "name": "Fire detection from Gazebo pipeline",
        "message": {
            "drone_id": "drone_1",
            "object": "fire",
            "location": [120, 80, 420, 500],
            "size": [300, 420],
            "velocity": [0, 0, 0],
        },
    },
    {
        "name": "Tree detection from YOLO bbox",
        "message": {
            "drone_id": "drone_2",
            "object": "tree",
            "location": [600, 100, 900, 700],
            "size": [300, 600],
            "velocity": [0, 0, 0],
        },
    },
    {
        "name": "Classic message with distance",
        "message": {
            "drone_id": "drone_3",
            "object": "building",
            "distance": 4,
            "direction": "front",
            "confidence": 0.95,
        },
    },
    {
        "name": "Low confidence detection",
        "message": {
            "drone_id": "drone_4",
            "object": "car",
            "distance": 20,
            "direction": "left",
            "confidence": 0.35,
        },
    },
]


def main() -> None:
    decision_maker = LLMDecisionMaker(drone_id="llm_test", use_llm=False, keep_history=True)
    results = []
    for scenario in TEST_SCENARIOS:
        results.append(
            {
                "scenario": scenario["name"],
                "input": scenario["message"],
                "decision": decision_maker.interpret(scenario["message"]),
            }
        )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
