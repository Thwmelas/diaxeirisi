# Mosquitto Docker

This folder contains a simple Mosquitto broker setup for MQTT communication.

## What it does

- Runs Mosquitto in Docker
- Exposes MQTT on `1883`
- Exposes WebSockets on `9001`
- Allows anonymous access for easy testing
- Persists messages in `data/`

## Run it

```bash
docker compose up -d
```

## Test it

Subscribe in a terminal(in success it will look frozen and wait till you execute the next instruction):

```bash
docker exec -it mosquitto mosquitto_sub -h localhost -t test/topic
```

Publish a message from inside the container, from another terminal:

```bash
docker exec -it mosquitto mosquitto_pub -h localhost -t test/topic -m "Hello from the broker"
```

## How To Use The Communication Nodes (Phase 2)

The `communications` directory contains the Python modules that interact with the broker using the `paho-mqtt` library.

### 1. Integration With AI / YOLO

The publisher logic is wrapped in a reusable function so other teams do not have to write networking code.

In your AI script, import and use it like this:

```python
from communications.publisher import send_drone_alert

# Call this when an object is detected
send_drone_alert(
	drone_id="drone_1",
	object_name="car",
	coordinates=[37.9, 23.7, 50.0],
	size=[4.5, 1.8],
)
```

### 2. Integration With ROS2 / Decision Making

To listen for incoming alerts from the swarm, use the subscriber node.

Run this from the `communications` directory:

```bash
python3 subscriber.py
```

This node listens to the `drones/#` wildcard topic and automatically parses and prints incoming JSON payloads from any drone.

## Notes

- `data/` and `logs/` are ignored by git because they are runtime files.
- `config/passwd` is kept in the project, but the current config does not require authentication.
- If you want a cleaner demo, keep the current anonymous setup and avoid changing the broker config.
## 🛰️ Swarm Communication Protocol (MQTT Architecture)

In this new version, Gazebo is used only as a visual bonus[cite: 2]. The drones are now real, independent entities that communicate exclusively via the MQTT Broker, while a central node (LLM Node - LLaMA) handles decision-making[cite: 2].

### 1. Why did we choose MQTT?
MQTT (Message Queuing Telemetry Transport) was selected because[cite: 5]:
- **It is extremely lightweight:** Instead of transmitting heavy video streams over the network, each drone analyzes its video locally (via OpenCV and YOLO) and sends only the results (compressed JSON payloads)[cite: 2, 5].
- **Pub/Sub Architecture (Publish/Subscribe):** The drones do not need to know the IP addresses of other drones or the LLaMA node. They simply broadcast to the network (publish) or listen to specific channels (subscribe), providing complete decoupling between nodes.

### 2. Why do we use these 4 specific Topics?
The 4 topics (`drones/<id>/detections`, `drones/<id>/decision`, `swarm/alerts`, `swarm/confirmations`) serve as the strict **Common Contract** for the team[cite: 3]. 
This agreement allows each member to write their code independently[cite: 3]:
- It ensures that no drone talks directly to another drone (preventing chaos)[cite: 2].
- It separates the **information** (detections sent to the LLM) from the **action/decision** (decisions/alerts sent from the LLM to the drones)[cite: 3].
- It allows the creation of passive observers (like `swarm_monitor.py`), which listens to all topics (using the wildcard `#`) without affecting the communication flow[cite: 3, 5].

### 3. What is the QoS (Quality of Service) we use?
QoS in MQTT defines the guarantee of message delivery[cite: 5].
In our implementation, we use the default **QoS 0 (At most once / Fire and Forget)**:
- **How it works:** The message is sent once, and the sender does not wait for an acknowledgment (ACK) from the Broker.
- **Why we chose it:** Detections from YOLO are generated continuously (multiple frames per second). If a packet is lost in the network, it is not a critical issue, as the next JSON payload will arrive in a few milliseconds. QoS 0 provides the **maximum possible speed** and zero latency for the swarm, preventing network bottlenecks.