import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from tf2_ros import TransformBroadcaster
from geometry_msgs.msg import TransformStamped
from px4_msgs.msg import VehicleLocalPosition, VehicleAttitude

DRONES = ["px4_1", "px4_2", "px4_3"]


class DroneTFBroadcaster(Node):
    def __init__(self):
        super().__init__('drone_tf_broadcaster')
        self.broadcaster = TransformBroadcaster(self)

        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        self.positions = {d: (0.0, 0.0, 0.0) for d in DRONES}
        self.attitudes = {d: (1.0, 0.0, 0.0, 0.0) for d in DRONES}

        for drone in DRONES:
            self.create_subscription(
                VehicleLocalPosition,
                f'/{drone}/fmu/out/vehicle_local_position',
                self._make_pos_callback(drone),
                qos_profile
            )
            self.create_subscription(
                VehicleAttitude,
                f'/{drone}/fmu/out/vehicle_attitude',
                self._make_att_callback(drone),
                qos_profile
            )

        self.timer = self.create_timer(0.1, self._broadcast_all)

    def _make_pos_callback(self, drone):
        def cb(msg):
            # NED -> ENU-ish for RViz (x,y, -z για "πάνω θετικό")
            self.positions[drone] = (msg.x, msg.y, -msg.z)
        return cb

    def _make_att_callback(self, drone):
        def cb(msg):
            # PX4 quaternion: [w, x, y, z]
            self.attitudes[drone] = (msg.q[0], msg.q[1], msg.q[2], msg.q[3])
        return cb

    def _broadcast_all(self):
        now = self.get_clock().now().to_msg()
        for drone in DRONES:
            x, y, z = self.positions[drone]
            w, qx, qy, qz = self.attitudes[drone]

            t = TransformStamped()
            t.header.stamp = now
            t.header.frame_id = 'map'
            t.child_frame_id = f'{drone}/base_link'
            t.transform.translation.x = float(x)
            t.transform.translation.y = float(y)
            t.transform.translation.z = float(z)
            t.transform.rotation.w = float(w)
            t.transform.rotation.x = float(qx)
            t.transform.rotation.y = float(qy)
            t.transform.rotation.z = float(qz)
            self.broadcaster.sendTransform(t)


def main():
    rclpy.init()
    node = DroneTFBroadcaster()
    print("TF broadcaster ξεκίνησε για:", DRONES)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
