import sys
import time
import random
import cv2

sys.path.insert(0, '/home/sdi2300104/mqtt_test')
from publisher import send_drone_alert

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import VehicleLocalPosition

DRONE_ID = "px4_1"
CAMERA_PORT = 5601
DETECT_INTERVAL_SEC = 5

# οταν εχεισ best.pt απο YOLO αντικατέστησε τη fake_detect()
# παρακάτω με αυτό (uncomment + comment out fake_detect):
#
# from ultralytics import YOLO
# model = YOLO("best.pt")
#
# def real_detect(frame):
#     results = model(frame)
#     if len(results[0].boxes) == 0:
#         return None
#     box = results[0].boxes[0]
#     class_name = model.names[int(box.cls[0])]
#     x1, y1, x2, y2 = box.xyxy[0].tolist()
#     size = [round((x2-x1)/100, 1), round((y2-y1)/100, 1)]  # rough pixel->m placeholder
#     return class_name, size

FAKE_CLASSES = ["car", "person", "bus", "tree", "boat", "fire"]


class PerceptionPlaceholder(Node):
    def __init__(self):
        super().__init__('perception_placeholder')
        self.position = (0.0, 0.0, 0.0)

        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        self.create_subscription(
            VehicleLocalPosition,
            f'/{DRONE_ID}/fmu/out/vehicle_local_position',
            self._position_callback,
            qos_profile
        )

    def _position_callback(self, msg):
        self.position = (msg.x, msg.y, -msg.z)  # NED z -> "up positive"


def fake_detect(frame):
    """
    PLACEHOLDER: αντικατάστησε αυτή τη συνάρτηση με πραγματικό YOLO inference
    όταν είναι έτοιμο το μοντέλο. Πρέπει να επιστρέφει (object_name, size)
    ή None αν δεν εντοπίστηκε τίποτα.
    """
    if frame is None:
        return None
    obj = random.choice(FAKE_CLASSES)
    size = [round(random.uniform(1.0, 5.0), 1), round(random.uniform(1.0, 3.0), 1)]
    return obj, size


def main():
    rclpy.init()
    node = PerceptionPlaceholder()

    pipeline = f"udpsrc port={CAMERA_PORT} ! application/x-rtp ! rtph264depay ! avdec_h264 ! videoconvert ! appsink"
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print(f"ERROR: δεν άνοιξε το camera stream στο port {CAMERA_PORT}")
        return

    print(f"Perception placeholder ξεκίνησε για {DRONE_ID} (port {CAMERA_PORT}).")
    print("Στέλνει fake detections κάθε", DETECT_INTERVAL_SEC, "δευτερόλεπτα. Ctrl+C για stop.")

    last_send = 0
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            ret, frame = cap.read()

            now = time.time()
            if ret and (now - last_send) >= DETECT_INTERVAL_SEC:
                result = fake_detect(frame)
                if result:
                    obj, size = result
                    x, y, z = node.position
                    send_drone_alert(
                        drone_id=DRONE_ID,
                        object_name=obj,
                        coordinates=[round(x, 2), round(y, 2), round(z, 2)],
                        size=size
                    )
                    print(f"[{time.strftime('%H:%M:%S')}] Sent: {obj} at ({x:.1f},{y:.1f},{z:.1f})")
                last_send = now
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
