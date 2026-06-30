import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import OffboardControlMode, TrajectorySetpoint, VehicleCommand
import math

DRONE_NS = "px4_1"
TARGET_SYSTEM_ID = int(DRONE_NS.split("_")[1]) + 1


class OffboardControl(Node):
    def __init__(self):
        super().__init__('takeoff_node')
        qos_sensor = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        qos_command = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        self.offboard_ctrl_pub = self.create_publisher(
            OffboardControlMode, f'/{DRONE_NS}/fmu/in/offboard_control_mode', qos_sensor)
        self.trajectory_pub = self.create_publisher(
            TrajectorySetpoint, f'/{DRONE_NS}/fmu/in/trajectory_setpoint', qos_sensor)
        self.command_pub = self.create_publisher(
            VehicleCommand, f'/{DRONE_NS}/fmu/in/vehicle_command', qos_command)
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.offboard_setpoint_counter = 0
        self.takeoff_height = -5.0  # -5.0 = 5 μέτρα πάνω

    def timer_callback(self):
        mode_msg = OffboardControlMode()
        mode_msg.position = True
        mode_msg.velocity = False
        mode_msg.acceleration = False
        mode_msg.attitude = False
        mode_msg.body_rate = False
        mode_msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.offboard_ctrl_pub.publish(mode_msg)

        traj_msg = TrajectorySetpoint()
        traj_msg.position = [0.0, 0.0, self.takeoff_height]
        traj_msg.velocity = [math.nan, math.nan, math.nan]
        traj_msg.acceleration = [math.nan, math.nan, math.nan]
        traj_msg.jerk = [math.nan, math.nan, math.nan]
        traj_msg.yaw = 0.0
        traj_msg.yawspeed = math.nan
        traj_msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.trajectory_pub.publish(traj_msg)

        if self.offboard_setpoint_counter == 10:
            self.publish_vehicle_command(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0)
            self.publish_vehicle_command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0, 21196.0)
            self.get_logger().info(f"[{DRONE_NS}] Στέλνω εντολή Οπλισμού & Απογείωσης...")

        if self.offboard_setpoint_counter < 11:
            self.offboard_setpoint_counter += 1

    def publish_vehicle_command(self, command, param1=0.0, param2=0.0, param3=0.0,
                                  param4=0.0, param5=0.0, param6=0.0, param7=0.0):
        msg = VehicleCommand()
        msg.command = command
        msg.param1 = float(param1)
        msg.param2 = float(param2)
        msg.param3 = float(param3)
        msg.param4 = float(param4)
        msg.param5 = float(param5)
        msg.param6 = float(param6)
        msg.param7 = float(param7)
        msg.target_system = TARGET_SYSTEM_ID
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.command_pub.publish(msg)

    def land(self):
        """Στέλνει εντολή ομαλής προσγείωσης (αντί να αφήσουμε το PX4 σε failsafe)."""
        self.get_logger().info(f"[{DRONE_NS}] Στέλνω εντολή ομαλής προσγείωσης (LAND)...")
        self.publish_vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)


def main(args=None):
    rclpy.init(args=args)
    node = OffboardControl()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Λήφθηκε Ctrl+C, στέλνω LAND πριν τον τερματισμό...")
        node.land()
        # Δίνουμε λίγο χρόνο ώστε το μήνυμα LAND να σταλεί πραγματικά πριν κλείσουμε
        for _ in range(10):
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
