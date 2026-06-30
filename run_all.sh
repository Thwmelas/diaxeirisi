#!/bin/bash
# run_all.sh - Σηκώνει ολόκληρο το pipeline: simulation + MQTT broker +
# perception placeholder + decision placeholder, το καθένα σε ξεχωριστό
# xterm window, ώστε να βλέπεις τα logs του καθενός ζωντανά.
#
# Χρήση: bash run_all.sh

set -e

echo "1/4: Έλεγχος αν τρέχει ο Mosquitto broker..."
if ! systemctl is-active --quiet mosquitto; then
    echo "   Ξεκινάω τον mosquitto..."
    sudo systemctl start mosquitto
fi
echo "   ✓ Mosquitto τρέχει."

echo "2/4: Ξεκινάω το Gazebo/ROS2 swarm simulation..."
xterm -hold -e "cd $HOME/drone_ws && source /opt/ros/humble/setup.bash && source $HOME/drone_ws/install/setup.bash && ros2 launch launch/swarm_launch.py" &

echo "   Περιμένω 20 δευτερόλεπτα να σταθεροποιηθεί το simulation..."
sleep 20

echo "3/4: Ξεκινάω το decision placeholder..."
xterm -hold -e "cd $HOME/drone_ws && python3 decision_placeholder.py" &

sleep 2

echo "4/4: Ξεκινάω το perception placeholder..."
xterm -hold -e "cd $HOME/drone_ws && source /opt/ros/humble/setup.bash && source $HOME/drone_ws/install/setup.bash && python3 perception_placeholder.py" &

echo ""
echo "Όλα ξεκίνησαν. 3 xterm windows άνοιξαν (simulation, decision, perception)."
echo "Για να σταματήσεις τα πάντα τρέξε το stop_all.sh"
