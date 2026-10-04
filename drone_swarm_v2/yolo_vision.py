import os
import sys
import time

import cv2
from ultralytics import YOLO

# ---- Σταθερές ρυθμίσεις ----
CONF = 0.5
IMGSZ = 1024

# ---- Φόρτωση μοντέλου ΜΙΑ φορά ----
model = YOLO(os.path.join(os.path.dirname(os.path.abspath(__file__)), "best.pt"))


def detect(frame):
    """Παίρνει ένα frame και επιστρέφει λίστα με ό,τι εντόπισε."""
    results = model.predict(source=frame, imgsz=IMGSZ, conf=CONF, verbose=False)

    detections = []
    for box in results[0].boxes:
        detections.append({
            "object": model.names[int(box.cls[0])],
            "confidence": round(float(box.conf[0]), 2),
            "bbox": [int(v) for v in box.xyxy[0].tolist()],
        })
    return detections


def draw(frame, detections):
    """Επιστρέφει το frame με πράσινα κουτιά και ονόματα."""
    annotated = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        label = f'{d["object"]} {d["confidence"]:.2f}'
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated, label, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return annotated



if __name__ == "__main__":
    if len(sys.argv) >= 3:
        IMGSZ = int(sys.argv[2])

    cap = cv2.VideoCapture(sys.argv[1])
    times = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        start = time.time()
        detections = detect(frame)
        ms = (time.time() - start) * 1000
        times.append(ms)

        annotated = draw(frame, detections)
        cv2.putText(annotated, f"{ms:.0f} ms/frame", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imshow("test", annotated)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    # Το 1ο frame είναι πάντα αργό, οπότε δεν μετράει στον μέσο όρο
    if len(times) > 1:
        avg = sum(times[1:]) / len(times[1:])
        print(f"imgsz={IMGSZ}: μέσος χρόνος {avg:.0f} ms/frame")
