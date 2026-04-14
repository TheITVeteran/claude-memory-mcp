"""Step 0: Metric verification analysis for LongMemEval benchmark.

Answers:
1. Which metric variant does LongMemEval officially use?
2. What do OUR metrics actually compute (recall_any vs recall_all)?
3. Evidence session count distribution
4. MemPalace's metric comparison
"""

import json
from collections import Counter, defaultdict

# Load dataset
data = json.load(open("benchmarks/longmemeval/data/longmemeval_oracle.json"))

# Load our results
results = json.load(open("benchmarks/longmemeval/results/results_oracle.json"))

print("=" * 80)
print("STEP 0: METRIC VERIFICATION ANALYSIS")
print("=" * 80)

# 1. Evidence session count distribution
print("\n## 1. Evidence Session Count Distribution")
print("-" * 60)
evidence_counts = []
for q in data:
    n = len(q.get("answer_session_ids", []))
    evidence_counts.append(n)

dist = Counter(evidence_counts)
for count in sorted(dist.keys()):
    pct = dist[count] / len(data) * 100
    bar = "#" * int(pct)
    print(f"  {count} evidence session(s): {dist[count]:>4d} questions ({pct:.1f}%) {bar}")

print(f"\n  Total questions: {len(data)}")
print(f"  Questions with >5 evidence sessions: {sum(1 for c in evidence_counts if c > 5)}")
print(f"  Questions with >10 evidence sessions: {sum(1 for c in evidence_counts if c > 10)}")

# 2. Our metric definition analysis
print("\n## 2. Our Metric Definition")
print("-" * 60)
print("  Our recall_at_k computes: len(top_k & relevant) / len(relevant)")
print("  This is RECALL_ALL (fraction of ALL relevant items found)")
print("  NOT recall_any (binary: is ANY relevant item in top-k)")
print()

# 3. Compute both variants on our results
print("## 3. Both Metric Variants on Our Results")
print("-" * 60)

recall_any_5 = []
recall_all_5 = []
recall_any_10 = []
recall_all_10 = []

for q in results["per_question"]:
    retrieved = q["retrieved_ids"]
    expected = q["expected_uuids"]

    if not expected:
        continue

    # recall_all: fraction found
    top5 = set(retrieved[:5])
    top10 = set(retrieved[:10])
    relevant = set(expected)

    r_all_5 = len(top5 & relevant) / len(relevant)
    r_all_10 = len(top10 & relevant) / len(relevant)

    # recall_any: binary
    r_any_5 = 1.0 if len(top5 & relevant) > 0 else 0.0
    r_any_10 = 1.0 if len(top10 & relevant) > 0 else 0.0

    recall_all_5.append(r_all_5)
    recall_all_10.append(r_all_10)
    recall_any_5.append(r_any_5)
    recall_any_10.append(r_any_10)

print(f"  recall_all@5  (our metric): {sum(recall_all_5) / len(recall_all_5):.1%}")
print(f"  recall_any@5  (binary):     {sum(recall_any_5) / len(recall_any_5):.1%}")
print(f"  recall_all@10 (our metric): {sum(recall_all_10) / len(recall_all_10):.1%}")
print(f"  recall_any@10 (binary):     {sum(recall_any_10) / len(recall_any_10):.1%}")

# 4. Per-type breakdown with both variants
print("\n## 4. Per-Type: recall_all vs recall_any")
print("-" * 60)

by_type = defaultdict(lambda: {"all5": [], "any5": [], "all10": [], "any10": []})

for q in results["per_question"]:
    retrieved = q["retrieved_ids"]
    expected = q["expected_uuids"]
    t = q["question_type"]
    if not expected:
        continue
    top5 = set(retrieved[:5])
    top10 = set(retrieved[:10])
    relevant = set(expected)
    by_type[t]["all5"].append(len(top5 & relevant) / len(relevant))
    by_type[t]["any5"].append(1.0 if (top5 & relevant) else 0.0)
    by_type[t]["all10"].append(len(top10 & relevant) / len(relevant))
    by_type[t]["any10"].append(1.0 if (top10 & relevant) else 0.0)

print(f"  {'Type':30s} {'R_all@5':>8s} {'R_any@5':>8s} {'R_all@10':>9s} {'R_any@10':>9s}")
print(f"  {'-' * 30} {'-' * 8} {'-' * 8} {'-' * 9} {'-' * 9}")
for t in sorted(by_type.keys()):
    v = by_type[t]
    a5 = sum(v["all5"]) / len(v["all5"])
    n5 = sum(v["any5"]) / len(v["any5"])
    a10 = sum(v["all10"]) / len(v["all10"])
    n10 = sum(v["any10"]) / len(v["any10"])
    print(f"  {t:30s} {a5:>7.1%} {n5:>7.1%} {a10:>8.1%} {n10:>8.1%}")

print("\n## 5. Key Finding")
print("-" * 60)
print("  LongMemEval official code does NOT compute recall@K.")
print("  It computes QA accuracy via LLM-as-judge (GPT-4o).")
print("  MemPalace defines their own 'recall@5' which is recall_any@5.")
print("  Our metric is recall_all@5 (stricter: ALL evidence must be found).")
print("  This means our 61.3% is NOT directly comparable to MemPalace's 96.6%.")
print()
