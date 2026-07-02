import rclpy
import math
import random
import time
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import (OffboardControlMode, TrajectorySetpoint,
                           VehicleCommand, VehicleLocalPosition)

DRONE_NS = "px4_1"
TARGET_SYSTEM_ID = int(DRONE_NS.split("_")[1]) + 1

TAKEOFF_HEIGHT  = -5.0    # μέτρα (NED)
PATROL_HEIGHT   = -8.0    # μέτρα κατά το patrol
NUM_WAYPOINTS   = 6       # αριθμός τυχαίων waypoints
SCAN_DURATION   = 20.0    # δευτερόλεπτα για το 360° scan
YAW_RATE        = (2 * math.pi) / SCAN_DURATION  # rad/s για πλήρη στροφή

X_MIN, X_MAX = -20.0, 20.0
Y_MIN, Y_MAX = -20.0, 20.0
POSITION_THRESHOLD = 1.5


def random_waypoint():
    x = round(random.uniform(X_MIN, X_MAX), 1)
    y = round(random.uniform(Y_MIN, Y_MAX), 1)
    return x, y


class PatrolNode(Node):
    def __init__(self):
        super().__init__('patrol_node')

        qos_sensor = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        qos_cmd = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        self.offboard_pub = self.create_publisher(
            OffboardControlMode,
            f'/{DRONE_NS}/fmu/in/offboard_control_mode', qos_sensor)
        self.traj_pub = self.create_publisher(
            TrajectorySetpoint,
            f'/{DRONE_NS}/fmu/in/trajectory_setpoint', qos_sensor)
        self.cmd_pub = self.create_publisher(
            VehicleCommand,
            f'/{DRONE_NS}/fmu/in/vehicle_command', qos_cmd)

        self.create_subscription(
            VehicleLocalPosition,
            f'/{DRONE_NS}/fmu/out/vehicle_local_position',
            self._pos_callback, qos_sensor)

        self.position = (0.0, 0.0, 0.0)
        self.counter = 0
        self.armed = False
        self.current_yaw = 0.0

        self.waypoints = [random_waypoint() for _ in range(NUM_WAYPOINTS)]
        self.current_wp = 0
        self.scan_start_time = None
        self.state = "TAKEOFF"

        self.timer = self.create_timer(0.1, self._timer_callback)

        self.get_logger().info(
            f"Patrol ξεκίνησε. {NUM_WAYPOINTS} waypoints: {self.waypoints}")

    def _pos_callback(self, msg):
        self.position = (msg.x, msg.y, -msg.z)

    def _timer_callback(self):
        self._publish_offboard_mode()

        if self.state == "TAKEOFF":
            self._send_setpoint(0.0, 0.0, TAKEOFF_HEIGHT, yaw=0.0)
            if self.counter == 10 and not self.armed:
                self._send_command(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0)
                self._send_command(
                    VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0, 21196.0)
                self.armed = True
                self.get_logger().info("Arm + Takeoff εντολή στάλθηκε.")
            if self.counter < 11:
                self.counter += 1
            if self._reached(0.0, 0.0, TAKEOFF_HEIGHT):
                self.get_logger().info(
                    f"Takeoff ολοκληρώθηκε. Ξεκινώ patrol "
                    f"({NUM_WAYPOINTS} waypoints, 360° scan σε κάθε ένα).")
                self.state = "PATROL"

        elif self.state == "PATROL":
            if self.current_wp >= len(self.waypoints):
                self.get_logger().info(
                    "Patrol ολοκληρώθηκε. Επιστρέφω στο κέντρο και προσγειώνομαι.")
                self.state = "RETURN"
                return

            wx, wy = self.waypoints[self.current_wp]

            if not self._reached(wx, wy, PATROL_HEIGHT):
                # Κινούμαστε προς το waypoint, κοιτάμε μπροστά
                self._send_setpoint(wx, wy, PATROL_HEIGHT, yaw=0.0)
                self.scan_start_time = None
                self.current_yaw = 0.0
            else:
                # Φτάσαμε — ξεκινάμε το 360° scan
                if self.scan_start_time is None:
                    self.scan_start_time = time.time()
                    self.get_logger().info(
                        f"Waypoint {self.current_wp+1}/{NUM_WAYPOINTS}: "
                        f"({wx}, {wy}) — ξεκινώ 360° scan ({SCAN_DURATION}s)...")

                elapsed = time.time() - self.scan_start_time
                # Υπολογισμός τρέχοντος yaw (αυξάνεται σταδιακά)
                self.current_yaw = (elapsed * YAW_RATE) % (2 * math.pi)
                self._send_setpoint(wx, wy, PATROL_HEIGHT, yaw=self.current_yaw)

                if elapsed >= SCAN_DURATION:
                    self.get_logger().info(
                        f"Waypoint {self.current_wp+1} scan ολοκληρώθηκε. "
                        f"Προχωρώ στο επόμενο.")
                    self.current_wp += 1
                    self.scan_start_time = None
                    self.current_yaw = 0.0

        elif self.state == "RETURN":
            # Επιστροφή στο κέντρο πριν την προσγείωση
            self._send_setpoint(0.0, 0.0, PATROL_HEIGHT, yaw=0.0)
            if self._reached(0.0, 0.0, PATROL_HEIGHT):
                self.state = "LAND"

        elif self.state == "LAND":
            self._send_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
            self.get_logger().info("Εντολή προσγείωσης στάλθηκε.")
            self.timer.cancel()

    def _reached(self, tx, ty, tz_ned):
        x, y, z = self.position
        target_z = -tz_ned
        dist = math.sqrt((x-tx)**2 + (y-ty)**2 + (z-target_z)**2)
        return dist < POSITION_THRESHOLD

    def _publish_offboard_mode(self):
        msg = OffboardControlMode()
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.offboard_pub.publish(msg)

    def _send_setpoint(self, x, y, z, yaw=0.0):
        msg = TrajectorySetpoint()
        msg.position = [x, y, z]
        msg.velocity = [math.nan, math.nan, math.nan]
        msg.acceleration = [math.nan, math.nan, math.nan]
        msg.jerk = [math.nan, math.nan, math.nan]
        msg.yaw = float(yaw)
        msg.yawspeed = math.nan
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.traj_pub.publish(msg)

    def _send_command(self, command, param1=0.0, param2=0.0):
        msg = VehicleCommand()
        msg.command = command
        msg.param1 = float(param1)
        msg.param2 = float(param2)
        msg.target_system = TARGET_SYSTEM_ID
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.cmd_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = PatrolNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Διακοπή — στέλνω LAND...")
        node._send_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
        for _ in range(10):
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
