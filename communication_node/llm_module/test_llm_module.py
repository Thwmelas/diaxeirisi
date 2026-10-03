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


def reply(risk="low", action="continue_mission", rec="Continue.", broadcast=False, target="none"):
    return json.dumps({"risk_level": risk, "action": action, "recommendation": rec,
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
    for key in ("risk_level", "action", "recommendation", "broadcast", "target_drone",
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
    d = parse_and_validate('```json\n{"risk_level":"HIGH","action":"Notify Swarm","recommendation":"x",'
                           '"broadcast":"false","target_drone":"drone_2"}\n```')
    assert d == {"risk_level": "high", "action": "notify_swarm", "recommendation": "x",
                 "broadcast": False, "target_drone": "drone_2"}


@pytest.mark.parametrize("bad", [
    "", "no json here", "[1]",
    '{"risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":true}',
    '{"risk_level":"extreme","action":"notify_swarm","recommendation":"x","broadcast":true,"target_drone":"all"}',
    '{"risk_level":"high","action":"fly_to_moon","recommendation":"x","broadcast":true,"target_drone":"all"}',
    '{"risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":"maybe","target_drone":"all"}',
    '{"risk_level":"high","action":"notify_swarm","recommendation":"x","broadcast":true,"target_drone":"all drones!"}',
])
def test_parse_rejects_invalid(bad):
    with pytest.raises(InvalidDecision):
        parse_and_validate(bad)


# --- LLM path -------------------------------------------------------------------

def test_llm_answer_used():
    llm = FakeLLM(reply("medium", "update_awareness_map", "Map the car.", True, "all"))
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
    assert "collision_action" in d["safety_overrides"]


def test_safety_allows_escalation():
    msg = {"object": "car", "distance": 40, "confidence": 0.35}
    final, overrides = apply_safety_override(msg, parse_and_validate(reply("high", "hover_and_monitor", "Watch.", True, "all")))
    assert overrides == [] and final["risk_level"] == "high"


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
    history_part = llm.prompts[0].split("Recent reports")[1].split("Current report")[0]
    assert "drone_2: fire" in history_part and "drone_3: smoke" in history_part
    assert "m from the current report" in history_part
    assert "drone_1" not in history_part      # current message not duplicated
    assert d["risk_level"] == "high"


def test_old_reports_ignored():
    hist = [{"drone_id": "d2", "object": "smoke", "timestamp": "2026-07-10T12:00:00+00:00"}]
    cur = {"drone_id": "d1", "object": "car", "timestamp": "2026-07-10T12:05:00+00:00"}
    assert summarize_history(hist, cur) == "No recent reports."


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
    assert received["stream"] is False and received["format"] == {"type": "object"}


def test_ollama_unreachable():
    client = OllamaClient(url="http://127.0.0.1:9", timeout=1)
    assert not client.is_available()
    with pytest.raises(LLMUnavailable):
        client("hi")
