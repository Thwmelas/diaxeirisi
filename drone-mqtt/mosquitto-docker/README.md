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

## Notes

- `data/` and `logs/` are ignored by git because they are runtime files.
- `config/passwd` is kept in the project, but the current config does not require authentication.
- If you want a cleaner demo, keep the current anonymous setup and avoid changing the broker config.