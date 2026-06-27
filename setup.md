### Προαπαιτούμενα
- WSL2 Ubuntu 22.04 
- ROS 2 Humble
- Gazebo Classic 11.10.2
- PX4-Autopilot v1.14.3 cloned ξεχωριστά στο `~/PX4-Autopilot`
1. Clone οτι υπαρχει σε αυτο το branch
2. 2. Clone το PX4-Autopilot:
```bash
   git clone https://github.com/PX4/PX4-Autopilot.git --recursive ~/PX4-Autopilot
   cd ~/PX4-Autopilot
   git checkout v1.14.3
```
3. Τρέξε το setup script εφαρμόζει το patch για RGB κάμερα στο iris model:
```bash
   cd ~/drone_ws
   bash setup.sh
```
4. Build το PX4-Autopilot και το ROS2 workspace
5. 5. Source τα δύο environments σε κάθε νέο terminal:
```bash
   source /opt/ros/humble/setup.bash
   source ~/drone_ws/install/setup.bash
```

### Εκκίνηση swarm

```bash

ros2 launch launch/swarm_launch.py
```
Αυτό ανοίγει 3x iris drones (με ενσωματωμένη RGB κάμερα) + τον MicroXRCEAgent bridge.
### Camera feeds

Κάθε drone instance στέλνει video μέσω GStreamer/UDP:
- px4_1 → port 5601
- px4_2 → port 5602
- px4_3 → port 5603
- Δοκιμή feed:
```bash
gst-launch-1.0 udpsrc port=5601 ! application/x-rtp ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink
```
