
import sys
import time
from datetime import datetime, timezone

import cv2

from yolo_vision import detect, draw
from mqtt_client import SwarmClient, DETECTIONS, DECISION, ALERTS, CONFIRMATIONS

VERIFY_REQUEST = "swarm/verify_request"   # νέο topic: αίτημα επαλήθευσης προς το σμήνος

DRONE_ID = sys.argv[1]
SOURCE = sys.argv[2]

FRAME_STEP = 60        # PATROL: αναλύουμε 1 στα 60 frames
FRAME_STEP_FAST = 15   # TRACKING / VERIFYING: 1 στα 15 frames
COOLDOWN = 120         # δευτ. πριν ξαναστείλουμε την ίδια κατηγορία στο LLM
HOVER_TIME = 8         # δευτ. ακινησίας για hover_and_monitor / emergency_stop
MIN_HOVER = 5          # δευτ. που μένει σταματημένο τουλάχιστον, ώστε να φαίνεται
WAIT_TIME = 20         # δευτ. που περιμένουμε απάντηση από το σμήνος
VERIFY_TIME = 15       # δευτ. που ψάχνουμε όταν μας ζητάνε επαλήθευση
TRACK_TIME = 30        # δευτ. στενής παρακολούθησης μετά από track_person

HOVER_ACTIONS = {"hover_and_monitor", "emergency_stop", "avoid_obstacle"}

# Εικονικές θέσεις των drones στον χώρο [x, y, ύψος] σε μέτρα.
# drone_1 - drone_2: 30 m (κοντά), drone_1 - drone_3: 80 m (μακριά).
POSITIONS = {
    "drone_1": [0.0, 0.0, 30.0],
    "drone_2": [30.0, 0.0, 30.0],
    "drone_3": [80.0, 0.0, 30.0],
}

MODE_COLORS = {   # χρώματα OpenCV (BGR)
    "PATROL": (0, 200, 0),
    "HOVER": (0, 0, 255),
    "TRACKING": (0, 165, 255),
    "VERIFYING": (0, 255, 255),
}

last_sent = {}      # κατηγορία -> πότε τη στείλαμε τελευταία φορά στο LLM
last_answer = ""    # η τελευταία απόφαση του LLM, για να φαίνεται πάνω στο βίντεο
mode = "PATROL"     # η κατάσταση που όρισε η τελευταία απόφαση
mode_until = 0      # μέχρι πότε ισχύει
my_request = None   # το δικό μου αίτημα επαλήθευσης: {"object", "action", "until"}
after_hover = None  # σε τι κατάσταση πάμε όταν τελειώσει το HOVER
verify_task = None  # αίτημα άλλου drone που εξυπηρετώ: {"object", "requester", "until"}


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] [{DRONE_ID}] {text}", flush=True)


def set_mode(new_mode, seconds):
    global mode, mode_until
    mode = new_mode
    mode_until = time.time() + seconds


def current_mode():
    if verify_task is not None:
        return "VERIFYING"            # η βοήθεια σε άλλο drone έχει προτεραιότητα
    if time.time() < mode_until:
        return mode
    return "PATROL"


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
    """Η απόφαση του LLaMA για κάτι που είδα εγώ: αντιδρώ."""
    global last_answer, my_request
    obj, risk, action = data["object"], data["risk_level"], data["action"]
    last_answer = f"{obj}: {risk} / {action}"
    log(f"LLM ({data.get('decision_source')}): {data.get('description', '')}")
    log(f"     πρόταση: {data['recommendation']}")
    log(f"     risk={risk}  action={action}")
    if "safety_overrides" in data:
        log(f"     (ο έλεγχος ασφαλείας διόρθωσε το LLaMA: {data['safety_overrides']})")

    if (risk == "high" or action == "verify_detection") and my_request is None:
        my_request = {"object": obj, "action": action, "until": time.time() + WAIT_TIME,
                      "since": time.time()}
        set_mode("HOVER", WAIT_TIME)
        client.publish(VERIFY_REQUEST, {"drone_id": DRONE_ID, "object": obj, "reason": action})
        log(f"-> Σταματάω και ζητάω από το σμήνος να επαληθεύσει: {obj}")
    elif action in HOVER_ACTIONS:
        set_mode("HOVER", HOVER_TIME)
        log(f"-> Σταματάω και παρακολουθώ για {HOVER_TIME} δευτ.")
    elif action == "track_person":
        set_mode("TRACKING", TRACK_TIME)
        log(f"-> Παρακολουθώ στενά για {TRACK_TIME} δευτ.")


def on_alert(topic, data):
    """Ειδοποίηση για όλο το σμήνος από άλλο drone."""
    if data["drone_id"] != DRONE_ID:
        log(f"Ειδοποίηση από {data['drone_id']}: {data['object']} (risk={data['risk_level']})")


