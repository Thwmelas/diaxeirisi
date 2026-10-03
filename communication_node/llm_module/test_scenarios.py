"""Run local scenarios for the LLM decision module.

Usage:
    cd communication_node/llm_module
    python3 test_scenarios.py            # rules only (no LLM needed)
    python3 test_scenarios.py --llm      # with Ollama
"""
from __future__ import annotations

import argparse
import json

from llm_decision import LLMDecisionMaker, default_llm_client
from scenarios import SCENARIOS


def run(use_llm: bool, model: str | None = None) -> None:
    client = None
    if use_llm:
        client = default_llm_client()
        if model:
            client.model = model
        if not client.is_available():
            print(f"[warning] {client.name} not available -> decisions fall back to rules.\n")
        else:
            client.warm_up()

    passed = 0
    for sc in SCENARIOS:
        maker = LLMDecisionMaker(drone_id="llm_test", use_llm=use_llm, llm_client=client)
        for earlier in sc.get("context", []):
            maker._remember(maker._normalize_message(earlier))
        decision = maker.interpret(sc["message"])
        ok = decision["risk_level"] in sc["expect"]["risk"] and decision["action"] in sc["expect"]["actions"]
        passed += ok

        print(f"[{'OK ' if ok else 'BAD'}] {sc['name']}")
        print("  input:   ", json.dumps(sc["message"]))
        if sc.get("context"):
            print(f"  context:  {len(sc['context'])} earlier reports")
        shown = {k: decision[k] for k in ("risk_level", "action", "broadcast", "target_drone", "decision_source")}
        print("  decision:", json.dumps(shown))
        print("  recommendation:", decision["recommendation"])
        for key in ("safety_overrides", "fallback_reason", "llm_latency_ms"):
            if key in decision:
                print(f"  {key}: {decision[key]}")
        print("-" * 70)
    print(f"\n{passed}/{len(SCENARIOS)} scenarios as expected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="use the LLM (Ollama)")
    parser.add_argument("--model", default=None, help="Ollama model, e.g. qwen2.5:3b")
    args = parser.parse_args()
    run(args.llm, args.model)
