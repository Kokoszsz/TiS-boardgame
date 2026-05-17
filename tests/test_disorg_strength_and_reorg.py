"""Tests for disorganization strength penalty (14.2) and reorganization (14.2).

Rule 14.2:
  - Disorganized unit fights at 1/2 PS, rounded up.
  - D removed automatically if unit doesn't move or fight for one full turn.
    Token removed at end of movement phase when conditions met.
  - Entrenching does NOT count as activity — unit can still reorganize.
"""
from __future__ import annotations

import math

from hexwar.core.actions import (
    DeclareAttackAction, EndPhaseAction, EntrenchAction,
    MoveAction, ResolveBattleAction, ResolveDisorgRollsAction,
    StrategicMoveAction,
)
from hexwar.core.battle import PostBattlePhase
from hexwar.core.events import BattleResolved, UnitReorganized
from hexwar.core.hex import HexCoord
from hexwar.core.rng import GameRNG
from hexwar.core.state import build_initial_state
from hexwar.systems.wb48.combat_declaration import CombatSubPhase
from hexwar.systems.wb48.combat_resolution import ResolutionMixin
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B, WB48System

from tests.conftest import advance_to_phase, do_actions, make_engine, make_map, make_unit


class SequenceRNG(GameRNG):
    """RNG returning a fixed sequence of dice values."""

    def __init__(self, dice_sequence: list[int]):
        super().__init__(seed=0)
        self._queue = list(dice_sequence)

    def roll_d6(self) -> int:
        return self._queue.pop(0)

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        return [self._queue.pop(0) for _ in range(count)]


def _engine_with_rng(units, rng: GameRNG):
    state = build_initial_state(
        scenario_id="test", scenario_name="Test", system_id="test",
        hex_map=make_map(), units=units, active_player=PLAYER_A,
    )
    from hexwar.core.engine import Engine
    return Engine(state, WB48System(), rng)


# ---------------------------------------------------------------------------
# Strength halving (rule 14.2)
# ---------------------------------------------------------------------------


class TestEffectiveStrength:

    def test_disorganized_unit_half_strength_rounded_up(self):
        """Disorganized unit with strength 5 → effective 3 (ceil(5/2))."""
        unit = make_unit("a1", strength=5)
        unit = unit.with_disorganized(True)
        assert ResolutionMixin._effective_strength(unit) == math.ceil(5 / 2)

    def test_disorganized_even_strength_halves_exactly(self):
        """Disorganized unit with strength 6 → effective 3."""
        unit = make_unit("a1", strength=6)
        unit = unit.with_disorganized(True)
        assert ResolutionMixin._effective_strength(unit) == 3

    def test_non_disorganized_full_strength(self):
        unit = make_unit("a1", strength=5)
        assert ResolutionMixin._effective_strength(unit) == 5

    def test_disorganized_strength_1_stays_1(self):
        """Minimum strength: ceil(1/2) = 1."""
        unit = make_unit("a1", strength=1)
        unit = unit.with_disorganized(True)
        assert ResolutionMixin._effective_strength(unit) == 1


class TestCombatUsesEffectiveStrength:

    def test_disorganized_attacker_reduced_in_battle(self):
        """Disorganized attacker uses halved strength in CRT lookup."""
        units = [
            make_unit("a1", q=1, r=0, strength=6),
            make_unit("b1", player=PLAYER_B, q=2, r=0, strength=3),
        ]
        rng = SequenceRNG([3, 4])
        engine = _engine_with_rng(units, rng)

        a1 = engine.state.get_unit("a1")
        engine._state = engine.state.with_unit(
            a1.with_disorganized(True).with_last_active_turn(engine.state.turn)
        )

        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # move_a → combat_a

        do_actions(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 0),),
        ))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # declaration → resolution

        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        resolved = [e for e in events if isinstance(e, BattleResolved)]
        assert len(resolved) == 1
        # Disorganized a1: strength 6 → effective 3. Defender b1: strength 3.
        assert resolved[0].attack_strength == 3
        assert resolved[0].defense_strength == 3

    def test_disorganized_defender_reduced_in_battle(self):
        """Disorganized defender uses halved strength in CRT lookup."""
        units = [
            make_unit("a1", q=1, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=0, strength=6),
        ]
        rng = SequenceRNG([3, 4])
        engine = _engine_with_rng(units, rng)

        b1 = engine.state.get_unit("b1")
        engine._state = engine.state.with_unit(
            b1.with_disorganized(True).with_last_active_turn(engine.state.turn)
        )

        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # move_a → combat_a

        do_actions(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 0),),
        ))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # declaration → resolution

        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        resolved = [e for e in events if isinstance(e, BattleResolved)]
        assert resolved[0].attack_strength == 3
        assert resolved[0].defense_strength == 3  # 6 halved → 3

    def test_both_sides_disorganized(self):
        """Both attacker and defender disorganized — both halved."""
        units = [
            make_unit("a1", q=1, r=0, strength=6),
            make_unit("b1", player=PLAYER_B, q=2, r=0, strength=4),
        ]
        rng = SequenceRNG([3, 4])
        engine = _engine_with_rng(units, rng)

        a1 = engine.state.get_unit("a1")
        b1 = engine.state.get_unit("b1")
        turn = engine.state.turn
        engine._state = engine.state.with_unit(
            a1.with_disorganized(True).with_last_active_turn(turn)
        )
        engine._state = engine.state.with_unit(
            b1.with_disorganized(True).with_last_active_turn(turn)
        )

        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 0),),
        ))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))

        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        resolved = [e for e in events if isinstance(e, BattleResolved)]
        assert resolved[0].attack_strength == 3   # ceil(6/2)
        assert resolved[0].defense_strength == 2   # ceil(4/2)


