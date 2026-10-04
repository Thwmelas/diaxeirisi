"""
drone.py - Ένα drone του σμήνους.

Κάθε drone:
  1. διαβάζει το βίντεό του με OpenCV, frame-by-frame
  2. τρέχει YOLO (yolo_vision.detect) για να δει τι υπάρχει
  3. στέλνει ό,τι είδε στο LLM μέσω MQTT (drones/<id>/detections)
  4. λαμβάνει την απάντηση του LLaMA (drones/<id>/decision)
  5. ακούει τις ειδοποιήσεις των άλλων drones (swarm/alerts) και, αν βλέπει
     κι αυτό το ίδιο αντικείμενο, στέλνει επιβεβαίωση (swarm/confirmations)

Χρήση:
  python3 drone.py drone_1 videos/drone1.mp4
"""
import sys
import time
from datetime import datetime, timezone

import cv2

from yolo_vision import detect, draw
from mqtt_client import SwarmClient, DETECTIONS, DECISION, ALERTS, CONFIRMATIONS

DRONE_ID = sys.argv[1]
SOURCE = sys.argv[2]

FRAME_STEP = 60   # αναλύουμε 1 στα 10 frames (το YOLO στη CPU είναι αργό)
COOLDOWN = 120     # δευτ. πριν ξαναστείλουμε την ίδια κατηγορία αντικειμένου

# Εικονικές θέσεις των drones στον χώρο [x, y, ύψος] σε μέτρα.
# drone_1 - drone_2: 30 m (κοντά), drone_1 - drone_3: 80 m (μακριά).
POSITIONS = {
    "drone_1": [0.0, 0.0, 30.0],
    "drone_2": [30.0, 0.0, 30.0],
    "drone_3": [80.0, 0.0, 30.0],
}

last_sent = {}    # κατηγορία -> πότε τη στείλαμε τελευταία φορά στο LLM
last_seen = {}    # κατηγορία -> πότε την είδαμε τελευταία φορά στην κάμερα
last_answer = ""  # η τελευταία απάντηση του LLM, για να φαίνεται πάνω στο βίντεο


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] [{DRONE_ID}] {text}", flush=True)


def direction(bbox, width):
    """Πού βρίσκεται το αντικείμενο στο κάδρο: αριστερά, μπροστά ή δεξιά."""
    x1, _, x2, _ = bbox
    center = (x1 + x2) / 2 / width
    if center < 0.33:
        return "left"
    if center > 0.66:
        return "right"
    return "front"


# ---------- Τι κάνει το drone όταν λαμβάνει μηνύματα ----------

def on_decision(topic, data):
    """Η απάντηση του LLaMA για κάτι που είδα εγώ."""
    global last_answer
    last_answer = f"{data['object']}: {data['risk_level']} / {data['action']}"
    log(f"LLM ({data.get('decision_source')}): {data['recommendation']}")
    log(f"     risk={data['risk_level']}  action={data['action']}")
    if "safety_overrides" in data:
        log(f"     (ο έλεγχος ασφαλείας διόρθωσε το LLaMA: {data['safety_overrides']})")


def on_alert(topic, data):
    """Ειδοποίηση από άλλο drone. Αν βλέπω κι εγώ το ίδιο, το επιβεβαιώνω."""
    if data["drone_id"] == DRONE_ID:
        return
    obj = data["object"]
    log(f"Ειδοποίηση από {data['drone_id']}: {obj} (risk={data['risk_level']})")
    if time.time() - last_seen.get(obj, 0) < COOLDOWN:
        client.publish(CONFIRMATIONS, {
            "drone_id": DRONE_ID,
            "confirms": data["drone_id"],
            "object": obj,
        })
        log(f"Επιβεβαιώνω στο {data['drone_id']}: βλέπω κι εγώ {obj}")


def on_confirmation(topic, data):
    """Άλλο drone επιβεβαίωσε κάτι που είδα εγώ."""
    if data["confirms"] == DRONE_ID:
        log(f"Το {data['drone_id']} επιβεβαίωσε ότι βλέπει κι αυτό {data['object']}")


# ---------- Σύνδεση στο σμήνος ----------

client = SwarmClient(DRONE_ID)
client.subscribe(DECISION.format(id=DRONE_ID), on_decision)
client.subscribe(ALERTS, on_alert)
client.subscribe(CONFIRMATIONS, on_confirmation)

# ---------- Κάμερα: αρχείο βίντεο ή (μπόνους) κάμερα Gazebo ----------

if SOURCE.startswith("udpsrc"):
    cap = cv2.VideoCapture(SOURCE, cv2.CAP_GSTREAMER)
else:
    cap = cv2.VideoCapture(SOURCE)

if not cap.isOpened():
    log(f"Δεν άνοιξε η πηγή βίντεο: {SOURCE}")
    sys.exit(1)

log(f"Ξεκίνησα. Πηγή: {SOURCE}")

# ---------- Κύριος βρόχος ----------

frame_no = 0
try:
    while True:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # τέλος βίντεο -> από την αρχή
            continue

        frame_no += 1
        if frame_no % FRAME_STEP:
            continue

        detections = detect(frame)
        width = frame.shape[1]
        now = time.time()

        # Ομαδοποίηση ανά κατηγορία: κρατάμε πόσα βρήκαμε και το πιο σίγουρο
        groups = {}
        for d in detections:
            obj = d["object"]
            last_seen[obj] = now
            if obj not in groups:
                groups[obj] = {"count": 0, "best": d}
            groups[obj]["count"] += 1
            if d["confidence"] > groups[obj]["best"]["confidence"]:
                groups[obj]["best"] = d

        # Ένα μήνυμα ανά κατηγορία, το πολύ μία φορά ανά COOLDOWN δευτ.
        for obj, g in groups.items():
            if now - last_sent.get(obj, 0) < COOLDOWN:
                continue
            last_sent[obj] = now
            best = g["best"]
            client.publish(DETECTIONS.format(id=DRONE_ID), {
                "drone_id": DRONE_ID,
                "object": obj,
                "count": g["count"],
                "confidence": best["confidence"],
                "direction": direction(best["bbox"], width),
                "bbox": best["bbox"],
                "location": POSITIONS.get(DRONE_ID, [0.0, 0.0, 30.0]),
                "frame": frame_no,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            log(f"YOLO: {obj} x{g['count']} (conf={best['confidence']}) -> στάλθηκε στο LLM")

        # Live παράθυρο: boxes + η τελευταία απάντηση του LLM
        view = draw(frame, detections)
        cv2.putText(view, f"{DRONE_ID}  LLM: {last_answer}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow(DRONE_ID, view)
        if cv2.waitKey(1) == 27:   # ESC για έξοδο
            break
except KeyboardInterrupt:
    pass
finally:
    cap.release()
    cv2.destroyAllWindows()
    client.stop()
    log("Σταμάτησα.")
