"""
Benchmark harness: runs the same bilingual query set through the agent while
you swap OLLAMA_MODEL / EMBEDDING_MODEL in .env between runs, and writes a CSV
of results to experiments/results/ for your paper's comparison tables.

Usage:
    1. set OLLAMA_MODEL=llama3.1:8b in .env, run:  python -m app.evaluation.benchmark
    2. set OLLAMA_MODEL=mistral:7b in .env, run again
    3. repeat for each model / embedding you want to compare
    4. combine the CSVs in experiments/results/ for your accuracy/latency tables
"""
import csv
from pathlib import Path
from datetime import datetime

from app.agent.graph import agent_graph
from app.config import settings
from app.database.database import init_db
from app.evaluation.datasets import TEST_QUERIES
from app.evaluation.metrics import keyword_match, time_call

RESULTS_DIR = Path(__file__).resolve().parents[2] / "experiments" / "results"


def run_benchmark():
    init_db()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name_for_report = getattr(settings, "huggingface_model", None) or settings.ollama_model
    out_path = RESULTS_DIR / f"benchmark_{str(model_name_for_report).replace(':', '-')}_{timestamp}.csv"

    rows = []
    for i, case in enumerate(TEST_QUERIES):
        config = {"configurable": {"thread_id": f"eval-{i}"}}

        def _invoke():
            return agent_graph.invoke(
                {"user_id": f"eval-{i}", "user_message": case["query"]}, config=config
            )

        result, elapsed = time_call(_invoke)
        response = result.get("response", "")
        hit = keyword_match(response, case["expected_contains"])

        rows.append({
            "model": model_name_for_report,
            "embedding_model": settings.embedding_model,
            "lang": case["lang"],
            "query": case["query"],
            "response": response,
            "latency_seconds": round(elapsed, 3),
            "keyword_hit": hit,
        })
        print(f"[{i+1}/{len(TEST_QUERIES)}] {case['lang']} | hit={hit} | {elapsed:.2f}s | {case['query']}")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    accuracy = sum(r["keyword_hit"] for r in rows) / len(rows)
    avg_latency = sum(r["latency_seconds"] for r in rows) / len(rows)
    print(f"\nSaved results to {out_path}")
    print(f"Keyword-match accuracy: {accuracy:.1%} | Avg latency: {avg_latency:.2f}s")


if __name__ == "__main__":
    run_benchmark()
