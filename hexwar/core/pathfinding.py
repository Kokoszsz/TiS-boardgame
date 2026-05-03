from __future__ import annotations

import heapq
from typing import Callable

from hexwar.core.hex import HexCoord


CostFn = Callable[[HexCoord, HexCoord], float | None]
BlockedFn = Callable[[HexCoord], bool]


def reachable_hexes(
    start: HexCoord,
    movement_points: int,
    cost_fn: CostFn,
    blocked_fn: BlockedFn | None = None,
    allow_first_step_overrun: bool = True,
) -> dict[HexCoord, float]:
    """BFS/Dijkstra from start. Returns dict of reachable hex → remaining MP.

    cost_fn(from, to) returns movement cost or None if impassable.
    blocked_fn(coord) returns True if hex is completely blocked.
    allow_first_step_overrun: if True, unit can always move one hex even if cost > MP.
    """
    if blocked_fn is None:
        blocked_fn = lambda c: False

    frontier: list[tuple[float, HexCoord]] = [(0, start)]
    visited: dict[HexCoord, float] = {start: float(movement_points)}

    while frontier:
        spent, current = heapq.heappop(frontier)

        remaining = movement_points - spent
        if remaining < visited.get(current, -1):
            continue

        for nb in current.neighbors():
            if blocked_fn(nb):
                continue
            cost = cost_fn(current, nb)
            if cost is None:
                continue
            if cost == float('inf'):
                if remaining <= 0:
                    continue
                new_spent = float(movement_points)
                new_remaining = 0.0
            else:
                new_spent = spent + cost
                new_remaining = movement_points - new_spent
            if new_remaining < 0:
                if allow_first_step_overrun and spent == 0:
                    new_remaining = 0
                else:
                    continue
            if new_remaining > visited.get(nb, -1):
                visited[nb] = new_remaining
                heapq.heappush(frontier, (new_spent, nb))

    del visited[start]
    return visited


def shortest_path(
    start: HexCoord,
    end: HexCoord,
    cost_fn: CostFn,
    blocked_fn: BlockedFn | None = None,
) -> list[HexCoord] | None:
    """Dijkstra shortest path. Returns path including start and end, or None if unreachable."""
    if blocked_fn is None:
        blocked_fn = lambda c: False

    frontier: list[tuple[float, HexCoord]] = [(0, start)]
    came_from: dict[HexCoord, HexCoord | None] = {start: None}
    cost_so_far: dict[HexCoord, float] = {start: 0}

    while frontier:
        current_cost, current = heapq.heappop(frontier)

        if current == end:
            path = []
            node: HexCoord | None = end
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        if current_cost > cost_so_far.get(current, float("inf")):
            continue

        for nb in current.neighbors():
            if blocked_fn(nb):
                continue
            cost = cost_fn(current, nb)
            if cost is None:
                continue
            new_cost = current_cost + cost
            if new_cost < cost_so_far.get(nb, float("inf")):
                cost_so_far[nb] = new_cost
                came_from[nb] = current
                heapq.heappush(frontier, (new_cost, nb))

    return None
