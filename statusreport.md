* Infastracture setup , successfully integrated PX4-Autopilot with ROS 2 via the Micro XRCE-DDS Agent on Ubuntu/WSL
* Developed a custom ROS 2 launch file (`swarm_launch.py`)
* Successfully spawned 3 independent x500 drones in Gazebo
* Configured isolated ROS 2 namespaces (e.g., `/px4_1`, `/px4_2`) for independent telemetry and control
* Custom testing world created `custom_world.sdf` featuring geometric cubes, sphere and a rover to facilitate YOLO object detection and obstacle avoidance testing
* ROS 2 Python Nodes:`odometry_reader.py`:reads real-time X, Y, Z telemetry data from the drones,`takeoff.py`: automates PX4 Offboard mode arming and executes a 5-meter takeoff
