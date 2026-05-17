"""Tests for strategic movement tagging (rule 11.12).

Tag declaration in movement phase. SM phase movement itself = future work.
"""
from __future__ import annotations

import pytest

from hexwar.core.actions import (
    DeclareStrategicMovementAction, EndPhaseAction, MoveAction,
)
from hexwar.core.events import SMTagToggled
from hexwar.core.hex import HexCoord
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal, assert_action_legal, do_actions,
    make_engine, make_unit,
)


class TestSMTagDeclaration:
    """DeclareStrategicMovementAction toggles unit.strategic_movement."""

    def test_eligible_unit_can_be_tagged(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        action = DeclareStrategicMovementAction(player=PLAYER_A, unit_id="a1")
        assert_action_legal(engine, action)
        events = do_actions(engine, action)
        assert engine.state.get_unit("a1").strategic_movement is True
        sm_events = [e for e in events if isinstance(e, SMTagToggled)]
        assert sm_events and sm_events[0].tagged is True

    def test_tag_is_toggle_untag_works(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        assert engine.state.get_unit("a1").strategic_movement is True
        # Toggle again — should untag
        events = do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        assert engine.state.get_unit("a1").strategic_movement is False
        sm_events = [e for e in events if isinstance(e, SMTagToggled)]
        assert sm_events and sm_events[0].tagged is False

    def test_moved_unit_cannot_be_tagged(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        do_actions(engine, MoveAction(
            player=PLAYER_A, unit_id="a1", target=HexCoord(2, 1),
        ))
        # After moving, a1 has movement_left < movement_max → ineligible
        assert_action_illegal(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))

    def test_entrenched_unit_cannot_be_tagged(self):
        """Entrench sets movement_left=0, so movement_left < movement_max."""
        from hexwar.core.actions import EntrenchAction
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="a1"))
        assert_action_illegal(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))

    def test_unit_in_enemy_zoc_cannot_be_tagged(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=2, r=1),  # adjacent → projects ZOC on (1,1)
        ])
        assert_action_illegal(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))

    def test_tag_not_legal_outside_movement_phase(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        # End move_a → combat_a
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        assert engine.current_phase.id == "combat_a"
        assert_action_illegal(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))

    def test_tag_stored_on_unit_not_metadata(self):
        """Regression: SM tag must live on Unit, not state.metadata."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        assert engine.state.get_unit("a1").strategic_movement is True
        # Must NOT pollute metadata
        assert "strategic_movement" not in engine.state.metadata

    def test_tag_zeroes_mp_locking_unit_out_of_normal_move(self):
        """Tagging commits unit: MP zeroed so it cannot move normally this phase.

        Unit then moves only in SM phase with movement_max - 2 budget.
        """
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=3),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        a1 = engine.state.get_unit("a1")
        assert a1.movement_left == 0
        assert a1.movement_max == 3
        assert a1.strategic_movement is True


class TestSMPhaseMovement:
    """StrategicMoveAction in strategic_move_a/b phase (rule 11.2)."""

    def _advance_to_sm_phase(self, engine):
        """Tag a1 then advance to strategic_move_a."""
        from tests.conftest import advance_to_phase
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        advance_to_phase(engine, "strategic_move_a")

    def test_tagged_unit_can_move_in_sm_phase(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=4),
            make_unit("b1", player=PLAYER_B, q=8, r=8),
        ])
        self._advance_to_sm_phase(engine)
        assert engine.current_phase.id == "strategic_move_a"
        from hexwar.core.actions import StrategicMoveAction
        legal = engine.get_legal_actions()
        sm_moves = [a for a in legal if isinstance(a, StrategicMoveAction)]
        assert sm_moves, "Tagged unit should have legal SM moves"

    def test_untagged_unit_cannot_move_in_sm_phase(self):
        """Only tagged units act in SM phase."""
        from tests.conftest import advance_to_phase
        from hexwar.core.actions import StrategicMoveAction
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=4),
            make_unit("a2", q=2, r=2, movement=4),
            make_unit("b1", player=PLAYER_B, q=8, r=8),
        ])
        # Tag only a1
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        advance_to_phase(engine, "strategic_move_a")
        legal = engine.get_legal_actions()
        sm_moves = [a for a in legal if isinstance(a, StrategicMoveAction)]
        unit_ids = {a.unit_id for a in sm_moves}
        assert "a1" in unit_ids
        assert "a2" not in unit_ids

    def test_sm_uses_movement_max_minus_2(self):
        """Rule 11.21: SM MP = max(0, movement_max - 2)."""
        from tests.conftest import advance_to_phase
        from hexwar.core.actions import StrategicMoveAction
        # movement=4 → SM budget 2 → reachable hexes at distance ≤ 2
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=4),
            make_unit("b1", player=PLAYER_B, q=8, r=8),
        ])
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        advance_to_phase(engine, "strategic_move_a")
        legal = engine.get_legal_actions()
        sm_moves = [a for a in legal if isinstance(a, StrategicMoveAction)]
        # No target reachable beyond 2 hexes from (1,1) with full plain terrain
        for action in sm_moves:
            dist = action.target.distance(HexCoord(1, 1))
            assert dist <= 2, f"SM move beyond MP-2 budget: dist={dist}"

    def test_sm_cannot_enter_zoc(self):
        """Rule 11.22: SM cannot enter enemy ZOC."""
        from tests.conftest import advance_to_phase
        from hexwar.core.actions import StrategicMoveAction
        # Tag a1; enemy b1 projects ZOC on hex (3,1)
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=4),
            make_unit("b1", player=PLAYER_B, q=4, r=1),  # projects ZOC on (3,1)
        ])
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        advance_to_phase(engine, "strategic_move_a")
        legal = engine.get_legal_actions()
        sm_moves = [a for a in legal if isinstance(a, StrategicMoveAction)]
        targets = {a.target for a in sm_moves}
        assert HexCoord(3, 1) not in targets, "SM must not allow entry into ZOC"

    def test_sm_move_executes_and_clears_tag(self):
        from tests.conftest import advance_to_phase
        from hexwar.core.actions import StrategicMoveAction
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=4),
            make_unit("b1", player=PLAYER_B, q=8, r=8),
        ])
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        advance_to_phase(engine, "strategic_move_a")
        legal = engine.get_legal_actions()
        sm_moves = [a for a in legal if isinstance(a, StrategicMoveAction)]
        # Pick a target 2 hexes away
        target_action = next(a for a in sm_moves if a.target.distance(HexCoord(1, 1)) == 2)
        do_actions(engine, target_action)
        moved = engine.state.get_unit("a1")
        assert moved.position == target_action.target
        # Tag consumed
        assert moved.strategic_movement is False

    def test_sm_tag_cleared_on_phase_exit(self):
        """Unused SM tags clear when strategic phase ends (rule: tag is per-turn)."""
        from tests.conftest import advance_to_phase
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=4),
            make_unit("b1", player=PLAYER_B, q=8, r=8),
        ])
        do_actions(engine, DeclareStrategicMovementAction(
            player=PLAYER_A, unit_id="a1",
        ))
        # Skip SM phase without using tag
        advance_to_phase(engine, "move_b")
        a1 = engine.state.get_unit("a1")
        assert a1.strategic_movement is False, "Unused SM tag should clear at phase exit"

    def test_sm_phase_only_offers_end_when_no_tagged_units(self):
        from tests.conftest import advance_to_phase
        from hexwar.core.actions import StrategicMoveAction
        # No SM tags set
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=8, r=8),
        ])
        advance_to_phase(engine, "strategic_move_a")
        legal = engine.get_legal_actions()
        sm_moves = [a for a in legal if isinstance(a, StrategicMoveAction)]
        assert sm_moves == [], "No tagged units → no SM moves"
        ends = [a for a in legal if isinstance(a, EndPhaseAction)]
        assert ends, "EndPhaseAction must be available to exit SM phase"
