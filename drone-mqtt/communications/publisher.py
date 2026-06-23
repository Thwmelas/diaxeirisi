import paho.mqtt.client as mqttclient
import time
import json

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Drone 1 (Publisher) connected successfully!")
        global connected
        connected = True
    else:
        print(f"Connection failed with code {reason_code}")

connected = False

# Create client (NO username_pw_set needed because of allow_anonymous)
client = mqttclient.Client(mqttclient.CallbackAPIVersion.VERSION2, "Anonymous_Drone_1")
client.on_connect = on_connect

# Connect to local Docker broker
client.connect("localhost", 1883)
client.loop_start()

while not connected:
    time.sleep(0.2)

# The payload (mimicking YOLOv5 detection)
topic = "drones/drone_1/obstacles"
obstacle_data = {
    "drone_id": "drone_1",
    "object": "tree",
    "location": [34.5, -118.2, 15.0],
    "size": [2.5, 7.0],
    "velocity": [0, 0, 0]
}

json_payload = json.dumps(obstacle_data)

print(f"Publishing to {topic}...")
client.publish(topic, json_payload)
print("Message sent!")

time.sleep(1)
client.loop_stop()