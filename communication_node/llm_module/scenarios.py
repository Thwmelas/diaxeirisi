"""Shared scenarios for test_scenarios.py, evaluate.py and the unit tests.

Messages use the real formats of the project:
  - MQTT payload (publisher.py): drone_id, object, location, size, velocity
  - drone_integration.py: drone_id, object, distance, direction, confidence, location [x, y, z]

"expect" lists the acceptable risk levels and actions (what a sensible operator
would want), so it also measures the rule engine, not just the LLM.
"context" = earlier reports the decision node already received.
"""

T = "2026-07-10T12:00:{:02d}+00:00"


def mqtt(drone, obj, loc, size=(2.0, 2.0), sec=0):
    return {"drone_id": drone, "object": obj, "location": list(loc), "size": list(size),
            "velocity": [0, 0, 0], "timestamp": T.format(sec)}


def yolo(drone, obj, dist, direction, conf, loc=(0.0, 0.0, 10.0), sec=0):
    return {"drone_id": drone, "object": obj, "distance": dist, "direction": direction,
            "confidence": conf, "location": list(loc), "timestamp": T.format(sec)}


SCENARIOS = [
    # Original team scenarios
    {"name": "fire_mqtt_bbox", "message": mqtt("drone_1", "fire", (120, 80, 420, 500), (300, 420)),
     "expect": {"risk": ["high"], "actions": ["notify_swarm", "hover_and_monitor"]}},
    {"name": "tree_mqtt_bbox", "message": mqtt("drone_2", "tree", (600, 100, 900, 700), (300, 600)),
     "expect": {"risk": ["low", "medium"], "actions": ["update_awareness_map", "continue_mission"]}},
    {"name": "building_4m", "message": yolo("drone_3", "building", 4, "front", 0.95),
     "expect": {"risk": ["high"], "actions": ["emergency_stop"]}},
    {"name": "car_low_conf", "message": yolo("drone_4", "car", 20, "left", 0.35),
     "expect": {"risk": ["low"], "actions": ["verify_detection", "continue_mission"]}},

    # Collisions
    {"name": "tree_8m", "message": yolo("drone_1", "tree", 8, "front", 0.89),
     "expect": {"risk": ["high"], "actions": ["avoid_obstacle", "emergency_stop"]}},
    {"name": "close_but_unsure", "message": yolo("drone_2", "building", 3, "front", 0.40),
     "expect": {"risk": ["high"], "actions": ["emergency_stop"]}},
    {"name": "fire_color_detector", "message": yolo("drone_1", "fire", 5.0, "front", 0.95, (4.2, -3.1, 10.0)),
     "expect": {"risk": ["high"], "actions": ["emergency_stop"]}},

    # Hazards / people (Gazebo world coordinates)
    {"name": "fire_mqtt_world", "message": mqtt("drone_2", "fire", (10.5, 3.2, 12.0)),
     "expect": {"risk": ["high"], "actions": ["notify_swarm", "hover_and_monitor"]}},
    {"name": "smoke_far", "message": yolo("drone_3", "smoke", 40, "right", 0.80),
     "expect": {"risk": ["high"], "actions": ["notify_swarm", "hover_and_monitor"]}},
    {"name": "person_far", "message": yolo("drone_2", "person", 25, "left", 0.92),
     "expect": {"risk": ["high"], "actions": ["track_person", "hover_and_monitor", "notify_swarm"]}},
    {"name": "person_mqtt", "message": mqtt("drone_4", "person", (1.0, 7.5, 10.0)),
     "expect": {"risk": ["high"], "actions": ["track_person", "hover_and_monitor", "notify_swarm"]}},

    # Nothing important / odd input
    {"name": "bus_mid", "message": yolo("drone_1", "bus", 30, "right", 0.85),
     "expect": {"risk": ["low", "medium"], "actions": ["update_awareness_map", "continue_mission"]}},
    {"name": "unknown_object", "message": mqtt("drone_1", "kite", (2.0, 2.0, 10.0)),
     "expect": {"risk": ["low"], "actions": ["continue_mission", "update_awareness_map"]}},
    {"name": "broken_values", "message": {"drone_id": "drone_5", "object": None, "distance": "far",
                                          "confidence": "high"},
     "expect": {"risk": ["low"], "actions": ["continue_mission", "verify_detection"]}},

    # Swarm context: earlier reports should change the answer
    {"name": "uncertain_fire_confirmed_by_swarm",
     "message": yolo("drone_1", "fire", 35, "front", 0.40, (10.0, 3.0, 10.0), sec=30),
     "context": [mqtt("drone_2", "fire", (11.0, 4.0, 12.0), sec=20),
                 yolo("drone_3", "smoke", 25, "left", 0.85, (9.0, 2.5, 11.0), sec=25)],
     "expect": {"risk": ["high"], "actions": ["notify_swarm", "hover_and_monitor"]}},
    {"name": "uncertain_person_confirmed",
     "message": yolo("drone_4", "person", 30, "left", 0.45, (-5.0, 6.0, 10.0), sec=40),
     "context": [yolo("drone_1", "person", 20, "front", 0.90, (-4.0, 6.5, 10.0), sec=35),
                 yolo("drone_2", "person", 22, "right", 0.88, (-5.5, 5.0, 10.0), sec=38)],
     "expect": {"risk": ["medium", "high"], "actions": ["track_person", "hover_and_monitor", "notify_swarm"]}},
    {"name": "uncertain_car_unrelated_context",
     "message": yolo("drone_1", "car", 40, "back", 0.35, (0.0, 0.0, 10.0), sec=50),
     "context": [mqtt("drone_2", "tree", (30.0, 30.0, 10.0), sec=45),
                 mqtt("drone_3", "building", (-25.0, 20.0, 10.0), sec=48)],
     "expect": {"risk": ["low"], "actions": ["verify_detection", "continue_mission"]}},
]


