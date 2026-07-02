"""MQTT -> LLM Decision -> MQTT node.

This is the integration point for the LLM part of the project.
It listens to obstacle alerts from drones and publishes decision JSON.

Run:
    cd communication_node
    python3 llm_decision_node.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

# Import local llm_module/ without installing it as a package.
LLM_MODULE_PATH = Path(__file__).resolve().parent / "llm_module"
sys.path.insert(0, str(LLM_MODULE_PATH))

from llm_decision import LLMDecisionMaker  # noqa: E402

BROKER = "localhost"
PORT = 1883
ALERT_TOPIC = "drones/+/obstacles"
DECISION_TOPIC = "swarm/decisions"
LOG_FILE = Path(__file__).resolve().parent / "decisions.log"

decision_maker = LLMDecisionMaker(drone_id="llm_decision_node", use_llm=False, keep_history=True)


def log_decision(decision: dict[str, Any]) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {json.dumps(decision, ensure_ascii=False)}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(line)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[LLM Node] Connected to MQTT broker")
        client.subscribe(ALERT_TOPIC)
        print(f"[LLM Node] Subscribed to {ALERT_TOPIC}")
    else:
        print(f"[LLM Node] Connection failed: {reason_code}")


def on_message(client, userdata, msg):
    try:
        alert = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[LLM Node] Ignored invalid JSON from topic {msg.topic}")
        return

    decision = decision_maker.interpret(alert)

    # Add traceability fields so we can explain interoperability in the presentation.
    decision["source_topic"] = msg.topic
    decision["source_drone"] = alert.get("drone_id", "unknown")
    decision["detected_object"] = alert.get("object", "unknown")
    decision["input_location"] = alert.get("location")

    log_decision(decision)
    client.publish(DECISION_TOPIC, json.dumps(decision), qos=0)

    print(
        "[LLM Decision] "
        f"drone={decision['source_drone']} "
        f"object={decision['detected_object']} "
        f"risk={decision['risk_level']} "
        f"action={decision['action']} "
        f"-> published to {DECISION_TOPIC}"
    )


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    print("LLM Decision Node waiting for drone alerts...")
    client.loop_forever()


if __name__ == "__main__":
    main()
