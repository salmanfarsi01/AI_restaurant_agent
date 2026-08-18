"""Benchmark harness for local Ollama model comparison and seaborn charts.

This is a practical, project-level evaluation suite for the current local RAG bot.
It reports:
- accuracy %: answer contains the expected fact(s)
- latency: end-to-end response time
- factual correctness: percentage of answers grounded in the expected facts
- hallucination rate: percentage of answers that do not match the expected facts

This is intentionally a lightweight benchmark for local model comparison, not a
full-blown RAGAS or human-judged evaluation suite.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from app.agent.graph import agent_graph
from app.config import MODEL_REGISTRY, settings
from app.database.database import init_db
from app.evaluation.datasets import TEST_QUERIES
from app.evaluation.metrics import keyword_match, time_call

RESULTS_DIR = Path(__file__).resolve().parents[2] / "experiments" / "results"


def _model_display_name(model_key_or_name: str) -> str:
    if model_key_or_name in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_key_or_name]["label"]
    return model_key_or_name


def _resolve_ollama_name(model_key_or_name: str) -> str:
    if model_key_or_name in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_key_or_name]["ollama_model"]
    return model_key_or_name


def evaluate_model(model_key_or_name: str, queries=None) -> pd.DataFrame:
    raw_queries = queries or TEST_QUERIES
    queries = [q for q in raw_queries if q.get("lang") == "en"]
    model_display = _model_display_name(model_key_or_name)
    model_name_for_run = _resolve_ollama_name(model_key_or_name)
    previous_model = settings.ollama_model
    previous_backend = settings.llm_backend
    settings.llm_backend = "ollama"
    settings.ollama_model = model_name_for_run

    try:
        rows = []
        for i, case in enumerate(queries):
            config = {"configurable": {"thread_id": f"eval-{model_name_for_run}-{i}"}}

            def _invoke(case=case, config=config):
                return agent_graph.invoke(
                    {"user_id": f"eval-{model_name_for_run}-{i}", "user_message": case["query"]},
                    config=config,
                )

            result, elapsed = time_call(_invoke)
            response = result.get("response", "")
            expected = case["expected_contains"]
            hit = keyword_match(response, expected)

            # Factual correctness is treated as grounded faithfulness to the
            # expected fact(s) for the current benchmark dataset.
            factual_correct = 1 if hit else 0
            hallucination = 0 if hit else 1

            rows.append({
                "model_key": model_key_or_name,
                "model_name": model_display,
                "ollama_model": model_name_for_run,
                "lang": case["lang"],
                "query": case["query"],
                "response": response,
                "latency_seconds": round(elapsed, 3),
                "keyword_hit": int(hit),
                "factual_correctness": factual_correct,
                "hallucination": hallucination,
                "expected_contains": "; ".join(expected),
            })
            print(f"[{model_display}] {i + 1}/{len(queries)} | hit={hit} | {elapsed:.2f}s | {case['query']}")

        return pd.DataFrame(rows)
    finally:
        settings.llm_backend = previous_backend
        settings.ollama_model = previous_model


def save_model_csv(df: pd.DataFrame, out_path: Path) -> None:
    df.to_csv(out_path, index=False)


def plot_model_comparison(summary_df: pd.DataFrame, out_dir: Path) -> None:
    sns.set_theme(style="whitegrid")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.barplot(data=summary_df, x="model_name", y="accuracy_pct", hue="model_name", dodge=False, palette="viridis", legend=False, ax=axes[0])
    axes[0].set_title("Accuracy by model (%)")
    axes[0].set_xlabel("Model")
    axes[0].set_ylabel("Accuracy (%)")
    axes[0].tick_params(axis="x", rotation=20)

    sns.barplot(data=summary_df, x="model_name", y="avg_latency_seconds", hue="model_name", dodge=False, palette="magma", legend=False, ax=axes[1])
    axes[1].set_title("Average latency by model")
    axes[1].set_xlabel("Model")
    axes[1].set_ylabel("Seconds")
    axes[1].tick_params(axis="x", rotation=20)

    fig.tight_layout()
    fig.savefig(out_dir / "model_performance_comparison.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def run_benchmark(model_keys: list[str] | None = None) -> pd.DataFrame:
    init_db()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if model_keys is None:
        model_keys = list(MODEL_REGISTRY.keys())

    all_rows = []
    summary_rows = []

    for key in model_keys:
        df = evaluate_model(key)
        all_rows.append(df)

        correct_count = int(df["keyword_hit"].sum())
        total_queries = int(len(df))
        accuracy_pct = (correct_count / total_queries * 100.0) if total_queries else 0.0
        factual_correctness_pct = (df["factual_correctness"].mean() * 100.0) if total_queries else 0.0
        hallucination_rate_pct = (df["hallucination"].mean() * 100.0) if total_queries else 0.0

        summary = {
            "model_name": df["model_name"].iloc[0],
            "ollama_model": df["ollama_model"].iloc[0],
            "correct_answers": correct_count,
            "total_questions": total_queries,
            "accuracy_pct": accuracy_pct,
            "factual_correctness_pct": factual_correctness_pct,
            "hallucination_rate_pct": hallucination_rate_pct,
            "avg_latency_seconds": float(df["latency_seconds"].mean()),
        }
        summary_rows.append(summary)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = RESULTS_DIR / f"benchmark_{key}_{timestamp}.csv"
        save_model_csv(df, csv_path)
        print(f"\nSaved per-model CSV to {csv_path}")
        print(
            f"Accuracy: {accuracy_pct:.2f}% ({correct_count}/{total_queries}) | "
            f"Factual correctness: {factual_correctness_pct:.2f}% | "
            f"Hallucination rate: {hallucination_rate_pct:.2f}% | "
            f"Avg latency: {summary['avg_latency_seconds']:.2f}s"
        )

    combined_df = pd.concat(all_rows, ignore_index=True)
    combined_csv = RESULTS_DIR / "model_comparison_all_runs.csv"
    save_model_csv(combined_df, combined_csv)

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(["accuracy_pct", "avg_latency_seconds"], ascending=[False, True]).reset_index(drop=True)
    summary_df["accuracy_pct"] = summary_df["accuracy_pct"].astype(float)
    summary_df["factual_correctness_pct"] = summary_df["factual_correctness_pct"].astype(float)
    summary_df["hallucination_rate_pct"] = summary_df["hallucination_rate_pct"].astype(float)
    summary_df["avg_latency_seconds"] = summary_df["avg_latency_seconds"].astype(float)

    summary_csv = RESULTS_DIR / "model_comparison_summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    table_csv = RESULTS_DIR / "comparison_table.csv"
    summary_df.to_csv(table_csv, index=False)

    plot_model_comparison(summary_df, RESULTS_DIR)
    print(f"Saved combined results to {combined_csv}")
    print(f"Saved summary to {summary_csv}")
    print(f"Saved cleaner comparison table to {table_csv}")
    print(f"Saved graph to {RESULTS_DIR / 'model_performance_comparison.png'}")

    return summary_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the installed local Ollama models and generate seaborn comparison charts.")
    parser.add_argument(
        "--models",
        nargs="*",
        default=list(MODEL_REGISTRY.keys()),
        help="Model keys to benchmark. Examples: qwen2.5-0.5b qwen2.5-1.5b qwen3-0.6b qwen3-1.7b",
    )
    args = parser.parse_args()
    run_benchmark(args.models)


if __name__ == "__main__":
    main()
