import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessStart

def generate_launch_description():
    px4_dir = os.path.expanduser('~/PX4-Autopilot')
    
    #Εκκίνηση του Micro XRCE-DDS Agent το οποίο είναι κοινή γέφυρα για όλα
    start_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        output='screen'
    )
    
    #Drone 0 ανοίγει το Gazebo στη θέση Y=0.0
    start_drone_0 = ExecuteProcess(
        cmd=['make', 'px4_sitl', 'gz_x500'],
        cwd=px4_dir,
        output='screen'
    )
    
    #Drone 1 μπαίνει στο ιδιο περιβαλλον
    start_drone_1 = ExecuteProcess(
        cmd=['./build/px4_sitl_default/bin/px4', '-i', '1'],
        cwd=px4_dir,
        additional_env={
            'PX4_SYS_AUTOSTART': '4001',
            'PX4_GZ_MODEL': 'x500',
            'PX4_GZ_Y': '2.0',
            'PX4_GZ_STANDALONE': '1'
        },
        output='screen'
    )
    
    #Drone 2 μπαίνει στον ίδιο κόσμο
    start_drone_2 = ExecuteProcess(
        cmd=['./build/px4_sitl_default/bin/px4', '-i', '2'],
        cwd=px4_dir,
        additional_env={
            'PX4_SYS_AUTOSTART': '4001',
            'PX4_GZ_MODEL': 'x500',
            'PX4_GZ_Y': '4.0',
            'PX4_GZ_STANDALONE': '1'
        },
        output='screen'
    )
    
    #Καθυστέρηση έναρξης των Drone 1 και Drone 2 μέχρι να ξεκινήσει επιτυχώς το Drone 0
    delay_drone_1 = RegisterEventHandler(
        OnProcessStart(
            target_action=start_drone_0,
            on_start=[start_drone_1]
        )
    )
    
    delay_drone_2 = RegisterEventHandler(
        OnProcessStart(
            target_action=start_drone_0,
            on_start=[start_drone_2]
        )
    )

    return LaunchDescription([
        start_agent,
        start_drone_0,
        delay_drone_1,
        delay_drone_2
    ])
