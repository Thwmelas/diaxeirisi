import paho.mqtt.client as mqttclient
import time
import json

# Κρατάμε κανονικά το on_connect callback
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        global connected
        connected = True
    else:
        print(f"Connection failed: {reason_code}")

connected = False

# Αυτή είναι η συνάρτηση που θα δώσεις στην ομάδα σου!
def send_drone_alert(drone_id, object_name, coordinates, size):
    """
    Αυτή τη συνάρτηση θα την καλεί η ομάδα του YOLO/Simulation.
    Παίρνει live ορίσματα και τα στέλνει μέσω MQTT.
    """
    global connected
    
    # Αρχικοποίηση client
    client = mqttclient.Client(mqttclient.CallbackAPIVersion.VERSION2, f"Publisher_{drone_id}")
    client.on_connect = on_connect

    client.connect("localhost", 1883)
    client.loop_start()

    # Αναμονή για σύνδεση
    while not connected:
        time.sleep(0.1)

    # Δυναμικό Topic ανάλογα με το ποιο drone εντόπισε το αντικείμενο
    topic = f"drones/{drone_id}/obstacles"
    
    # Δυναμικό Payload με τα πραγματικά δεδομένα της προσομοίωσης
    obstacle_data = {
        "drone_id": drone_id,
        "object": object_name,
        "location": coordinates,  # π.χ. [x, y, z]
        "size": size,             # π.χ. [width, height]
        "velocity": [0, 0, 0]     # Μπορεί να προστεθεί αργότερα
    }

    json_payload = json.dumps(obstacle_data)
    client.publish(topic, json_payload)
    
    # Κλείσιμο loop με ασφάλεια
    time.sleep(0.2)
    client.loop_stop()
    connected = False # Reset για την επόμενη κλήση