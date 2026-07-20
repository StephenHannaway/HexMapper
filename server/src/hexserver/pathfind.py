import heapq
from collections.abc import Callable

from hexserver.config import (
    REUSE_DISCOUNT,
    RIVER_COSTS,
    RIVER_DEFAULT,
    ROAD_COSTS,
    ROAD_DEFAULT,
)

NEIGHBOURS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]

Hex = tuple[int, int]


def hex_distance(a: Hex, b: Hex) -> int:
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def build_cost(
    kind: str, terrain_at: dict[Hex, str], occupied: set[Hex]
) -> Callable[[int, int], float]:
    if kind == "road":
        table, default = ROAD_COSTS, ROAD_DEFAULT
    elif kind == "river":
        table, default = RIVER_COSTS, RIVER_DEFAULT
    else:
        raise ValueError(f"unknown feature kind {kind!r}")

    def cost(q: int, r: int) -> float:
        base = table.get(terrain_at.get((q, r), ""), default)
        if (q, r) in occupied:
            return base * REUSE_DISCOUNT
        return base

    return cost


def a_star(
    start: Hex,
    goal: Hex,
    cost: Callable[[int, int], float],
    max_nodes: int = 4000,
) -> list[Hex]:
    if start == goal:
        return [start]
    open_heap: list[tuple[float, int, Hex]] = [(0.0, 0, start)]
    g_score: dict[Hex, float] = {start: 0.0}
    came_from: dict[Hex, Hex] = {}
    counter = 0  # heap tiebreaker
    explored = 0
    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        explored += 1
        if explored > max_nodes:
            break
        for dq, dr in NEIGHBOURS:
            nxt = (current[0] + dq, current[1] + dr)
            tentative = g_score[current] + cost(*nxt)
            if tentative < g_score.get(nxt, float("inf")):
                g_score[nxt] = tentative
                came_from[nxt] = current
                counter += 1
                f = tentative + hex_distance(nxt, goal)
                heapq.heappush(open_heap, (f, counter, nxt))
    raise ValueError("no route found (budget exhausted)")
