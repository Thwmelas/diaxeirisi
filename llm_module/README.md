# LLM Decision-Making Module

Αυτός ο φάκελος είναι η υλοποίηση του δικού μου μέρους: **LLM-based Inter-Drone Communication & Decision-Making**.

Το module δέχεται structured μηνύματα από drones, τα ερμηνεύει και επιστρέφει απόφαση σε JSON μορφή.

## Input example

```json
{
  "drone_id": "drone_1",
  "object": "tree",
  "distance": 8,
  "direction": "front",
  "confidence": 0.89,
  "location": [34.5, -118.2, 15.0]
}
```

## Output example

```json
{
  "risk_level": "high",
  "action": "avoid_obstacle",
  "recommendation": "Obstacle close at front. Reduce speed and change course.",
  "broadcast": true,
  "target_drone": "all"
}
```

## Files

```text
llm_decision_module/
├── llm_decision.py
├── rule_based_fallback.py
├── test_scenarios.py
├── mqtt_integration_example.py
├── optional_hf_client.py
├── drone_llm_examples.jsonl
├── requirements.txt
└── README.md
```

## How to run

```bash
python test_scenarios.py
```

## How another teammate can use it

```python
from llm_decision import interpret_drone_message

message = {
    "drone_id": "drone_1",
    "object": "tree",
    "distance": 8,
    "direction": "front",
    "confidence": 0.89
}

decision = interpret_drone_message(message)
print(decision)
```

## MQTT connection

The MQTT teammate can pass received messages directly to this module:

```python
import json
from llm_decision import interpret_drone_message

data = json.loads(msg.payload.decode("utf-8"))
decision = interpret_drone_message(data)
```

## Why fallback exists

A real LLM can be slow, unavailable, or return invalid JSON. The fallback makes sure the system always returns a valid and safe decision.

## Presentation text

Το δικό μου κομμάτι είναι το LLM-based decision-making module. Το module λαμβάνει μηνύματα από drones σε JSON μορφή, όπως το αντικείμενο που εντοπίστηκε, την απόσταση, την κατεύθυνση και το confidence score. Στη συνέχεια, το μήνυμα μετατρέπεται σε prompt για LLM και το σύστημα επιστρέφει απόφαση σε JSON μορφή με risk level, action, recommendation και broadcast flag. Για λόγους αξιοπιστίας υλοποιήθηκε και rule-based fallback, ώστε το σύστημα να συνεχίζει να λειτουργεί ακόμη και αν το LLM δεν απαντήσει σωστά. Έτσι το module είναι έτοιμο για σύνδεση με το MQTT και το υπόλοιπο drone swarm pipeline.
