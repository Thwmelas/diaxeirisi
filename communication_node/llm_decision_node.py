"""MQTT -> LLM Decision -> MQTT node.

This is the integration point for the LLM part of the project.
It listens to obstacle alerts from drones and publishes decision JSON.

Run:
    cd communication_node
    python3 llm_decision_node.py                 # rules only (stable demo)
    python3 llm_decision_node.py --llm           # local LLM via Ollama + safety layer
    python3 llm_decision_node.py --llm --model qwen2.5:3b

The node remembers the latest alerts from ALL drones, so with --llm the model
can see whether other drones reported the same thing nearby.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

# Import local llm_module/ without installing it as a package.
LLM_MODULE_PATH = Path(__file__).resolve().parent / "llm_module"
sys.path.insert(0, str(LLM_MODULE_PATH))

from llm_decision import LLMDecisionMaker, llm_enabled_from_env  # noqa: E402

BROKER = "localhost"
PORT = 1883
ALERT_TOPIC = "drones/+/obstacles"
DECISION_TOPIC = "swarm/decisions"
LOG_FILE = Path(__file__).resolve().parent / "decisions.log"

decision_maker: LLMDecisionMaker | None = None  # created in main()


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
        f"source={decision['decision_source']} "
        f"-> published to {DECISION_TOPIC}"
    )
    if "safety_overrides" in decision:
        print(f"[LLM Decision]   safety layer corrected the LLM: {decision['safety_overrides']}")
    if "fallback_reason" in decision:
        print(f"[LLM Decision]   LLM not used: {decision['fallback_reason']}")


def main() -> None:
    global decision_maker
    parser = argparse.ArgumentParser(description="MQTT -> LLM decision -> MQTT")
    parser.add_argument("--llm", action="store_true", help="use the local LLM (Ollama); default: rules only")
    parser.add_argument("--model", default=None, help="Ollama model name (default llama3.2:3b)")
    args = parser.parse_args()

    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model
    use_llm = args.llm or llm_enabled_from_env()
    decision_maker = LLMDecisionMaker(drone_id="llm_decision_node", use_llm=use_llm, keep_history=True)

    if use_llm:
        llm = decision_maker.llm_client
        if llm.is_available():
            print(f"[LLM Node] LLM mode: {llm.name} - loading model into memory...")
            llm.warm_up()
            print("[LLM Node] LLM ready")
        else:
            print(f"[LLM Node] LLM mode: {llm.name} NOT available, rules will be used until it is")
    else:
        print("[LLM Node] Rule-based mode (start with --llm to use the LLM)")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    print("LLM Decision Node waiting for drone alerts...")
    client.loop_forever()


if __name__ == "__main__":
    main()
