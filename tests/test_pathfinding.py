"""Unit tests for pathfinding functions."""
from __future__ import annotations

from hexwar.core.hex import HexCoord
from hexwar.core.pathfinding import reachable_hexes, shortest_path


def _flat_cost(from_hex: HexCoord, to_hex: HexCoord) -> float | None:
    return 1.0


def _bounded_cost(bounds: set[HexCoord]):
    def cost_fn(from_hex: HexCoord, to_hex: HexCoord) -> float | None:
        if to_hex not in bounds:
            return None
        return 1.0
    return cost_fn


class TestShortestPathNone:
    def test_unreachable_returns_none(self):
        all_hexes = {HexCoord(q, r) for q in range(5) for r in range(5)}
        wall = {HexCoord(2, r) for r in range(5)}
        cost_fn = _bounded_cost(all_hexes - wall)
        path = shortest_path(HexCoord(0, 0), HexCoord(4, 0), cost_fn)
        assert path is None

    def test_blocked_target_returns_none(self):
        all_hexes = {HexCoord(q, r) for q in range(5) for r in range(5)}
        cost_fn = _bounded_cost(all_hexes)
        blocked = lambda c: c == HexCoord(3, 0)
        path = shortest_path(HexCoord(0, 0), HexCoord(3, 0), cost_fn, blocked)
        assert path is None

    def test_reachable_returns_path(self):
        all_hexes = {HexCoord(q, r) for q in range(5) for r in range(5)}
        cost_fn = _bounded_cost(all_hexes)
        path = shortest_path(HexCoord(0, 0), HexCoord(2, 0), cost_fn)
        assert path is not None
        assert path[0] == HexCoord(0, 0)
        assert path[-1] == HexCoord(2, 0)


class TestReachableHexesInfCost:
    def test_inf_cost_consumes_all_mp(self):
        def cost_fn(from_hex, to_hex):
            if to_hex == HexCoord(1, 0):
                return float('inf')
            return 1.0
        result = reachable_hexes(HexCoord(0, 0), 4, cost_fn)
        assert HexCoord(1, 0) in result
        assert result[HexCoord(1, 0)] == 0

    def test_inf_cost_no_further_movement(self):
        def cost_fn(from_hex, to_hex):
            if to_hex == HexCoord(1, 0):
                return float('inf')
            return 1.0
        result = reachable_hexes(HexCoord(0, 0), 4, cost_fn)
        for nb in HexCoord(1, 0).neighbors():
            if nb == HexCoord(0, 0):
                continue
            if nb in result:
                assert result[nb] > 0 or nb.distance(HexCoord(0, 0)) == 1

    def test_inf_cost_with_zero_mp_blocked(self):
        def cost_fn(from_hex, to_hex):
            return float('inf')
        result = reachable_hexes(HexCoord(0, 0), 0, cost_fn)
        assert len(result) == 0


class TestFirstStepOverrun:
    def test_overrun_disabled_blocks_expensive_first_step(self):
        def cost_fn(from_hex, to_hex):
            return 3.0
        result = reachable_hexes(
            HexCoord(0, 0), 2, cost_fn,
            allow_first_step_overrun=False,
        )
        assert len(result) == 0

    def test_overrun_enabled_allows_expensive_first_step(self):
        def cost_fn(from_hex, to_hex):
            return 3.0
        result = reachable_hexes(
            HexCoord(0, 0), 2, cost_fn,
            allow_first_step_overrun=True,
        )
        assert len(result) > 0

    def test_overrun_disabled_allows_affordable_step(self):
        def cost_fn(from_hex, to_hex):
            return 2.0
        result = reachable_hexes(
            HexCoord(0, 0), 2, cost_fn,
            allow_first_step_overrun=False,
        )
        assert len(result) > 0

    def test_overrun_only_applies_to_first_step(self):
        def cost_fn(from_hex, to_hex):
            return 3.0
        result = reachable_hexes(
            HexCoord(0, 0), 2, cost_fn,
            allow_first_step_overrun=True,
        )
        assert len(result) == 6, "Should reach exactly 6 adjacent hexes"
        for coord, remaining in result.items():
            assert remaining == 0, "All MP consumed by overrun"
            assert coord.distance(HexCoord(0, 0)) == 1, \
                "Overrun only allows 1 step — no further movement"
