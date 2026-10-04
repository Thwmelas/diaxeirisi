# LLM Decision-Making Module

This module is the LLM / decision-making part of the drone swarm project.

It receives MQTT alerts produced by the perception/YOLO pipeline and returns a structured decision in JSON format.
A local LLM (served by **Ollama**) interprets each alert **together with recent alerts from the other drones**,
a safety layer makes sure the LLM can never weaken a hard safety rule, and a rule-based fallback guarantees
a valid decision even when the LLM is off, slow or wrong.

## Pipeline

```text
MQTT alert ─► normalize ─► prompt (+ recent swarm alerts) ─► LLM (Ollama) ─► validate ─► safety layer ─► decision
                                                                 │               │
                                                                 └──── error ────┴──► rule-based fallback ─► decision
```

## Files

| File | Purpose |
|---|---|
| `llm_decision.py` | `LLMDecisionMaker` and `interpret_drone_message` (public API, unchanged) |
| `rule_based_fallback.py` | Deterministic rules: fallback and safety reference |
| `schema.py` | Allowed risk levels / actions, JSON parsing and validation of LLM output |
| `safety.py` | Corrects LLM decisions that are less safe than the rules |
| `swarm_context.py` | Summarises recent alerts (with distance between drones) for the prompt |
| `llm_client.py` | Ollama client (Python standard library only) |
| `scenarios.py` | 17 scenarios with expected outcomes |
| `test_scenarios.py` | Prints the decision for every scenario |
| `evaluate.py` | Rules vs LLM models, writes result tables to `results/` |
| `test_llm_module.py` | Unit tests (no LLM needed) |

## Input example from MQTT

```json
{
  "drone_id": "drone_1",
  "object": "fire",
  "location": [10.5, 3.2, 12.0],
  "size": [2.0, 2.0],
  "velocity": [0, 0, 0]
}
```

`location` can be world coordinates `[x, y, z]` (Gazebo) or a YOLO box `[x1, y1, x2, y2]`
(direction is then estimated from the box). Messages from `drone_integration.py` with
`distance`, `direction` and `confidence` are also supported, as well as the swarm-v2 format with
`count` (how many objects of that class are in the frame). YOLO class names such as
`heavy vehicles` / `buildings` are normalised (`heavy_vehicle`, `building`). Missing fields are fine.

## Output example

```json
{
  "description": "The drone sees a crowd of about 60 people on the left.",
  "risk_level": "high",
  "action": "notify_swarm",
  "recommendation": "Fire confirmed by two nearby drones. Alert the swarm and send one drone to inspect.",
  "broadcast": true,
  "target_drone": "all",
  "decision_source": "llm",
  "llm_latency_ms": 840.2,
  "decision_time": "2026-07-10T12:00:30+00:00",
  "module_id": "llm_decision_node"
}
```

- `description`: one English sentence describing what the drone sees, built only from the report data
  (the LLM does not see the image). It is checked against the report (object, count, direction, no
  invented distance); if it contradicts it, the factual rule-based description is used instead and
  the LLM's text is kept in `description_rejected`. Rule-based decisions also include one.
- `action`: `emergency_stop`, `avoid_obstacle`, `notify_swarm`, `track_person`, `hover_and_monitor`,
  `verify_detection`, `update_awareness_map`, `continue_mission`
- `decision_source`: `llm` | `llm+safety` (corrected, see `safety_overrides`) | `rule_based_fallback` (see `fallback_reason` if the LLM failed)

## Setup for the LLM (optional)

```bash
# install Ollama: https://ollama.com/download  (on WSL/Linux:)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
```

No extra Python package is needed. Without Ollama everything still works with the rules.

## How to run

```bash
cd communication_node
python3 llm_decision_node.py            # rules only (stable live demo)
python3 llm_decision_node.py --llm      # with the LLM
python3 llm_decision_node.py --llm --model qwen2.5:3b
```

`llm_decision_node.py` listens to `drones/+/obstacles` and publishes decisions to `swarm/decisions`.

`perception_node/drone_integration.py` calls `interpret_drone_message()`; to make it use the LLM
without changing its code: `export DRONE_USE_LLM=1` before starting it.

## How to test locally

```bash
cd communication_node/llm_module
python3 test_scenarios.py              # rules
python3 test_scenarios.py --llm        # LLM
python3 -m pytest test_llm_module.py   # unit tests
python3 evaluate.py --models llama3.2:3b qwen2.5:3b   # table for the report
```

## Results (rules only)

| Engine | Accuracy | Swarm-context accuracy |
|---|---|---|
| rules | 88% (15/17) | 33% (1/3) |

The rules fail only where another drone's report changes the right answer
(e.g. an uncertain fire detection that two nearby drones already confirmed).
This is the gap the LLM closes. Run `evaluate.py` to add the LLM rows.

### Lesson from the first LLM evaluation

With only output validation, both 3B models scored **71%**, worse than the rules:
llama3.2:3b asked for `emergency_stop` when nothing was close (e.g. a car 40 m away), qwen2.5:3b
answered `continue_mission` for smoke and `track_person` for a kite. Both still solved some of the
swarm-confirmation cases the rules miss. This led to the guardrails above (allowed actions per message,
evidence-gated escalation). Replaying the same model answers through the guardrails gives 16/17 for
both models. Small LLMs are useful for context reasoning but must be constrained.

## Design choices

- **Hybrid LLM + rules**: the LLM reasons over swarm context; the rules guarantee predictable, safe behaviour.
- **Allowed actions per message**: only actions that make sense for the input are offered to the LLM
  and sent to Ollama as the schema enum (e.g. `emergency_stop` only if an object is closer than 10 m,
  `track_person` only for a person), so the model cannot even generate the others.
- **The LLM never weakens a hard rule**: an obstacle at 4 m is always `emergency_stop`, fire is always broadcast.
- **Escalation needs evidence**: the LLM may raise risk above the rules only if another drone recently
  reported the same kind of object within 50 m, and only fire, smoke and people can reach `high`
  (vehicles, trees... stop at `medium`). If the risk is reset, the reaction is reset too, so a decision is
  never "low risk + alert the swarm". Every correction is logged in `safety_overrides`.
- **Short prompt with a static prefix** (~350 tokens, was ~600): the unchanging instructions come first so
  Ollama can reuse its cache; only the history, the report and the allowed actions change. Output is
  capped at 120 tokens (`num_predict`).
- **Structured output**: a JSON schema is sent to Ollama and the answer is validated again in Python
  (closed set of actions, real booleans, valid `target_drone`).
- **Distance before confidence**: a close object is never ignored because YOLO was unsure.
- **Always available**: network errors, timeouts or invalid answers fall back to the rules.
- **Local model**: no cloud, no data leaves the system.

## Presentation explanation

My module receives structured detection messages from the MQTT communication layer, normalizes the input,
and asks a local LLM to decide, giving it the recent alerts from the whole swarm so it can recognise when
several drones see the same event. The LLM's answer is validated and checked against safety rules, and if
the LLM is unavailable a rule-based fallback takes over, so the system always returns a valid JSON decision:
risk level, action, recommendation, whether to broadcast, and which drone it is for.
