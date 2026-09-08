"""Topological load-order resolution from a foreign-key graph (bonus)."""

from __future__ import annotations

from collections import defaultdict, deque


def topological_load_order(fk_graph: dict[str, list[str]], tables: list[str]) -> list[str]:
    """Return parent-before-child order. `fk_graph[child] = [parent, ...]`."""
    incoming: dict[str, int] = {t: 0 for t in tables}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for child, parents in fk_graph.items():
        if child not in incoming:
            incoming[child] = 0
        for parent in parents:
            if parent not in incoming:
                incoming[parent] = 0
            outgoing[parent].append(child)
            incoming[child] += 1
    queue = deque(sorted(t for t, deg in incoming.items() if deg == 0))
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for child in outgoing[node]:
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    remaining = [t for t in incoming if t not in ordered]
    return ordered + remaining
