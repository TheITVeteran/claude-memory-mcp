"""Quick smoke test for FTS store."""

from claude_memory.fts_store import FTSStore

fts = FTSStore(db_path=":memory:")
fts.index_entity("e1", "Python Programming", "Concept", "A high-level language")
fts.index_entity("e2", "Java Spring", "Framework", "Enterprise Java framework")
fts.index_entity("e3", "Python Flask", "Framework", "Lightweight Python web framework")

results = fts.search("Python")
print(f"Query: 'Python' => {len(results)} results")
for r in results:
    print(f"  {r['name']} (score={r['bm25_score']:.3f})")

results2 = fts.search("enterprise Java")
print(f"Query: 'enterprise Java' => {len(results2)} results")
for r in results2:
    print(f"  {r['name']} (score={r['bm25_score']:.3f})")

# Test edge cases
assert fts.search("") == [], "Empty query should return empty"
assert fts.search("   ") == [], "Whitespace query should return empty"
assert fts.search("zzzznotfound") == [], "No-match query should return empty"

# Test update (re-index)
fts.index_entity("e1", "Python Programming", "Concept", "Updated description about Python")
results3 = fts.search("Updated description")
assert len(results3) == 1, f"Expected 1 result after update, got {len(results3)}"

# Test remove
fts.remove_entity("e1")
results4 = fts.search("Python")
assert len(results4) == 1, f"Expected 1 after remove (Flask only), got {len(results4)}"
assert results4[0]["name"] == "Python Flask"

print(f"Total indexed: {fts.count()}")
fts.close()
print("FTS store: ALL TESTS PASSED")
