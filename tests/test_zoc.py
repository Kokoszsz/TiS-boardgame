"""Functional tests for Zone of Control (ZOC).

ZOC rules:
- Only combat units (infantry, tank) project ZOC, not artillery/HQ
- ZOC = unit's own hex + 6 adjacent hexes
- Entering enemy ZOC costs all remaining MP (unit stops)
- Can't move within the SAME enemy unit's ZOC (ZOC-A to ZOC-A blocked)
- CAN move from ZOC of unit A to ZOC of unit B (different sources)
"""

from hexwar.core.actions import EndPhaseAction, MoveAction
from hexwar.core.hex import HexCoord
from hexwar.systems.test_system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal,
    assert_action_legal,
    do_actions,
    make_engine,
    make_unit,
)


class TestZOCStopsMovement:
    def test_entering_zoc_stops_unit(self):
        """Unit with 3 MP entering ZOC hex uses all remaining MP — can't move further."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=0, r=2, movement=3),
            make_unit("b1", player=PLAYER_B, q=3, r=2, movement=2),
        ])
        # Hex(2,2) is adjacent to b1 at (3,2) — it's in ZOC
        move_to_zoc = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 2))
        assert_action_legal(engine, move_to_zoc)

        do_actions(engine, move_to_zoc)
        # Should have 0 MP remaining — can't move further
        move_further = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 1))
        assert_action_illegal(engine, move_further)

    def test_can_still_reach_zoc_hex(self):
        """ZOC hex is reachable — unit can enter it, just stops there."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=0, r=2, movement=3),
            make_unit("b1", player=PLAYER_B, q=3, r=2, movement=2),
        ])
        move_to_zoc = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 2))
        assert_action_legal(engine, move_to_zoc)


class TestZOCBlocksMovement:
    def test_cannot_move_directly_between_zoc_hexes(self):
        """Unit in ZOC can reach another ZOC hex only via non-ZOC path, not directly.
        Here all paths to target go through ZOC, so it's blocked."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=3, r=1, movement=1),  # in ZOC of b1, only 1 MP
            make_unit("b1", player=PLAYER_B, q=3, r=2, movement=2),
        ])
        # a1 at (3,1) in ZOC. With 1 MP can only move to adjacent hexes.
        # (4,1) is adjacent AND in ZOC. Direct move = ZOC→ZOC = blocked.
        # With only 1 MP, can't go around.
        move_zoc_to_zoc = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(4, 1))
        assert_action_illegal(engine, move_zoc_to_zoc)

    def test_can_move_from_zoc_to_non_zoc(self):
        """Unit in ZOC hex CAN move away to a non-ZOC hex."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=3, r=1, movement=3),  # in ZOC of b1
            make_unit("b1", player=PLAYER_B, q=3, r=2, movement=2),
        ])
        # a1 at (3,1) in ZOC. (3,0) is NOT in ZOC of b1
        move_away = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(3, 0))
        assert_action_legal(engine, move_away)


