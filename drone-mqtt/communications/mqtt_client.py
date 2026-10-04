import json
import paho.mqtt.client as mqtt

TOPIC_DETECTIONS = "drones/{id}/detections"
TOPIC_DECISION = "drones/{id}/decision"
TOPIC_ALERTS = "swarm/alerts"
TOPIC_CONFIRMATIONS = "swarm/confirmations"

class SwarmClient:
    """Manage MQTT communication for drones."""
    def __init__(self, client_id, host="localhost", port=1883):
        self.client_id = client_id
        
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)

        self._user_callbacks = {}

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.client.connect(host, port, keepalive=60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"[{self.client_id}] Connected to the broker.")
            for topic in self._user_callbacks.keys():
                self.client.subscribe(topic)
        else:
            print(f"[{self.client_id}] Connection failed. Code: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f"[{self.client_id}] Unexpected disconnection. Retrying connection...")

    def _on_message(self, client, userdata, msg):
        """Handle incoming messages and convert JSON payloads to dictionaries."""
        topic = msg.topic

        try:
            data = json.loads(msg.payload.decode('utf-8'))
        except json.JSONDecodeError:
            data = msg.payload.decode('utf-8')
            print(f"[{self.client_id}] Warning: Received non-JSON message on {topic}")

        for sub_topic, callback in self._user_callbacks.items():
            if mqtt.topic_matches_sub(sub_topic, topic):
                callback(topic, data)

    def subscribe(self, topic, callback):
        """Subscribe to a topic with a callback accepting (topic, data)."""
        self._user_callbacks[topic] = callback
        self.client.subscribe(topic)
        print(f"[{self.client_id}] Subscribed to topic: {topic}")

    def publish(self, topic, data, qos=0):
        """Convert a dictionary to JSON and publish it."""
        json_payload = json.dumps(data)
        self.client.publish(topic, json_payload, qos=qos)

    def stop(self):
        """Close the connection and stop the background thread."""
        self.client.loop_stop()
        self.client.disconnect()
        print(f"[{self.client_id}] Disconnected.")