import paho.mqtt.client as mqtt
import json

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Connected with result code {reason_code}")
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("drones/#")
    else:
        print(f"Connection failed with result code {reason_code}")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    # Decode the payload from bytes to a readable string/JSON
    try:
        data = json.loads(msg.payload.decode('utf-8'))
        print(f"\n[ALERT] Message received on topic: {msg.topic}")
        print(f"Data: {json.dumps(data, indent=2)}") # Prints JSON nicely
    except json.JSONDecodeError:
        # Fallback if the message isn't JSON
        print(f"\n[ALERT] {msg.topic}: {msg.payload.decode('utf-8')}")

# Create the client
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message

# CRITICAL CHANGE: Point this to your local Docker broker, not the Eclipse cloud
mqttc.connect("localhost", 1883, 60)

# Blocking call that processes network traffic and handles reconnecting.
print("Drone 2 is waiting for messages...")
mqttc.loop_forever()