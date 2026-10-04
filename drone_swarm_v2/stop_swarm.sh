#!/bin/bash
# stop_swarm.sh - Σταματάει όλο το σμήνος.
pkill -f "drone.py"
pkill -f "llm_node.py"
pkill -f "swarm_monitor.py"
pkill xterm
echo "Το σμήνος σταμάτησε."
