
import sys
import time
from datetime import datetime, timezone

from mqtt_client import SwarmClient, DETECTIONS, DECISION, ALERTS

sys.path.insert(0, "llm_module")
from llm_decision import LLMDecisionMaker

MAX_AGE = 30   # detections παλιότερα από αυτό τα πετάμε (το drone έχει ήδη προχωρήσει)


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] [LLM] {text}", flush=True)


# ΕΝΑ LLMDecisionMaker για όλα τα drones: έτσι θυμάται τι ανέφεραν όλα
decision_maker = LLMDecisionMaker(drone_id="llm_node", use_llm=True, keep_history=True)


def on_detection(topic, data):
    sent = datetime.fromisoformat(data["timestamp"])
    age = (datetime.now(timezone.utc) - sent).total_seconds()
    if age > MAX_AGE:
        log(f"Παραλείπω παλιό μήνυμα από {data['drone_id']} ({age:.0f} δευτ.)")
        return

    log(f"Από {data['drone_id']}: {data['object']} x{data.get('count', 1)} "
        f"(conf={data['confidence']}) -> ρωτάω το LLaMA...")
    decision = decision_maker.interpret(data)
    decision["drone_id"] = data["drone_id"]
    decision["object"] = data["object"]
    decision["count"] = data.get("count", 1)

    latency = decision.get("llm_latency_ms")
    took = f"{latency / 1000:.1f} δευτ." if latency else "-"
    log(f"Απάντηση ({decision['decision_source']}, {took}): {decision.get('description', '')}")
    log(f"     πρόταση: {decision['recommendation']}")
    log(f"     risk={decision['risk_level']}  action={decision['action']}")
    if "safety_overrides" in decision:
        log(f"     έλεγχος ασφαλείας: {decision['safety_overrides']}")
    if "fallback_reason" in decision:
        log(f"     fallback: {decision['fallback_reason']}")

    client.publish(DECISION.format(id=data["drone_id"]), decision)
    if decision["broadcast"]:
        client.publish(ALERTS, decision)
        log("     -> ειδοποίηση σε όλο το σμήνος")


llm = decision_maker.llm_client
if llm.is_available():
    log(f"Φορτώνω το {llm.name} στη μνήμη...")
    llm.warm_up()
else:
    log(f"Το {llm.name} δεν είναι διαθέσιμο, θα απαντάνε οι κανόνες")

client = SwarmClient("llm_node")
client.subscribe(DETECTIONS.format(id="+"), on_detection)
log("Ακούω τα detections όλων των drones")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.stop()
