"""Functional tests for point-based stacking limits.

Stacking uses stack_size stat per unit (default 1). Hex limit = 6 points.
WB-48: infantry/cavalry full = 2, weakened = 1, artillery/HQ = 1.
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


class TestStackingLimits:
    def test_can_move_to_empty_hex(self):
        engine = make_engine(units=[make_unit("u1", q=1, r=1, stack_size=2)])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, move)

    def test_can_stack_within_limit(self):
        """Two units with stack_size=2 = 4 points, under limit of 6."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1, stack_size=2),
            make_unit("u2", q=2, r=1, stack_size=2),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, move)

    def test_three_full_infantry_at_limit(self):
        """3 units × stack_size=2 = 6 points, exactly at limit."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1, stack_size=2),
            make_unit("u2", q=2, r=1, stack_size=2),
            make_unit("u3", q=2, r=1, stack_size=2),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, move)

    def test_exceed_limit_blocked(self):
        """4 units × stack_size=2 = 8 points, over limit of 6."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1, stack_size=2),
            make_unit("u2", q=2, r=1, stack_size=2),
            make_unit("u3", q=2, r=1, stack_size=2),
            make_unit("u4", q=2, r=1, stack_size=2),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_illegal(engine, move)

    def test_small_unit_fits_where_big_doesnt(self):
        """Hex has 5 points used. stack_size=1 fits, stack_size=2 doesn't."""
        engine = make_engine(units=[
            make_unit("big", q=1, r=1, stack_size=2),
            make_unit("small", q=1, r=2, stack_size=1),
            make_unit("u2", q=2, r=1, stack_size=2),
            make_unit("u3", q=2, r=1, stack_size=2),
            make_unit("u4", q=2, r=1, stack_size=1),
        ])
        # Hex (2,1) has 5 points. big (2) would make 7 > 6
        move_big = MoveAction(player=PLAYER_A, unit_id="big", target=HexCoord(2, 1))
        assert_action_illegal(engine, move_big)
        # small (1) would make 6 = limit, OK
        move_small = MoveAction(player=PLAYER_A, unit_id="small", target=HexCoord(2, 1))
        assert_action_legal(engine, move_small)

    def test_six_small_units_at_limit(self):
        """6 units × stack_size=1 = 6, at limit."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1, stack_size=1),
            make_unit("u2", q=2, r=1, stack_size=1),
            make_unit("u3", q=2, r=1, stack_size=1),
            make_unit("u4", q=2, r=1, stack_size=1),
            make_unit("u5", q=2, r=1, stack_size=1),
            make_unit("u6", q=2, r=1, stack_size=1),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, move)

    def test_seven_small_units_over_limit(self):
        """7 units × stack_size=1 = 7, over limit."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1, stack_size=1),
            make_unit("u2", q=2, r=1, stack_size=1),
            make_unit("u3", q=2, r=1, stack_size=1),
            make_unit("u4", q=2, r=1, stack_size=1),
            make_unit("u5", q=2, r=1, stack_size=1),
            make_unit("u6", q=2, r=1, stack_size=1),
            make_unit("u7", q=2, r=1, stack_size=1),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_illegal(engine, move)

    def test_cannot_move_to_hex_with_enemy(self):
        """Can't move to hex occupied by enemy unit."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 1))
        assert_action_illegal(engine, move)

    def test_stacking_counts_only_friendly(self):
        """Stack limit only counts friendly units, enemy blocks hex entirely."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, stack_size=1),
            make_unit("a2", player=PLAYER_A, q=2, r=1, stack_size=1),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(2, 1))
        assert_action_legal(engine, move)

    def test_moving_out_frees_space(self):
        """Moving unit out frees stacking points."""
        engine = make_engine(units=[
            make_unit("u1", q=2, r=1, stack_size=2),
            make_unit("u2", q=2, r=1, stack_size=2),
            make_unit("u3", q=2, r=1, stack_size=2),
            make_unit("u4", q=1, r=1, stack_size=2),
        ])
        # Hex (2,1) at 6 points. Move u1 out → 4 points. u4 (2) can enter.
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1)))
        move = MoveAction(player=PLAYER_A, unit_id="u4", target=HexCoord(2, 1))
        assert_action_legal(engine, move)

    def test_default_stack_size_is_1(self):
        """Units without explicit stack_size default to 1."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1),  # no stack_size in stats
            make_unit("u2", q=2, r=1),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, move)

    def test_stacking_does_not_block_pathfinding(self):
        """Full hex blocks destination but not pathing through."""
        engine = make_engine(units=[
            make_unit("u1", q=0, r=1, stack_size=1),
            make_unit("u2", q=1, r=1, stack_size=2),
            make_unit("u3", q=1, r=1, stack_size=2),
            make_unit("u4", q=1, r=1, stack_size=2),
        ])
        beyond = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, beyond)