# ---------------------------------------------------------------------------
# swarm-v2 scenarios: real message format of drone_swarm_v2/drone.py
# (count, no distance, virtual positions drone_1 [0,0,30], drone_2 [30,0,30], drone_3 [80,0,30]).
# Written BEFORE running any LLM on them, so they work as a held-out test set
# (the guardrails were NOT tuned on these).
# ---------------------------------------------------------------------------
POS = {"drone_1": (0.0, 0.0, 30.0), "drone_2": (30.0, 0.0, 30.0), "drone_3": (80.0, 0.0, 30.0)}
T2 = "2026-10-04T11:25:{:02d}+00:00"


def v2(drone, obj, count, conf, direction, sec=0):
    return {"drone_id": drone, "object": obj, "count": count, "confidence": conf, "direction": direction,
            "bbox": [100, 500, 140, 580], "location": list(POS[drone]), "frame": 450 + sec,
            "timestamp": T2.format(sec)}


LOWMED = ["low", "medium"]
MAPPING = ["update_awareness_map", "continue_mission"]

SWARM_V2_SCENARIOS = [
    {"name": "v2_crowd_61", "message": v2("drone_1", "person", 61, 0.70, "left"),
     "expect": {"risk": ["high"], "actions": ["hover_and_monitor", "notify_swarm"]}},
    {"name": "v2_single_person", "message": v2("drone_3", "person", 1, 0.82, "front"),
     "expect": {"risk": ["high"], "actions": ["track_person", "hover_and_monitor"]}},
    {"name": "v2_three_people", "message": v2("drone_2", "person", 3, 0.66, "right"),
     "expect": {"risk": ["high"], "actions": ["track_person", "hover_and_monitor"]}},
    {"name": "v2_cars", "message": v2("drone_2", "car", 5, 0.88, "front"),
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_heavy_traffic", "message": v2("drone_1", "car", 25, 0.91, "right"),
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_heavy_vehicle_neighbour_sees_too",
     "message": v2("drone_1", "heavy_vehicle", 3, 0.74, "left", sec=10),
     "context": [v2("drone_2", "heavy_vehicle", 2, 0.80, "front", sec=6)],
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_light_vehicles", "message": v2("drone_3", "light_vehicle", 4, 0.62, "left"),
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_trees", "message": v2("drone_2", "tree", 12, 0.77, "front"),
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_building", "message": v2("drone_1", "building", 2, 0.85, "right"),
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_boat", "message": v2("drone_3", "boat", 1, 0.93, "front"),
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_plane", "message": v2("drone_2", "plane", 1, 0.90, "left"),
     "expect": {"risk": LOWMED, "actions": MAPPING}},
    {"name": "v2_person_confirmed_by_neighbour",
     "message": v2("drone_2", "person", 2, 0.58, "left", sec=20),
     "context": [v2("drone_1", "person", 40, 0.75, "front", sec=15)],
     "expect": {"risk": ["high"], "actions": ["track_person", "hover_and_monitor", "notify_swarm"]}},
    {"name": "v2_person_far_drone_is_not_evidence",
     "message": v2("drone_3", "car", 6, 0.80, "right", sec=30),
     "context": [v2("drone_1", "person", 50, 0.75, "front", sec=25),
                 v2("drone_2", "person", 8, 0.70, "left", sec=27)],
     "expect": {"risk": LOWMED, "actions": MAPPING}},
]
