"""
Simple, dependency-light metrics for comparing LLM/embedding/vector-DB configs.
Extend with a proper RAG-eval framework (e.g. RAGAS) once the pipeline is stable.
"""
import time
from dataclasses import dataclass, field


@dataclass
class RunResult:
    query: str
    lang: str
    response: str
    latency_seconds: float
    keyword_hit: bool
    retrieved_sources: list[str] = field(default_factory=list)


def keyword_match(response: str, expected_contains: list[str]) -> bool:
    return any(kw.lower() in response.lower() for kw in expected_contains)


def time_call(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed
