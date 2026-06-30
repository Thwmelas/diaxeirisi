"""
Placeholder decision-making node.

Ακούει σε MQTT alerts από όλα τα drones (topic drones/#), εφαρμόζει απλό
rule-based logic, και καταγράφει αποφάσεις. ΣΚΟΠΟΣ: λειτουργικό pipeline
detection -> decision ΣΗΜΕΡΑ.

Όταν η ομάδα LLM/Decision-Making τελειώσει το μοντέλο τους (LLaMA2 ή πιο
σύνθετο rule-based σύστημα), αντικαθιστούν μόνο τη συνάρτηση decide()
παρακάτω -- όλο το υπόλοιπο (MQTT subscribe, logging) παραμένει ίδιο.

Χρήση:
    python3 decision_placeholder.py
"""

import paho.mqtt.client as mqtt
import json
import time

LOG_FILE = "decisions.log"

# Simple priority rules - placeholder μέχρι να έρθει το πραγματικό decision layer
PRIORITY_RULES = {
    "fire": "CRITICAL",
    "person": "HIGH",
    "car": "MEDIUM",
    "bus": "MEDIUM",
    "boat": "LOW",
    "tree": "LOW",
}


def decide(alert):
    """
    PLACEHOLDER: αντικατέστησε αυτή τη συνάρτηση με πραγματικό LLM reasoning
    ή πιο σύνθετο rule-based σύστημα. Πρέπει να επιστρέφει ένα dict με
    τουλάχιστον το πεδίο 'priority' και 'action'.
    """
    obj = alert.get("object", "unknown")
    priority = PRIORITY_RULES.get(obj, "LOW")

    if priority == "CRITICAL":
        action = "ALERT_ALL_DRONES_AND_OPERATOR"
    elif priority == "HIGH":
        action = "NOTIFY_OPERATOR"
    else:
        action = "LOG_ONLY"

    return {
        "priority": priority,
        "action": action,
        "source_drone": alert.get("drone_id"),
        "object": obj,
        "location": alert.get("location"),
    }


def log_decision(decision):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {json.dumps(decision)}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    print(f"[DECISION] priority={decision['priority']} action={decision['action']} "
          f"object={decision['object']} drone={decision['source_drone']}")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Connected to broker.")
        client.subscribe("drones/#")
    else:
        print(f"Connection failed: {reason_code}")


def on_message(client, userdata, msg):
    try:
        alert = json.loads(msg.payload.decode('utf-8'))
    except json.JSONDecodeError:
        print(f"Could not parse message on {msg.topic}")
        return

    decision = decide(alert)
    log_decision(decision)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("localhost", 1883, 60)
    print("Decision placeholder waiting for alerts...")
    client.loop_forever()


if __name__ == '__main__':
    main()
