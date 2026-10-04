"""Unit tests (no real LLM needed).

Usage:
    cd communication_node/llm_module
    python3 -m pytest test_llm_module.py -v
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_decision
from llm_client import LLMUnavailable, OllamaClient
from llm_decision import LLMDecisionMaker, interpret_drone_message
from rule_based_fallback import rule_based_decision
from safety import apply_safety_override
from scenarios import SCENARIOS
from schema import InvalidDecision, parse_and_validate
from swarm_context import summarize_history


def reply(risk="low", action="continue_mission", rec="Continue.", broadcast=False, target="none",
          desc="The drone sees fire."):
    return json.dumps({"description": desc, "risk_level": risk, "action": action, "recommendation": rec,
                       "broadcast": broadcast, "target_drone": target})


class FakeLLM:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


TREE_8M = {"drone_id": "drone_1", "object": "tree", "distance": 8, "direction": "front", "confidence": 0.9}
MQTT_FIRE = {"drone_id": "drone_1", "object": "fire", "location": [120, 80, 420, 500],
             "size": [300, 420], "velocity": [0, 0, 0]}


# --- backwards compatibility with the rest of the team -----------------------

def test_node_style_usage_unchanged():
    maker = LLMDecisionMaker(drone_id="llm_decision_node", use_llm=False, keep_history=True)
    d = maker.interpret(MQTT_FIRE)
    for key in ("description", "risk_level", "action", "recommendation", "broadcast", "target_drone",
                "decision_source", "decision_time", "module_id"):
        assert key in d
    assert d["decision_source"] == "rule_based_fallback"


def test_drone_integration_style_call():
    d = interpret_drone_message({"drone_id": "drone_1", "object": "fire", "distance": 5.0,
                                 "direction": "front", "confidence": 0.95, "location": [1.0, 2.0, 10.0]})
    assert d["risk_level"] == "high" and d["action"] == "emergency_stop"


def test_env_variable_enables_llm(monkeypatch):
    monkeypatch.setenv("DRONE_USE_LLM", "1")
    monkeypatch.setattr(llm_decision, "_shared_makers", {})
    monkeypatch.setattr(llm_decision, "default_llm_client", lambda: FakeLLM(reply("high", "notify_swarm", "x", True, "all")))
    assert interpret_drone_message(MQTT_FIRE)["decision_source"] == "llm"


def test_direction_from_bbox():
    maker = LLMDecisionMaker()
    assert maker._normalize_message({"location": [0, 0, 100, 100]})["direction"] == "left"
    assert maker._normalize_message({"location": [800, 0, 1000, 100]})["direction"] == "right"


# --- rules ----------------------------------------------------------------------

def test_close_object_wins_over_low_confidence():
    d = rule_based_decision({"object": "building", "distance": 3, "confidence": 0.4, "direction": "front"})
    assert d["action"] == "emergency_stop"


def test_missing_confidence_is_not_low():
    assert rule_based_decision({"object": "fire"})["action"] == "notify_swarm"


def test_rules_survive_broken_input():
    assert rule_based_decision({"object": None, "distance": "far", "confidence": "high"})["action"] == "continue_mission"


# --- schema ---------------------------------------------------------------------

def test_parse_with_fences_and_strings():
    d = parse_and_validate('```json\n{"description":" The drone   sees fire. ","risk_level":"HIGH",'
                           '"action":"Notify Swarm","recommendation":"x","broadcast":"false","target_drone":"drone_2"}\n```')
    assert d == {"description": "The drone sees fire.", "risk_level": "high", "action": "notify_swarm", "recommendation": "x",
                 "broadcast": False, "target_drone": "drone_2"}


@pytest.mark.parametrize("bad", [
    "", "no json here", "[1]",
    '{"risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":true,"target_drone":"all"}',  # no description
    '{"description":"  ","risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":true,"target_drone":"all"}',
    '{"description":"d","risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":true}',
    '{"description":"d","risk_level":"extreme","action":"notify_swarm","recommendation":"x","broadcast":true,"target_drone":"all"}',
    '{"description":"d","risk_level":"high","action":"fly_to_moon","recommendation":"x","broadcast":true,"target_drone":"all"}',
    '{"description":"d","risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":"maybe","target_drone":"all"}',
    '{"description":"d","risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":true,"target_drone":"all drones!"}',
])
def test_parse_rejects_invalid(bad):
    with pytest.raises(InvalidDecision):
        parse_and_validate(bad)


# --- LLM path -------------------------------------------------------------------

def test_llm_answer_used():
    llm = FakeLLM(reply("medium", "update_awareness_map", "Map the car.", True, "all", desc="The drone sees a car."))
    d = LLMDecisionMaker(use_llm=True, llm_client=llm).interpret(
        {"drone_id": "drone_1", "object": "car", "distance": 30, "confidence": 0.8})
    assert d["decision_source"] == "llm" and d["recommendation"] == "Map the car."
    assert "llm_latency_ms" in d


def test_fallback_when_llm_down():
    d = LLMDecisionMaker(use_llm=True, llm_client=FakeLLM(LLMUnavailable("down"))).interpret(TREE_8M)
    assert d["decision_source"] == "rule_based_fallback" and "LLMUnavailable" in d["fallback_reason"]
    assert d["action"] == "avoid_obstacle"


def test_fallback_on_garbage():
    d = LLMDecisionMaker(use_llm=True, llm_client=FakeLLM("just fly away")).interpret(TREE_8M)
    assert d["decision_source"] == "rule_based_fallback"


def test_safety_corrects_unsafe_llm():
    d = LLMDecisionMaker(use_llm=True, llm_client=FakeLLM(reply())).interpret(TREE_8M)
    assert d["decision_source"] == "llm+safety"
    assert (d["risk_level"], d["action"], d["broadcast"], d["target_drone"]) == ("high", "avoid_obstacle", True, "all")
    assert "action_not_allowed" in d["safety_overrides"]


def test_escalation_without_evidence_is_blocked():
    # The real llama3.2:3b failure: emergency_stop / high for a car 40 m away.
    msg = {"drone_id": "drone_1", "object": "car", "distance": 40, "confidence": 0.35}
    final, overrides = apply_safety_override(msg, parse_and_validate(reply("high", "emergency_stop", "Stop.", True, "all")))
    assert final["risk_level"] == "low" and final["action"] == "verify_detection"
    assert {"action_not_allowed", "unsupported_escalation"} <= set(overrides)


def test_escalation_with_swarm_evidence_is_allowed():
    msg = {"drone_id": "drone_1", "object": "fire", "confidence": 0.4, "location": [10, 3, 10]}
    history = [{"drone_id": "drone_2", "object": "smoke", "confidence": 0.85, "location": [12, 4, 10]}]
    final, overrides = apply_safety_override(msg, parse_and_validate(reply("high", "notify_swarm", "Fire confirmed.", True, "all")), history)
    assert overrides == [] and final["risk_level"] == "high"


def test_far_or_same_drone_reports_are_not_evidence():
    from safety import has_swarm_evidence
    msg = {"drone_id": "drone_1", "object": "fire", "location": [0, 0, 10]}
    assert not has_swarm_evidence(msg, [{"drone_id": "drone_2", "object": "fire", "location": [200, 0, 10]}])
    assert not has_swarm_evidence(msg, [{"drone_id": "drone_1", "object": "fire", "location": [1, 0, 10]}])
    assert not has_swarm_evidence(msg, [{"drone_id": "drone_2", "object": "fire", "confidence": 0.2}])


def test_allowed_actions():
    from safety import allowed_actions
    assert allowed_actions({"object": "car", "distance": 3}) == ["emergency_stop"]
    assert set(allowed_actions({"object": "car", "distance": 8})) == {"emergency_stop", "avoid_obstacle"}
    far_fire = allowed_actions({"object": "fire"})
    assert "emergency_stop" not in far_fire and "continue_mission" not in far_fire and "track_person" not in far_fire
    assert "track_person" in allowed_actions({"object": "person", "distance": 30})
    assert "track_person" not in allowed_actions({"object": "kite"})


def test_schema_sent_to_ollama_has_only_allowed_actions():
    llm = FakeLLM(reply("high", "notify_swarm", "x", True, "all"))
    seen = {}
    def client(prompt, schema=None):
        seen["schema"] = schema
        return llm(prompt)
    LLMDecisionMaker(use_llm=True, llm_client=client).interpret(MQTT_FIRE)
    assert "emergency_stop" not in seen["schema"]["properties"]["action"]["enum"]
    assert "notify_swarm" in seen["schema"]["properties"]["action"]["enum"]


def test_fire_is_always_broadcast():
    final, overrides = apply_safety_override({"object": "fire"}, parse_and_validate(reply("high", "notify_swarm", "x", False, "none")))
    assert final["broadcast"] and final["target_drone"] == "all"


# --- swarm context --------------------------------------------------------------

def test_history_reaches_prompt_without_current_message():
    sc = next(s for s in SCENARIOS if s["name"] == "uncertain_fire_confirmed_by_swarm")
    llm = FakeLLM(reply("high", "hover_and_monitor", "Fire confirmed. Hold and monitor.", True, "all"))
    maker = LLMDecisionMaker(use_llm=True, llm_client=llm)
    for m in sc["context"]:
        maker._remember(maker._normalize_message(m))
    d = maker.interpret(sc["message"])
    history_part = llm.prompts[0].split("Recent reports")[1].split("Report:")[0]
    assert "drone_2 (" in history_part and ": fire" in history_part
    assert "drone_3 (" in history_part and ": smoke" in history_part
    assert "m away" in history_part
    assert "drone_1" not in history_part      # current message not duplicated
    assert d["risk_level"] == "high"


def test_old_reports_ignored():
    hist = [{"drone_id": "d2", "object": "smoke", "timestamp": "2026-07-10T12:00:00+00:00"}]
    cur = {"drone_id": "d1", "object": "car", "timestamp": "2026-07-10T12:05:00+00:00"}
    assert summarize_history(hist, cur) == "none"


def test_history_is_bounded():
    maker = LLMDecisionMaker(max_history_items=3)
    for i in range(10):
        maker.interpret({"drone_id": f"d{i}", "object": "tree"})
    assert [m["drone_id"] for m in maker.history] == ["d7", "d8", "d9"]


# --- Ollama client against a fake server ----------------------------------------

@pytest.fixture
def fake_ollama():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode())

        def do_POST(self):
            received.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({"message": {"content": reply("high", "notify_swarm", "Alert.", True, "all")}}).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", received
    server.shutdown()


def test_ollama_roundtrip(fake_ollama):
    url, received = fake_ollama
    client = OllamaClient(model="llama3.2:3b", url=url, json_schema={"type": "object"})
    assert client.is_available()
    d = LLMDecisionMaker(use_llm=True, llm_client=client).interpret(MQTT_FIRE)
    assert d["decision_source"] == "llm"
    assert received["stream"] is False and received["keep_alive"] == "30m"
    assert "emergency_stop" not in received["format"]["properties"]["action"]["enum"]


def test_ollama_unreachable():
    client = OllamaClient(url="http://127.0.0.1:9", timeout=1)
    assert not client.is_available()
    with pytest.raises(LLMUnavailable):
        client("hi")


# --- swarm-v2 feedback (description, count, heavy_vehicle, low+notify) -----------

SWARM_MSG = {"drone_id": "drone_1", "object": "person", "count": 61, "confidence": 0.7, "direction": "left",
             "bbox": [110, 558, 126, 586], "location": [0.0, 0.0, 30.0], "frame": 450,
             "timestamp": "2026-10-04T11:25:03+00:00"}


def test_description_from_llm_is_kept():
    llm = FakeLLM(reply("high", "hover_and_monitor", "Hold and monitor the crowd.", True, "all",
                        desc="The drone sees a crowd of about 60 people on the left."))
    d = LLMDecisionMaker(use_llm=True, llm_client=llm).interpret(SWARM_MSG)
    assert d["description"] == "The drone sees a crowd of about 60 people on the left."
    assert d["decision_source"] == "llm"


def test_rules_also_give_description():
    d = LLMDecisionMaker().interpret(SWARM_MSG)
    assert d["description"] == "The drone sees a crowd of about 61 people on the left."
    assert d["action"] == "hover_and_monitor"


def test_count_and_compact_fields_in_prompt():
    llm = FakeLLM(reply("high", "hover_and_monitor", "x", True, "all"))
    LLMDecisionMaker(use_llm=True, llm_client=llm).interpret(SWARM_MSG)
    report_line = [l for l in llm.prompts[0].splitlines() if l.startswith("Report:")][0]
    assert '"count":61' in report_line
    for noise in ("bbox", "frame", "location", "timestamp"):
        assert noise not in report_line


def test_prompt_starts_with_identical_static_part():
    a, b = FakeLLM(reply()), FakeLLM(reply())
    LLMDecisionMaker(use_llm=True, llm_client=a).interpret(SWARM_MSG)
    LLMDecisionMaker(use_llm=True, llm_client=b).interpret({"drone_id": "drone_3", "object": "tree"})
    assert a.prompts[0].split("Recent reports")[0] == b.prompts[0].split("Recent reports")[0]


def test_prompt_is_short():
    llm = FakeLLM(reply())
    maker = LLMDecisionMaker(use_llm=True, llm_client=llm)
    for i in range(10):   # full history
        maker.interpret({"drone_id": f"drone_{i % 3 + 1}", "object": "car", "count": 3,
                         "location": [30.0 * (i % 3), 0, 30], "timestamp": f"2026-10-04T11:25:0{i}+00:00"})
    assert len(llm.prompts[-1]) < 1600      # ~400 tokens (was ~2400 chars)


def test_heavy_vehicle_never_high_even_with_neighbour_evidence():
    hist = [{"drone_id": "drone_2", "object": "heavy_vehicle", "count": 2, "confidence": 0.8, "location": [30, 0, 30]}]
    msg = {"drone_id": "drone_1", "object": "heavy vehicles", "count": 3, "confidence": 0.7, "location": [0, 0, 30]}
    final, overrides = apply_safety_override(msg, parse_and_validate(reply("high", "hover_and_monitor", "Stop.", True, "all")), hist)
    assert final["risk_level"] == "medium" and final["action"] == "update_awareness_map"
    assert "escalation_capped" in overrides


def test_no_low_risk_swarm_alert():
    # The demo bug: "low: notify_swarm".
    msg = {"drone_id": "drone_1", "object": "boat", "confidence": 0.9}   # rules: medium
    final, _ = apply_safety_override(msg, parse_and_validate(reply("low", "notify_swarm", "Alert all.", True, "all")))
    assert not (final["risk_level"] == "low" and final["action"] == "notify_swarm")
    msg = {"drone_id": "drone_1", "object": "kite", "confidence": 0.9}   # rules: low/continue
    final, overrides = apply_safety_override(msg, parse_and_validate(reply("low", "notify_swarm", "Alert all.", True, "all")))
    assert (final["action"], final["broadcast"], final["target_drone"]) == ("continue_mission", False, "none")
    assert "low_risk_no_alert" in overrides


def test_unsupported_escalation_resets_reaction_but_keeps_description():
    msg = {"drone_id": "drone_3", "object": "kite", "confidence": 0.9, "location": [80, 0, 30]}
    final, overrides = apply_safety_override(msg, parse_and_validate(
        reply("high", "notify_swarm", "Alert all.", True, "all", desc="The drone sees a kite.")), [])
    assert (final["risk_level"], final["action"], final["broadcast"]) == ("low", "continue_mission", False)
    assert final["description"] == "The drone sees a kite."


def test_yolo_class_names_are_understood():
    from rule_based_fallback import object_name
    assert object_name("heavy vehicles") == "heavy_vehicle"
    assert object_name("Light Vehicles") == "light_vehicle"
    assert object_name("buildings") == "building"
    assert rule_based_decision({"object": "heavy vehicles"})["risk_level"] == "medium"


# --- third evaluation feedback: invented descriptions, verify/map rules ---------

REAL_BAD_DESCRIPTIONS = [   # produced by llama3.2:3b in evaluate.py (2026-10-04)
    ({"object": "person", "count": 1, "direction": "front"}, "The drone sees a person on the left.", "wrong_direction"),
    ({"object": "person", "count": 3, "direction": "right"}, "The drone sees a person on the right.", "wrong_count"),
    ({"object": "car", "count": 5, "direction": "front"}, "The drone sees a car on the front, 15 meters away.", "invented_distance"),
    ({"object": "car", "count": 25, "direction": "right"}, "A car is 15 meters to the right.", "invented_distance"),
]
GOOD_DESCRIPTIONS = [
    ({"object": "person", "count": 61, "direction": "left"}, "The drone sees a crowd of about 60 people on the left."),
    ({"object": "heavy_vehicle", "count": 3, "direction": "left"}, "The drone sees three trucks on the left."),
    ({"object": "tree", "count": 12, "direction": "front"}, "The drone sees about 12 trees ahead."),
    ({"object": "boat", "count": 1, "direction": "front"}, "A single boat is in front of the drone."),
    ({"object": "car", "count": 1, "direction": "left", "distance": 8}, "A car is 8 m away on the left."),
]


@pytest.mark.parametrize("msg,text,problem", REAL_BAD_DESCRIPTIONS)
def test_invented_descriptions_are_detected(msg, text, problem):
    from safety import description_problem
    assert description_problem(msg, text) == problem


@pytest.mark.parametrize("msg,text", GOOD_DESCRIPTIONS)
def test_correct_descriptions_pass(msg, text):
    from safety import description_problem
    assert description_problem(msg, text) is None


def test_invented_description_replaced_by_facts():
    msg = {"drone_id": "drone_2", "object": "car", "count": 5, "confidence": 0.88, "direction": "front"}
    llm = FakeLLM(reply("medium", "update_awareness_map", "Map the cars.", True, "all",
                        desc="The drone sees a car on the front, 15 meters away."))
    d = LLMDecisionMaker(use_llm=True, llm_client=llm).interpret(msg)
    assert d["description"] == "The drone sees 5 cars in front."
    assert d["description_rejected"] == "The drone sees a car on the front, 15 meters away."
    assert "description_fixed" in d["safety_overrides"]


def test_verify_only_for_uncertain_and_no_uncertain_objects_on_map():
    from safety import allowed_actions
    assert "verify_detection" not in allowed_actions({"object": "person"})                 # no confidence
    assert "verify_detection" not in allowed_actions({"object": "car", "confidence": 0.8})
    uncertain = allowed_actions({"object": "car", "confidence": 0.35, "distance": 20})
    assert "verify_detection" in uncertain and "update_awareness_map" not in uncertain


def test_facts_line_in_prompt():
    llm = FakeLLM(reply("high", "hover_and_monitor", "x", True, "all"))
    LLMDecisionMaker(use_llm=True, llm_client=llm).interpret(SWARM_MSG)
    assert "Facts: 61 people, on the left, distance unknown" in llm.prompts[0]
    assert "60 people" not in llm.prompts[0]      # no copyable example matching real data
