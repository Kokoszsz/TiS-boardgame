"""Functional tests for core engine: phase cycling, turn advancement, undo, basic movement + combat."""

import pytest

from hexwar.core.actions import AttackAction, EndPhaseAction, MoveAction
from hexwar.core.events import CombatResolved, PhaseChanged, TurnChanged, UnitDestroyed, UnitMoved
from hexwar.core.hex import HexCoord
from hexwar.systems.test_system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal,
    assert_action_legal,
    assert_unit_at,
    assert_unit_destroyed,
    assert_unit_exists,
    do_actions,
    make_engine,
    make_unit,
)


class TestPhaseCycling:
    def test_initial_phase_is_player_a_movement(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        assert engine.current_phase.id == "move_a"
        assert engine.state.active_player == PLAYER_A

    def test_end_phase_advances_to_combat(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        assert engine.current_phase.id == "combat_a"

    def test_full_phase_cycle_returns_to_start(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        do_actions(
            engine,
            EndPhaseAction(player=PLAYER_A),  # move_a → combat_a
            EndPhaseAction(player=PLAYER_A),  # combat_a → move_b
            EndPhaseAction(player=PLAYER_B),  # move_b → combat_b
            EndPhaseAction(player=PLAYER_B),  # combat_b → move_a (turn 2)
        )
        assert engine.current_phase.id == "move_a"
        assert engine.state.turn == 2

    def test_wrong_player_action_rejected(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        with pytest.raises(ValueError, match="Not player_b's turn"):
            engine.submit_action(EndPhaseAction(player=PLAYER_B))


class TestMovement:
    def test_move_unit_to_adjacent_hex(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        events = engine.submit_action(move)
        assert_unit_at(engine, "u1", 2, 1)
        assert any(isinstance(e, UnitMoved) for e in events)

    def test_move_within_range(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1, movement=2)])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_legal(engine, move)

    def test_move_outside_range_is_illegal(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1, movement=1)])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_illegal(engine, move)

    def test_move_off_map_is_illegal(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=0, r=0, movement=3)])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(-1, 0))
        assert_action_illegal(engine, move)

    def test_cannot_move_enemy_unit(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=3, r=3),
        ])
        move = MoveAction(player=PLAYER_A, unit_id="b1", target=HexCoord(3, 4))
        assert_action_illegal(engine, move)


class TestCombat:
    def test_stronger_attacker_destroys_defender(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # skip to combat
        attack = AttackAction(player=PLAYER_A, attacker_id="a1", defender_id="b1")
        events = engine.submit_action(attack)
        assert_unit_destroyed(engine, "b1")
        assert_unit_exists(engine, "a1")
        assert any(isinstance(e, CombatResolved) and e.result == "attacker_wins" for e in events)

    def test_stronger_defender_destroys_attacker(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=2),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=5),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        attack = AttackAction(player=PLAYER_A, attacker_id="a1", defender_id="b1")
        events = engine.submit_action(attack)
        assert_unit_destroyed(engine, "a1")
        assert_unit_exists(engine, "b1")

    def test_equal_strength_tie(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        attack = AttackAction(player=PLAYER_A, attacker_id="a1", defender_id="b1")
        events = engine.submit_action(attack)
        assert_unit_exists(engine, "a1")
        assert_unit_exists(engine, "b1")
        assert any(isinstance(e, CombatResolved) and e.result == "tie" for e in events)

    def test_cannot_attack_non_adjacent(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        attack = AttackAction(player=PLAYER_A, attacker_id="a1", defender_id="b1")
        assert_action_illegal(engine, attack)


class TestUndo:
    def test_undo_restores_unit_position(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        engine.submit_action(MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)))
        assert_unit_at(engine, "u1", 2, 1)
        engine.undo()
        assert_unit_at(engine, "u1", 1, 1)

    def test_undo_restores_destroyed_unit(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        engine.submit_action(AttackAction(player=PLAYER_A, attacker_id="a1", defender_id="b1"))
        assert_unit_destroyed(engine, "b1")
        engine.undo()
        assert_unit_exists(engine, "b1")

    def test_undo_empty_history_returns_none(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        result = engine.undo()
        assert result is None
