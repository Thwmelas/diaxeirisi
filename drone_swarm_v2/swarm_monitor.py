import json
import time
from datetime import datetime

from mqtt_client import SwarmClient

LOG_FILE = "swarm_log.jsonl"

def format_message(topic, data):
    """Format a topic and JSON payload as a readable log line."""
    now = datetime.now().strftime("%H:%M:%S")
    drone_id = data.get("drone_id", "unknown")
    obj = data.get("object", "unknown")
    
    if topic.endswith("/detections"):
        conf = data.get("confidence", 0.0)
        return f"{now}  {drone_id} -> LLM       {obj} ({conf})"
        
    elif topic == "swarm/alerts":
        risk = data.get("risk_level", "UNKNOWN")
        action = data.get("action", "none")
        return f"{now}  LLM -> σμήνος     {risk}: {action}"
        
    elif topic.endswith("/decision"):
        action = data.get("action", "none")
        return f"{now}  LLM -> {drone_id}     Απόφαση: {action}"
        
    elif topic == "swarm/confirmations":
        confirms = data.get("confirms", "unknown")
        answer = "ΒΡΗΚΕ" if data.get("found") else "ΔΕΝ ΒΡΗΚΕ"
        return f"{now}  {drone_id} -> {confirms}     {answer} {obj}"
    elif topic == "swarm/verify_request":
        return f"{now}  {drone_id} -> σμήνος     ΖΗΤΑΕΙ ΕΠΑΛΗΘΕΥΣΗ: {obj}"

    else:
        return f"{now}  [{topic}] {data}"

def on_swarm_message(topic, data):
    """Handle each incoming swarm message."""
    print(format_message(topic, data))

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "topic": topic,
        "data": data
    }
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    print("==================================================")
    print(" Swarm Monitor starting (wildcard '#')")
    print(" Logging to file:", LOG_FILE)
    print(" Press Ctrl+C to exit")
    print("==================================================\n")

    monitor = SwarmClient(client_id="monitor_node")
    monitor.subscribe("#", on_swarm_message)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Monitor] Shutting down...")
        monitor.stop()