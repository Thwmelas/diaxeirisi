import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction

def generate_launch_description():
    px4_dir = os.path.expanduser('~/PX4-Autopilot')

    # 1. Micro XRCE-DDS Agent: γέφυρα PX4 <-> ROS 2
    start_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        output='screen'
    )

    #2 PX4 script: σηκώνει gzserver + κάνει spawn 3 iris drones + ανοίγει gzclient
    start_swarm = ExecuteProcess(
        cmd=['./Tools/simulation/gazebo-classic/sitl_multiple_run.sh', '-n', '3', '-m', 'iris', '-w', 'empty'],
        cwd=px4_dir,
        output='screen'
    )

    delay_agent = TimerAction(
        period=3.0,
        actions=[start_agent]
    )

    return LaunchDescription([
        start_swarm,
        delay_agent,
    ])
