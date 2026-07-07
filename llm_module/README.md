# LLM Decision-Making Module

This module is the LLM / decision-making part of the drone swarm project.

It receives MQTT alerts produced by the perception/YOLO pipeline and returns a structured decision in JSON format.

## Input example from MQTT

```json
{
  "drone_id": "drone_1",
  "object": "fire",
  "location": [120, 80, 420, 500],
  "size": [300, 420],
  "velocity": [0, 0, 0]
}
```

The module also supports older/classic messages with `distance`, `direction` and `confidence`.

## Output example

```json
{
  "risk_level": "high",
  "action": "notify_swarm",
  "recommendation": "fire detected. Notify the swarm and send one drone to inspect the area.",
  "broadcast": true,
  "target_drone": "all",
  "decision_source": "rule_based_fallback"
}
```

## How it connects to MQTT

`communication_node/llm_decision_node.py` listens to:

```text
drones/+/obstacles
```

and publishes decisions to:

```text
swarm/decisions
```

## Why fallback is used

A real LLM can be slow or unavailable during a live demo. The rule-based fallback guarantees that the module always returns valid JSON and the system keeps working.

## How to test locally

```bash
cd communication_node/llm_module
python3 test_scenarios.py
```

## Presentation explanation

My module receives structured detection messages from the MQTT communication layer, normalizes the input, evaluates the situation and returns a decision in JSON format. The decision includes risk level, action, recommendation and whether the alert should be broadcast to the swarm.
