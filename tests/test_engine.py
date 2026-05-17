"""Functional tests for core engine: phase cycling, turn advancement, undo, basic movement + combat."""

import pytest

from hexwar.core.actions import (
    DeclareAttackAction, EndPhaseAction, MoveAction, UndeclareAttackAction,
)
from hexwar.core.events import (
    AttackDeclared, AttackUndeclared, PhaseChanged, TurnChanged, UnitMoved,
)
from hexwar.core.hex import HexCoord
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B

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
            EndPhaseAction(player=PLAYER_A),  # combat_a → strategic_move_a
            EndPhaseAction(player=PLAYER_A),  # strategic_move_a → move_b
            EndPhaseAction(player=PLAYER_B),  # move_b → combat_b
            EndPhaseAction(player=PLAYER_B),  # combat_b → strategic_move_b
            EndPhaseAction(player=PLAYER_B),  # strategic_move_b → move_a (turn 2)
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
    def test_declare_attack_strong_attacker(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # skip to combat_a
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        events = engine.submit_action(declare)
        assert any(isinstance(e, AttackDeclared) for e in events)
        declared_event = next(e for e in events if isinstance(e, AttackDeclared))
        assert declared_event.attacker_ids == ("a1",)
        assert declared_event.defender_ids == ("b1",)
        assert declared_event.attack_ratio == "5:3"

    def test_declare_attack_weak_attacker(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=2),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=5),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        events = engine.submit_action(declare)
        declared_event = next(e for e in events if isinstance(e, AttackDeclared))
        assert declared_event.attack_ratio == "2:5"

    def test_declare_attack_equal_strength(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        events = engine.submit_action(declare)
        declared_event = next(e for e in events if isinstance(e, AttackDeclared))
        assert declared_event.attack_ratio == "3:3"

    def test_cannot_attack_non_adjacent(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(4, 4),),
        )
        assert_action_illegal(engine, declare)


class TestUndo:
    def test_undo_restores_unit_position(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        engine.submit_action(MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)))
        assert_unit_at(engine, "u1", 2, 1)
        engine.undo()
        assert_unit_at(engine, "u1", 1, 1)

    def test_undo_restores_declared_battle(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        engine.submit_action(declare)
        assert engine.state.metadata.get("battles")
        engine.undo()
        assert not engine.state.metadata.get("battles")

    def test_undo_empty_history_returns_none(self):
        engine = make_engine(units=[make_unit("u1", player=PLAYER_A, q=1, r=1)])
        result = engine.undo()
        assert result is None

    def test_undo_restores_rng_state(self):
        """Regression: undo must restore RNG so re-resolution is deterministic.

        Without RNG restore, replaying after undo consumes next RNG state,
        diverging from original behavior.
        """
        from hexwar.core.actions import ResolveBattleAction
        from hexwar.core.events import BattleResolved
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ], seed=42)
        # Set up a battle and resolve it
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # → combat_a
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        do_actions(engine, declare)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # → resolution
        events1 = engine.submit_action(ResolveBattleAction(player=PLAYER_A, battle_id=1))
        roll1 = next(e for e in events1 if isinstance(e, BattleResolved)).dice_total

        # Undo resolution, re-resolve — must give SAME dice roll
        engine.undo()
        events2 = engine.submit_action(ResolveBattleAction(player=PLAYER_A, battle_id=1))
        roll2 = next(e for e in events2 if isinstance(e, BattleResolved)).dice_total
        assert roll1 == roll2, (
            f"Undo+replay should produce same RNG outcome; "
            f"got {roll1} then {roll2}"
        )


class TestInitialPhaseSetup:
    """Engine must run on_phase_enter for the initial phase at construction.

    Regression: without this, units start with movement_left=0 (never reset),
    appearing exhausted with no legal moves at game start.
    """

    def test_active_player_units_have_full_mp_at_game_start(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, movement=2),
            make_unit("a2", player=PLAYER_A, q=2, r=2, movement=3),
            make_unit("b1", player=PLAYER_B, q=5, r=5, movement=2),
        ])
        a1 = engine.state.get_unit("a1")
        a2 = engine.state.get_unit("a2")
        assert a1.movement_left == a1.movement_max == 2
        assert a2.movement_left == a2.movement_max == 3

    def test_initial_phase_active_player_has_legal_moves(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, movement=2),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        legal = engine.get_legal_actions()
        moves = [a for a in legal if isinstance(a, MoveAction)]
        assert len(moves) > 0, "Active player at game start must have legal move actions"
