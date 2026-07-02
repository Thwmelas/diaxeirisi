import sys
import time
import cv2

# YOLO module  
sys.path.insert(0, '/home/sdi2300104/drone_ws/perception_node')
from yolo_vision import detect_objects

# LLM module 
sys.path.insert(0, '/home/sdi2300104/drone_ws/communication_node/llm_module')
from llm_decision import interpret_drone_message

# MQTT publisher 
sys.path.insert(0, '/home/sdi2300104/mqtt_test')
from publisher import send_drone_alert

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import VehicleLocalPosition

DRONE_ID = "px4_1"
CAMERA_PORT = 5601
DETECT_INTERVAL_SEC = 3  # κάθε 3 δευτερόλεπτα 

# Κατηγορίες που ενδιαφέρουν 
RELEVANT_CLASSES = {"person", "car", "bus", "boat", "building", "tree",
                    "fire", "drone", "airplane", "vehicle", "smoke"}


def estimate_distance(box_coords, frame_height):
    """
    Εκτιμά απόσταση από το ύψος του bounding box σε pixels.
    Πολύ κοντά: box_height > 50% frame → ~3m
    Κοντά:      box_height > 20% frame → ~8m
    Μακριά:     box_height < 20% frame → ~20m
    """
    x1, y1, x2, y2 = box_coords
    box_height = y2 - y1
    ratio = box_height / frame_height if frame_height > 0 else 0

    if ratio > 0.5:
        return 3.0
    elif ratio > 0.2:
        return 8.0
    else:
        return 20.0


def estimate_direction(box_coords, frame_width):
    """Εκτιμά κατεύθυνση από οριζόντια θέση του bounding box στο frame."""
    x1, _, x2, _ = box_coords
    center_x = (x1 + x2) / 2
    ratio = center_x / frame_width if frame_width > 0 else 0.5

    if ratio < 0.33:
        return "left"
    elif ratio < 0.66:
        return "front"
    else:
        return "right"


class IntegrationNode(Node):
    def __init__(self):
        super().__init__('drone_integration')
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
        self.position = (msg.x, msg.y, -msg.z)


def main():
    rclpy.init()
    node = IntegrationNode()

    pipeline = (f"udpsrc port={CAMERA_PORT} ! application/x-rtp ! "
                f"rtph264depay ! avdec_h264 ! videoconvert ! appsink")
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    if not cap.isOpened():
        print(f"ERROR: δεν άνοιξε το camera stream στο port {CAMERA_PORT}")
        return

    print(f"Integration node ξεκίνησε για {DRONE_ID}.")
    print(f"Camera: port {CAMERA_PORT} | YOLO: imgsz=1024 conf=0.5 | Interval: {DETECT_INTERVAL_SEC}s")

    last_detect = 0
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            ret, frame = cap.read()
            if not ret:
                continue

            now = time.time()
            if (now - last_detect) < DETECT_INTERVAL_SEC:
                continue
            last_detect = now

            # --- YOLO Detection ---
            annotated = detect_objects(frame)
            h, w = frame.shape[:2]

            

            results = _model.predict(
                source=frame, imgsz=1024, conf=0.25, verbose=False)

            if not results or len(results[0].boxes) == 0:
                print(f"[{time.strftime('%H:%M:%S')}] Δεν εντοπίστηκε τίποτα.")
                continue

            # Πάρε το box με το μεγαλύτερο confidence
            best_box = max(results[0].boxes,
                           key=lambda b: b.conf[0].item())
            class_id = int(best_box.cls[0].item())
            class_name = _model.names[class_id]
            confidence = best_box.conf[0].item()
            coords = best_box.xyxy[0].tolist()

            distance = estimate_distance(coords, h)
            direction = estimate_direction(coords, w)
            x, y, z = node.position

            print(f"[{time.strftime('%H:%M:%S')}] YOLO: {class_name} "
                  f"conf={confidence:.2f} dist≈{distance}m dir={direction}")

            # --- LLM Decision ---
            llm_input = {
                "drone_id": DRONE_ID,
                "object": class_name,
                "distance": distance,
                "direction": direction,
                "confidence": round(confidence, 2),
                "location": [round(x, 2), round(y, 2), round(z, 2)]
            }
            decision = interpret_drone_message(llm_input)
            print(f"[{time.strftime('%H:%M:%S')}] LLM: "
                  f"risk={decision.get('risk_level')} "
                  f"action={decision.get('action')}")

            # --- MQTT Alert ---
            if class_name in RELEVANT_CLASSES:
                send_drone_alert(
                    drone_id=DRONE_ID,
                    object_name=class_name,
                    coordinates=[round(x, 2), round(y, 2), round(z, 2)],
                    size=[round(coords[2]-coords[0], 1),
                          round(coords[3]-coords[1], 1)]
                )
                print(f"[{time.strftime('%H:%M:%S')}] MQTT alert sent.")

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
