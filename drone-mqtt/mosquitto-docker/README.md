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