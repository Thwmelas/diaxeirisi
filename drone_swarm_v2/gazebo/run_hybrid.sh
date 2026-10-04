#!/bin/bash

export LANG=C.UTF-8
cd "$(dirname "$0")/.."

GAZEBO_CAM="udpsrc port=5601 ! application/x-rtp ! rtph264depay ! avdec_h264 ! videoconvert ! appsink drop=1 max-buffers=1"

echo "MQTT broker..."
sudo systemctl start mosquitto

echo "LLaMA (Ollama)..."
if ! pgrep -x ollama > /dev/null; then
    ollama serve > /dev/null 2>&1 &
    sleep 3
fi

echo "Swarm monitor..."
xterm -fa "DejaVu Sans Mono" -fs 10 -T "Swarm monitor" -geometry 110x30 -hold -e "python3 swarm_monitor.py" &
sleep 1

echo "LLM node..."
xterm -fa "DejaVu Sans Mono" -fs 10 -T "LLM node" -geometry 110x30 -hold -e "python3 llm_node.py" &
sleep 2

echo "drone_1 (κάμερα Gazebo)..."
xterm -fa "DejaVu Sans Mono" -fs 10 -T "drone_1 (Gazebo)" -geometry 110x15 -hold -e "OMP_NUM_THREADS=1 nice -n 19 python3 drone.py drone_1 '$GAZEBO_CAM'" &
sleep 3

echo "drone_2, drone_3 (βίντεο)..."
xterm -fa "DejaVu Sans Mono" -fs 10 -T "drone_2" -geometry 110x15 -hold -e "OMP_NUM_THREADS=1 nice -n 19 python3 drone.py drone_2 videos/drone2.mp4" &
sleep 3
xterm -fa "DejaVu Sans Mono" -fs 10 -T "drone_3" -geometry 110x15 -hold -e "OMP_NUM_THREADS=1 nice -n 19 python3 drone.py drone_3 videos/drone3.mp4" &

echo ""
echo "Υβριδικό σμήνος έτοιμο. Για να σταματήσει: bash stop_swarm.sh"