def on_verify_request(topic, data):
    """Άλλο drone μου ζητάει να ελέγξω αν βλέπω κι εγώ κάτι."""
    global verify_task
    if data["drone_id"] == DRONE_ID:
        return
    if verify_task is not None:
        log(f"Αίτημα από {data['drone_id']} για {data['object']}: είμαι απασχολημένο, το αγνοώ")
        return
    verify_task = {"object": data["object"], "requester": data["drone_id"],
                   "until": time.time() + VERIFY_TIME}
    log(f"Το {data['drone_id']} ζητάει επαλήθευση για {data['object']}: ψάχνω...")


def on_confirmation(topic, data):
    """Απάντηση στο δικό μου αίτημα επαλήθευσης."""
    global my_request, after_hover
    if data["confirms"] != DRONE_ID:
        return
    if data.get("found"):
        log(f"Το {data['drone_id']} επιβεβαίωσε: βλέπει κι αυτό {data['object']} x{data.get('count', 1)}")
    else:
        log(f"Το {data['drone_id']} δεν βλέπει {data['object']}")
    if my_request is not None and my_request["object"] == data["object"]:
        after_hover = "TRACKING" if my_request["action"] == "track_person" else "PATROL"
        set_mode("HOVER", max(0, my_request["since"] + MIN_HOVER - time.time()))
        my_request = None
        log("-> Επιβεβαιώθηκε, συνεχίζω σε λίγο")


# ---------- Σύνδεση στο σμήνος ----------

client = SwarmClient(DRONE_ID)
client.subscribe(DECISION.format(id=DRONE_ID), on_decision)
client.subscribe(ALERTS, on_alert)
client.subscribe(VERIFY_REQUEST, on_verify_request)
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


def show(view, m):
    """Δείχνει το frame με την κατάσταση του drone και την τελευταία απόφαση."""
    label = f"{DRONE_ID}  [{m}]"
    if m == "HOVER" and my_request is not None:
        label += "  waiting for swarm..."
    out = view.copy()
    cv2.putText(out, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, MODE_COLORS[m], 2)
    cv2.putText(out, f"LLM: {last_answer}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.imshow(DRONE_ID, out)
    return cv2.waitKey(30 if m == "HOVER" else 1) != 27   # ESC για έξοδο


# ---------- Κύριος βρόχος ----------

frame_no = 0
last_view = None
shown_mode = "PATROL"
try:
    while True:
        now = time.time()
        m = current_mode()
        if after_hover is not None and m == "PATROL":
            if after_hover == "TRACKING":
                set_mode("TRACKING", TRACK_TIME)
                log("-> Συνεχίζω παρακολουθώντας στενά")
            else:
                log("-> Συνεχίζω την περιπολία")
            after_hover = None
            m = current_mode()
        if m != shown_mode:
            log(f"Κατάσταση: {shown_mode} -> {m}")
            shown_mode = m

        # Κανένα drone δεν απάντησε στο αίτημά μου μέσα στον χρόνο
        if my_request is not None and now > my_request["until"]:
            log(f"Κανένα drone δεν απάντησε για {my_request['object']}, συνεχίζω την περιπολία")
            my_request = None

        # HOVER: το drone μένει ακίνητο, άρα η εικόνα δεν αλλάζει
        if m == "HOVER" and last_view is not None:
            if not show(last_view, m):
                break
            continue

        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # τέλος βίντεο -> από την αρχή
            continue

        frame_no += 1
        step = FRAME_STEP if m == "PATROL" else FRAME_STEP_FAST
        if frame_no % step:
            continue

        detections = detect(frame)
        width = frame.shape[1]

        # Ομαδοποίηση ανά κατηγορία: πόσα βρήκαμε και το πιο σίγουρο
        groups = {}
        for d in detections:
            obj = d["object"]
            if obj not in groups:
                groups[obj] = {"count": 0, "best": d}
            groups[obj]["count"] += 1
            if d["confidence"] > groups[obj]["best"]["confidence"]:
                groups[obj]["best"] = d

        # Ένα μήνυμα ανά κατηγορία προς το LLM, το πολύ μία φορά ανά COOLDOWN
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

        # VERIFYING: ψάχνω αυτό που μου ζήτησε άλλο drone
        task = verify_task
        if task is not None:
            obj = task["object"]
            if obj in groups:
                client.publish(CONFIRMATIONS, {
                    "drone_id": DRONE_ID, "confirms": task["requester"], "object": obj,
                    "found": True, "count": groups[obj]["count"],
                    "confidence": groups[obj]["best"]["confidence"],
                })
                log(f"Βρήκα {obj} x{groups[obj]['count']} -> απαντάω στο {task['requester']}")
                verify_task = None
            elif now > task["until"]:
                client.publish(CONFIRMATIONS, {
                    "drone_id": DRONE_ID, "confirms": task["requester"], "object": obj,
                    "found": False,
                })
                log(f"Δεν βρήκα {obj} -> απαντάω στο {task['requester']}")
                verify_task = None

        last_view = draw(frame, detections)
        if not show(last_view, current_mode()):
            break
except KeyboardInterrupt:
    pass
finally:
    cap.release()
    cv2.destroyAllWindows()
    client.stop()
    log("Σταμάτησα.")
