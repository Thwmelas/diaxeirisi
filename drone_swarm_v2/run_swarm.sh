#!/bin/bash
export LANG=C.UTF-8
# run_swarm.sh - Ξεκινάει όλο το σμήνος με μία εντολή.
# Κάθε κομμάτι ανοίγει στο δικό του παράθυρο, για να φαίνονται τα logs του.
cd "$(dirname "$0")"

echo "1/4: MQTT broker..."
sudo systemctl start mosquitto

echo "2/4: LLaMA (Ollama)..."
if ! pgrep -x ollama > /dev/null; then
    ollama serve > /dev/null 2>&1 &
    sleep 3
fi

echo "Swarm monitor..."
xterm -fa "DejaVu Sans Mono" -fs 10 -T "Swarm monitor" -geometry 110x30 -hold -e "python3 swarm_monitor.py" &
sleep 1
echo "3/4: LLM node..."
xterm -fa "DejaVu Sans Mono" -fs 10 -T "LLM node" -geometry 110x30 -hold -e "python3 llm_node.py" &
sleep 2

echo "4/4: Drones..."
xterm -fa "DejaVu Sans Mono" -fs 10 -T "drone_1" -geometry 110x15 -hold -e "OMP_NUM_THREADS=1 nice -n 19 python3 drone.py drone_1 videos/drone1.mp4" &
sleep 3
xterm -fa "DejaVu Sans Mono" -fs 10 -T "drone_2" -geometry 110x15 -hold -e "OMP_NUM_THREADS=1 nice -n 19 python3 drone.py drone_2 videos/drone2.mp4" &
sleep 3
xterm -fa "DejaVu Sans Mono" -fs 10 -T "drone_3" -geometry 110x15 -hold -e "OMP_NUM_THREADS=1 nice -n 19 python3 drone.py drone_3 videos/drone3.mp4" &

echo ""
echo "Το σμήνος ξεκίνησε. Για να σταματήσεις τα πάντα: bash stop_swarm.sh"
