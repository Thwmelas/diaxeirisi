import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import VehicleOdometry

class SensorReader(Node):
    def __init__(self):
        super().__init__("odometry_reader")
        
        
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        self.subscription = self.create_subscription(
            VehicleOdometry, 
            "/fmu/out/vehicle_odometry",
            self.odometry_callback, 
            qos_profile
        )

    def odometry_callback(self, msg):
        x = msg.position[0]
        y = msg.position[1]
        z = msg.position[2]
        self.get_logger().info(f"Position: x={x:.2f}, y={y:.2f}, z={z:.2f}")

def main(args=None):
    rclpy.init(args=args)
    node = SensorReader()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
