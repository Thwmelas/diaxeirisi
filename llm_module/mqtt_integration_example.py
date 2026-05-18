"""Example MQTT integration. Requires: pip install paho-mqtt"""
from __future__ import annotations
import json
import paho.mqtt.client as mqtt
from llm_decision import LLMDecisionMaker

BROKER = "localhost"
PORT = 1883
INPUT_TOPIC = "drones/detections"
OUTPUT_TOPIC = "drones/decisions"
decision_maker = LLMDecisionMaker(drone_id="llm_decision_module", use_llm=False, keep_history=True)

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code: {rc}")
    client.subscribe(INPUT_TOPIC)

def on_message(client, userdata, msg):
    try:
        drone_message = json.loads(msg.payload.decode("utf-8"))
        decision = decision_maker.interpret(drone_message)
        client.publish(OUTPUT_TOPIC, json.dumps(decision))
        print(json.dumps({"input": drone_message, "decision": decision}, indent=2))
    except Exception as exc:
        print(f"Failed to process message: {exc}")

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_forever()

if __name__ == "__main__": main()
