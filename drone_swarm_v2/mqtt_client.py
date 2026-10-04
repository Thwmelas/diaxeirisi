"""
mqtt_client.py - Το "δίκτυο" του σμήνους.
ΠΡΟΣΩΡΙΝΗ ΕΚΔΟΣΗ μέχρι να παραδώσει ο Γιάννης την τελική.

    client = SwarmClient("drone_1")
    client.subscribe("swarm/alerts", on_alert)   # on_alert(topic, data)
    client.publish("drones/drone_1/detections", {...})
    client.stop()
"""
import json
import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883

# Τα 4 topics του κοινού συμβολαίου
DETECTIONS = "drones/{id}/detections"
DECISION = "drones/{id}/decision"
ALERTS = "swarm/alerts"
CONFIRMATIONS = "swarm/confirmations"


class SwarmClient:
    def __init__(self, client_id):
        self.callbacks = {}   # topic pattern -> συνάρτηση
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(BROKER, PORT, keepalive=300)
        self.client.loop_start()   # μία σύνδεση που μένει ανοιχτή, σε δικό της thread

    def subscribe(self, topic, callback):
        self.callbacks[topic] = callback
        self.client.subscribe(topic)

    def publish(self, topic, data):
        self.client.publish(topic, json.dumps(data, ensure_ascii=False))

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        # Αν πέσει και ξανασυνδεθεί, ξανακάνει subscribe σε όλα
        for topic in list(self.callbacks):
            client.subscribe(topic)

    def _on_message(self, client, userdata, msg):
        data = json.loads(msg.payload.decode("utf-8"))
        for pattern, callback in list(self.callbacks.items()):
            if mqtt.topic_matches_sub(pattern, msg.topic):
                callback(msg.topic, data)
