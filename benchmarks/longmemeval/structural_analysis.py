"""Structural Analysis Gate: Dependency graph + flow analysis."""

import os
import re
from collections import defaultdict

base = "src/claude_memory"
files = [
    f.replace(".py", "")
    for f in os.listdir(base)
    if f.endswith(".py") and f not in {"__init__.py", "__pycache__"}
]

# Build imports + imported_by maps
imports_from = {}
imported_by = defaultdict(set)

for f in files:
    path = os.path.join(base, f + ".py")
    content = open(path, encoding="utf-8").read()
    deps = set()
    for m in re.finditer(r"from (?:claude_memory|\.)\.?(\w+) import", content):
        dep = m.group(1)
        if dep in files:
            deps.add(dep)
    imports_from[f] = sorted(deps)
    for dep in deps:
        imported_by[dep].add(f)

print("=" * 80)
print("STRUCTURAL ANALYSIS GATE — Dependency Graph (Imported By)")
print("=" * 80)
for m in sorted(files):
    by = sorted(imported_by.get(m, set()))
    line_count = sum(1 for _ in open(os.path.join(base, m + ".py"), encoding="utf-8"))
    flag = " [OVER]" if line_count > 300 else ""
    by_str = ", ".join(by) if by else "** ORPHAN **"
    print(f"  {m:30s} ({line_count:>4d} lines){flag}  <- {by_str}")

print("\n" + "=" * 80)
print("MODULES OVER 300 LINES (must split before adding code)")
print("=" * 80)
for f in files:
    path = os.path.join(base, f + ".py")
    lines = sum(1 for _ in open(path, encoding="utf-8"))
    if lines > 300:
        print(f"  {f + '.py':30s} {lines:>4d} lines")

# Check for circular deps
print("\n" + "=" * 80)
print("CIRCULAR DEPENDENCY CHECK")
print("=" * 80)
# Simple cycle detection via DFS
visited = set()
rec_stack = set()
cycles = []


def find_cycles(node, path):
    visited.add(node)
    rec_stack.add(node)
    for dep in imports_from.get(node, []):
        if dep not in visited:
            find_cycles(dep, [*path, dep])
        elif dep in rec_stack:
            cycle = [*path[path.index(dep) :], dep] if dep in path else [node, dep]
            cycles.append(" → ".join(cycle))
    rec_stack.discard(node)


for f in files:
    if f not in visited:
        find_cycles(f, [f])

if cycles:
    for c in cycles:
        print(f"  CYCLE: {c}")
else:
    print("  [OK] No circular dependencies found")

# Find orphans (not imported by anything and not importing anything)
print("\n" + "=" * 80)
print("ORPHAN CHECK")
print("=" * 80)
for m in sorted(files):
    if not imported_by.get(m) and not imports_from.get(m):
        print(f"  ORPHAN: {m}.py")
    elif not imported_by.get(m):
        print(f"  NOT IMPORTED BY ANYONE: {m}.py (but imports: {', '.join(imports_from[m])})")
