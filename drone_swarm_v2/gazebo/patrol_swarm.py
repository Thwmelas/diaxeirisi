"""
patrol_swarm.py - Εκκινεί παράλληλα patrol για 3 drones.

Κάθε drone πετάει σε διαφορετικά τυχαία waypoints ταυτόχρονα,
κάνει 360° scan σε κάθε σημείο, και στέλνει YOLO+MQTT alerts.

Χρήση:
    source /opt/ros/humble/setup.bash
    source ~/drone_ws/install/setup.bash
    python3 patrol_swarm.py
"""

import subprocess
import sys
import os
import time

DRONES = ["px4_1", "px4_2", "px4_3"]
PATROL_SCRIPT = os.path.join(os.path.dirname(__file__), "patrol.py")
PYTHON = sys.executable


def main():
    processes = []

    print("Εκκίνηση patrol για όλα τα drones...")
    for drone_id in DRONES:
        env = os.environ.copy()
        env["PATROL_DRONE_ID"] = drone_id
        p = subprocess.Popen(
            [PYTHON, PATROL_SCRIPT],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append((drone_id, p))
        print(f"  ✓ {drone_id} patrol ξεκίνησε (PID {p.pid})")
        time.sleep(2)  # μικρή καθυστέρηση ανάμεσα στις εκκινήσεις

    print(f"\nΌλα τα drones πετούν. Ctrl+C για διακοπή.\n")

    try:
        while True:
            for drone_id, p in processes:
                line = p.stdout.readline()
                if line:
                    print(f"[{drone_id}] {line.rstrip()}")
            # έλεγξε αν κάποιο process τερμάτισε
            if all(p.poll() is not None for _, p in processes):
                print("Όλα τα drones ολοκλήρωσαν το patrol.")
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nΔιακοπή — σταματώ όλα τα drones...")
        for drone_id, p in processes:
            p.terminate()
        time.sleep(1)
        for drone_id, p in processes:
            p.kill()


if __name__ == '__main__':
    main()