# ---------------------------------------------------------------------------
# Reorganization (rule 14.2)
# ---------------------------------------------------------------------------


class TestReorganization:

    def test_idle_disorganized_unit_reorganizes_next_turn(self):
        """Unit disorganized in turn 1, idle in turn 2 → reorganized at end of move phase."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        # Mark a1 disorganized with last_active_turn=1 (current turn)
        a1 = engine.state.get_unit("a1")
        engine._state = engine.state.with_unit(
            a1.with_disorganized(True).with_last_active_turn(1)
        )
        assert engine.state.get_unit("a1").disorganized

        # Advance through all 6 phases to reach turn 2, move_a
        advance_to_phase(engine, "move_a")

        # Now in turn 2 move_a. Don't move a1 — just end phase.
        events = engine.submit_action(EndPhaseAction(player=PLAYER_A))

        # Should have reorganized
        assert not engine.state.get_unit("a1").disorganized
        reorg_events = [e for e in events if isinstance(e, UnitReorganized)]
        assert len(reorg_events) == 1
        assert reorg_events[0].unit_id == "a1"

    def test_unit_that_moved_does_not_reorganize(self):
        """Unit moves during movement phase → last_active_turn updated → no reorganization."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        a1 = engine.state.get_unit("a1")
        engine._state = engine.state.with_unit(
            a1.with_disorganized(True).with_last_active_turn(1)
        )

        advance_to_phase(engine, "move_a")

        # Move a1 during turn 2 movement
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(1, 0)))

        # End movement phase
        events = engine.submit_action(EndPhaseAction(player=PLAYER_A))

        # Should still be disorganized — moved this turn
        assert engine.state.get_unit("a1").disorganized
        assert not any(isinstance(e, UnitReorganized) for e in events)

    def test_entrenching_does_not_prevent_reorganization(self):
        """Rule 14.2: entrenching is allowed — unit can still reorganize."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        a1 = engine.state.get_unit("a1")
        engine._state = engine.state.with_unit(
            a1.with_disorganized(True).with_last_active_turn(1)
        )

        advance_to_phase(engine, "move_a")

        # Entrench — should NOT set last_active_turn
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="a1"))

        # End movement phase
        events = engine.submit_action(EndPhaseAction(player=PLAYER_A))

        # Should reorganize — entrenching doesn't count as activity
        assert not engine.state.get_unit("a1").disorganized
        assert any(isinstance(e, UnitReorganized) for e in events)

    def test_non_disorganized_unit_unaffected(self):
        """Reorganization check skips non-disorganized units."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])

        advance_to_phase(engine, "move_a")

        events = engine.submit_action(EndPhaseAction(player=PLAYER_A))

        assert not any(isinstance(e, UnitReorganized) for e in events)

    def test_disorganized_same_turn_does_not_reorganize(self):
        """Unit disorganized this turn → last_active_turn == current_turn → no reorg."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        # Disorganized this turn (turn 1)
        a1 = engine.state.get_unit("a1")
        engine._state = engine.state.with_unit(
            a1.with_disorganized(True).with_last_active_turn(1)
        )

        # End move_a (still turn 1)
        events = engine.submit_action(EndPhaseAction(player=PLAYER_A))

        # Should NOT reorganize — disorganized this same turn
        assert engine.state.get_unit("a1").disorganized
        assert not any(isinstance(e, UnitReorganized) for e in events)

    def test_player_b_unit_reorganizes_at_move_b_exit(self):
        """Player B's disorganized unit checks at end of move_b, not move_a."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        b1 = engine.state.get_unit("b1")
        engine._state = engine.state.with_unit(
            b1.with_disorganized(True).with_last_active_turn(1)
        )

        # Advance past turn 1's move_b (arrives at move_b in turn 1, phase_index=3)
        advance_to_phase(engine, "move_b")
        # Now advance to turn 2's move_b (wraps around full cycle)
        advance_to_phase(engine, "move_b")

        assert engine.state.turn == 2
        assert engine.state.get_unit("b1").disorganized

        events = engine.submit_action(EndPhaseAction(player=PLAYER_B))

        assert not engine.state.get_unit("b1").disorganized
        reorg = [e for e in events if isinstance(e, UnitReorganized)]
        assert len(reorg) == 1
        assert reorg[0].unit_id == "b1"


class TestActivityTracking:

    def test_movement_sets_last_active_turn(self):
        """Moving a unit updates last_active_turn to current turn."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        assert engine.state.get_unit("a1").last_active_turn == 0

        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="a1", target=HexCoord(1, 0)))
        assert engine.state.get_unit("a1").last_active_turn == 1

    def test_combat_sets_last_active_turn_for_both_sides(self):
        """Combat marks both attacker and defender as active."""
        units = [
            make_unit("a1", q=1, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=0, strength=3),
        ]
        rng = SequenceRNG([3, 4])
        engine = _engine_with_rng(units, rng)

        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # move_a → combat_a
        do_actions(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 0),),
        ))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # declaration → resolution
        engine.submit_action(ResolveBattleAction(player=PLAYER_A, battle_id=1))

        assert engine.state.get_unit("a1").last_active_turn == 1
        assert engine.state.get_unit("b1").last_active_turn == 1

    def test_entrench_does_not_set_last_active_turn(self):
        """Entrenching is not counted as activity for reorganization purposes."""
        engine = make_engine(units=[
            make_unit("a1", q=0, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=4, r=4, strength=3),
        ])
        assert engine.state.get_unit("a1").last_active_turn == 0

        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="a1"))
        assert engine.state.get_unit("a1").last_active_turn == 0