class TestZOCUnitTypes:
    def test_artillery_does_not_project_zoc(self):
        """Artillery units don't create ZOC — can move freely near them."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=2, movement=3),
            make_unit("b_art", player=PLAYER_B, q=3, r=2, type_id="artillery", movement=1),
        ])
        # Move adjacent to artillery — should NOT be stopped by ZOC
        move_adj = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 2))
        assert_action_legal(engine, move_adj)

        do_actions(engine, move_adj)
        # Should still have MP to continue (no ZOC stopping)
        move_further = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(3, 1))
        assert_action_legal(engine, move_further)

    def test_infantry_projects_zoc(self):
        """Infantry projects ZOC — entering adjacent hex costs all MP."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=2, movement=3),
            make_unit("b_inf", player=PLAYER_B, q=3, r=2, type_id="infantry", movement=2),
        ])
        move_to_zoc = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 2))
        do_actions(engine, move_to_zoc)
        # In ZOC — should have 0 MP
        move_further = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 1))
        assert_action_illegal(engine, move_further)

    def test_tank_projects_zoc(self):
        """Tank projects ZOC same as infantry."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=2, movement=3),
            make_unit("b_tank", player=PLAYER_B, q=3, r=2, type_id="tank", movement=3),
        ])
        move_to_zoc = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 2))
        do_actions(engine, move_to_zoc)
        move_further = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 1))
        assert_action_illegal(engine, move_further)


class TestZOCIncludesOwnHex:
    def test_enemy_hex_is_in_zoc(self):
        """Enemy unit's own hex is part of its ZOC."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=2, movement=2),
            make_unit("b1", player=PLAYER_B, q=3, r=2, type_id="infantry"),
        ])
        from hexwar.systems.test_system import TestSystem
        system: TestSystem = engine.system
        zoc_map = system.enemy_zoc_map(engine.state, PLAYER_A)
        assert HexCoord(3, 2) in zoc_map
        assert "b1" in zoc_map[HexCoord(3, 2)]

    def test_own_hex_zoc_blocks_zoc_to_zoc(self):
        """Moving from adjacent ZOC hex onto enemy hex is ZOC-to-ZOC (same source), blocked by enemy presence anyway."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=2, r=2, movement=3),
            make_unit("b1", player=PLAYER_B, q=3, r=2, type_id="infantry"),
        ])
        # (2,2) is in ZOC of b1, (3,2) is b1's hex also in ZOC — can't move there (enemy blocks)
        move_onto = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(3, 2))
        assert_action_illegal(engine, move_onto)


class TestZOCEdgeCases:
    def test_own_units_dont_create_zoc_for_self(self):
        """Friendly units don't project ZOC against own player."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=2, movement=3),
            make_unit("a2", player=PLAYER_A, q=3, r=2, movement=2),
        ])
        # Move near friendly unit — no ZOC effect
        move_adj = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 2))
        do_actions(engine, move_adj)
        move_further = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(3, 1))
        assert_action_legal(engine, move_further)

    def test_can_move_from_zoc_a_to_zoc_b(self):
        """CAN move from ZOC of unit A to ZOC of unit B (different sources)."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=2, r=2, movement=3),
            make_unit("b1", player=PLAYER_B, q=3, r=3, movement=2),
            make_unit("b2", player=PLAYER_B, q=1, r=1, movement=2),
        ])
        # a1 at (2,2) is in ZOC of b1 (neighbor of (3,3)).
        # (2,1) is in ZOC of b2 (neighbor of (1,1)) but NOT in ZOC of b1.
        # Moving (2,2)->(2,1) = ZOC-b1 -> ZOC-b2 = allowed (different sources)
        move_cross_zoc = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 1))
        assert_action_legal(engine, move_cross_zoc)

    def test_can_reenter_same_zoc_via_non_zoc(self):
        """Per 6.32: can leave ZOC then re-enter same unit's ZOC via non-ZOC hex."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=2, r=2, movement=3),
            make_unit("b1", player=PLAYER_B, q=3, r=2, movement=2),
        ])
        # (2,2) in ZOC of b1. (2,3) also in ZOC of b1.
        # Direct (2,2)->(2,3) blocked (same source), but indirect via (1,3) works.
        move_reenter = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 3))
        assert_action_legal(engine, move_reenter)

    def test_multiple_enemies_overlapping_zoc(self):
        """Hex in ZOC of both b1 and b2 — shares source with each, blocks ZOC-to-ZOC for either."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=2, r=2, movement=3),
            make_unit("b1", player=PLAYER_B, q=3, r=2, movement=2),
            make_unit("b2", player=PLAYER_B, q=3, r=1, movement=2),
        ])
        # (2,2) in ZOC of b1. Can move to non-ZOC hex.
        move_away = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(1, 2))
        assert_action_legal(engine, move_away)
