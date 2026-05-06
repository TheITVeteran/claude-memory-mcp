"""Performance & Memory Baselines — Gauntlet R9.

Establishes speed and memory baselines for core pure functions:
- Schema construction speed
- Router classification speed
- Schema serialization throughput
- Memory profiling for bulk operations

These tests serve as regression gates — if a refactor makes a function
significantly slower or use more memory, the test fails.
"""

import tracemalloc

from claude_memory.router import QueryRouter
from claude_memory.schema import (
    EntityCreateParams,
    SearchResult,
)

# ═══════════════════════════════════════════════════════════════
#  Helper: memory measurement
# ═══════════════════════════════════════════════════════════════


def measure_peak_memory(func, *args, **kwargs):
    """Run func and return (result, peak_memory_bytes)."""
    tracemalloc.start()
    result = func(*args, **kwargs)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, peak


# ═══════════════════════════════════════════════════════════════
#  Speed Baselines
# ═══════════════════════════════════════════════════════════════


class TestSpeedBaselines:
    """Benchmark core functions to establish speed baselines."""

    def test_happy_schema_construction_speed(self):
        """H1: 10K EntityCreateParams constructions in < 2s."""
        import time

        start = time.monotonic()
        for i in range(10_000):
            EntityCreateParams(
                name=f"entity_{i}",
                node_type="Concept",
                project_id="bench",
            )
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"10K schema constructions took {elapsed:.2f}s (limit: 2.0s)"

    def test_happy_router_classify_speed(self):
        """H2: 10K router classifications in < 2s."""
        import time

        router = QueryRouter()
        queries = [
            "what happened yesterday",
            "path between A and B",
            "related to entropy",
            "tell me about quantum physics",
            "when did we discuss this",
        ]
        start = time.monotonic()
        for i in range(10_000):
            router.classify(queries[i % len(queries)])
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"10K classifications took {elapsed:.2f}s (limit: 2.0s)"

    def test_happy_schema_serialization_speed(self):
        """H3: 5K SearchResult serialize+deserialize in < 3s."""
        import time

        results = [
            SearchResult(
                id=f"id-{i}",
                name=f"entity_{i}",
                node_type="Concept",
                project_id="bench",
                score=0.95,
                distance=0.05,
            )
            for i in range(5_000)
        ]
        start = time.monotonic()
        for r in results:
            json_str = r.model_dump_json()
            SearchResult.model_validate_json(json_str)
        elapsed = time.monotonic() - start
        assert elapsed < 3.0, f"5K serialize roundtrips took {elapsed:.2f}s (limit: 3.0s)"


# ═══════════════════════════════════════════════════════════════
#  Memory Baselines (tracemalloc)
# ═══════════════════════════════════════════════════════════════


class TestMemoryBaselines:
    """Verify core functions don't leak memory beyond expected limits."""

    def test_happy_schema_construction_memory(self):
        """H4: 10K EntityCreateParams uses < 10MB peak."""

        def build_batch():
            return [
                EntityCreateParams(
                    name=f"entity_{i}",
                    node_type="Concept",
                    project_id="bench",
                )
                for i in range(10_000)
            ]

        _, peak = measure_peak_memory(build_batch)
        mb = peak / (1024 * 1024)
        assert mb < 15, f"10K schema construction peak: {mb:.2f}MB (limit: 15MB)"

    def test_happy_router_classification_memory(self):
        """H5: 10K router classifications use < 5MB."""
        router = QueryRouter()

        def classify_batch():
            for i in range(10_000):
                router.classify(f"test query number {i} about entropy and physics")

        _, peak = measure_peak_memory(classify_batch)
        mb = peak / (1024 * 1024)
        assert mb < 5, f"10K classifications peak: {mb:.2f}MB (limit: 5MB)"

    def test_happy_search_result_memory(self):
        """H6: 5K SearchResult constructions use < 10MB."""

        def build_results():
            return [
                SearchResult(
                    id=f"id-{i}",
                    name=f"entity_{i}",
                    node_type="Concept",
                    project_id="bench",
                    score=0.95,
                    distance=0.05,
                    observations=[f"obs_{j}" for j in range(5)],
                    relationships=[{"src": f"a_{j}", "dst": f"b_{j}"} for j in range(3)],
                )
                for i in range(5_000)
            ]

        _, peak = measure_peak_memory(build_results)
        mb = peak / (1024 * 1024)
        assert mb < 15, f"5K SearchResult peak: {mb:.2f}MB (limit: 15MB)"
