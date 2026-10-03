"""Evaluation: rule engine vs LLM models (results table for the report).

Usage:
    cd communication_node/llm_module
    python3 evaluate.py                                   # rules only
    python3 evaluate.py --models llama3.2:3b qwen2.5:3b   # rules + LLMs

Metrics per engine:
    accuracy                 decisions matching the expected risk + action
    swarm-context accuracy   same, only on scenarios with earlier reports
    LLM used                 % answered by the LLM (rest = fallback: unreachable/invalid)
    safety overrides         % of LLM answers corrected by the safety layer
    latency                  mean / max LLM response time
Results are saved in results/ as JSON and Markdown.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from llm_decision import LLMDecisionMaker, default_llm_client
from scenarios import SCENARIOS

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def run_engine(name, client):
    rows = []
    for sc in SCENARIOS:
        maker = LLMDecisionMaker(drone_id="eval", use_llm=client is not None, llm_client=client)
        for earlier in sc.get("context", []):
            maker._remember(maker._normalize_message(earlier))
        d = maker.interpret(sc["message"])
        rows.append({
            "scenario": sc["name"],
            "has_context": bool(sc.get("context")),
            "risk_level": d["risk_level"], "action": d["action"],
            "correct": d["risk_level"] in sc["expect"]["risk"] and d["action"] in sc["expect"]["actions"],
            "source": d["decision_source"],
            "overrides": d.get("safety_overrides", []),
            "fallback_reason": d.get("fallback_reason"),
            "latency_ms": d.get("llm_latency_ms"),
        })
    ctx = [r for r in rows if r["has_context"]]
    s = {"engine": name, "scenarios": len(rows),
         "accuracy": sum(r["correct"] for r in rows) / len(rows),
         "context_accuracy": sum(r["correct"] for r in ctx) / len(ctx) if ctx else None}
    if client is not None:
        llm_rows = [r for r in rows if r["source"].startswith("llm")]
        lat = [r["latency_ms"] for r in llm_rows if r["latency_ms"] is not None]
        s.update({
            "llm_used": len(llm_rows) / len(rows),
            "safety_override_rate": (sum(bool(r["overrides"]) for r in llm_rows) / len(llm_rows)) if llm_rows else None,
            "latency_mean_ms": round(statistics.mean(lat), 1) if lat else None,
            "latency_max_ms": max(lat) if lat else None,
        })
    return {"summary": s, "rows": rows}


def pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"


def to_markdown(results):
    out = ["| Engine | Accuracy | Swarm-context accuracy | LLM used | Safety overrides | Mean latency | Max latency |",
           "|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["summary"]
        ms = lambda v: "-" if v is None else f"{v:.0f} ms"
        out.append(f"| {s['engine']} | {pct(s['accuracy'])} | {pct(s['context_accuracy'])} | "
                   f"{pct(s.get('llm_used'))} | {pct(s.get('safety_override_rate'))} | "
                   f"{ms(s.get('latency_mean_ms'))} | {ms(s.get('latency_max_ms'))} |")
    out += ["", "### Per scenario", "",
            "| Scenario | " + " | ".join(r["summary"]["engine"] for r in results) + " |",
            "|---|" + "---|" * len(results)]
    for i, sc in enumerate(SCENARIOS):
        cells = [f"{'✓' if r['rows'][i]['correct'] else '✗'} {r['rows'][i]['risk_level']}/{r['rows'][i]['action']}"
                 for r in results]
        out.append(f"| {sc['name']} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=[])
    args = parser.parse_args()

    results = [run_engine("rules", None)]
    for model in args.models:
        client = default_llm_client()
        client.model = model
        if not client.is_available():
            print(f"[skip] {client.name}: Ollama not running or model not pulled (ollama pull {model})")
            continue
        print(f"Evaluating {client.name} ...")
        results.append(run_engine(client.name, client))

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RESULTS_DIR / f"eval_{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    md = to_markdown(results)
    (RESULTS_DIR / f"eval_{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"Saved results/eval_{stamp}.json and .md")


if __name__ == "__main__":
    main()
