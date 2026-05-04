"""Tests for combat resolution sub-phase."""
from __future__ import annotations

import pytest

from hexwar.core.actions import (
    DeclareAttackAction, EndPhaseAction, ResolveBattleAction,
)
from hexwar.core.events import BattleResolved
from hexwar.core.hex import HexCoord
from hexwar.systems.test_system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal, assert_action_legal, do_actions,
    make_engine, make_unit,
)


def _setup_combat_phase(units, seed=42):
    """Create engine and advance to combat_a phase."""
    engine = make_engine(units=units, seed=seed)
    do_actions(engine, EndPhaseAction(player=PLAYER_A))  # end move_a → combat_a
    return engine


class TestResolutionTransition:
    """Tests for declaration → resolution sub-phase transition."""

    def test_end_phase_transitions_to_resolution(self):
        """EndPhaseAction during declaration with battles → resolution sub-phase."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        # Declare attack
        do_actions(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        assert engine.state.metadata["combat_sub_phase"] == "declaration"

        # End declaration → resolution
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        assert engine.state.metadata["combat_sub_phase"] == "resolution"

    def test_no_battles_skips_resolution(self):
        """EndPhaseAction with no battles → advances to next phase entirely."""
        engine = _setup_combat_phase([
            make_unit("a1", q=0, r=0),
            make_unit("b1", q=5, r=5, player=PLAYER_B),
        ])
        # No battles, declaration is already complete
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # end combat_a
        # Should be in move_b now
        assert engine.state.active_player == PLAYER_B

    def test_cannot_end_phase_during_resolution_with_unresolved(self):
        """EndPhaseAction illegal when battles remain unresolved."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),  # → resolution
        )
        assert_action_illegal(engine, EndPhaseAction(player=PLAYER_A))


class TestResolveBattle:
    """Tests for resolving individual battles."""

    def test_resolve_single_battle(self):
        """ResolveBattleAction resolves a battle and emits BattleResolved."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),  # → resolution
        )
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        resolved_events = [e for e in events if isinstance(e, BattleResolved)]
        assert len(resolved_events) == 1
        ev = resolved_events[0]
        assert ev.battle_id == 1
        assert ev.result == "tie"
        assert ev.attacker_ids == ("a1",)
        assert ev.defender_ids == ("b1",)
        assert len(ev.dice_roll) == 2
        assert 1 <= ev.dice_roll[0] <= 6
        assert 1 <= ev.dice_roll[1] <= 6
        assert ev.dice_total == ev.dice_roll[0] + ev.dice_roll[1]

    def test_resolve_shows_strengths(self):
        """BattleResolved event includes attack and defense strengths."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1, strength=5),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),
        )
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        ev = [e for e in events if isinstance(e, BattleResolved)][0]
        assert ev.attack_strength == 5
        assert ev.defense_strength == 3

    def test_result_always_tie(self):
        """For now, all battles result in tie regardless of ratio."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1, strength=10),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),
        )
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        ev = [e for e in events if isinstance(e, BattleResolved)][0]
        assert ev.result == "tie"

    def test_cannot_resolve_already_resolved(self):
        """Resolving the same battle twice is illegal."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),
            ResolveBattleAction(player=PLAYER_A, battle_id=1),
        )
        assert_action_illegal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))


class TestMultipleBattleResolution:
    """Tests for resolving multiple battles sequentially."""

    def test_player_chooses_order(self):
        """Player can resolve battles in any order."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("a2", q=1, r=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
            make_unit("b2", q=2, r=3, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a2",),
                                defender_hexes=(HexCoord(2, 3),)),
            EndPhaseAction(player=PLAYER_A),
        )
        # Both battles should be legal to resolve
        assert_action_legal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        assert_action_legal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=2))

        # Resolve battle 2 first
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=2)
        )
        ev = [e for e in events if isinstance(e, BattleResolved)][0]
        assert ev.battle_id == 2

        # Battle 1 still available, battle 2 gone
        assert_action_legal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        assert_action_illegal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=2))

    def test_end_phase_after_all_resolved(self):
        """EndPhaseAction becomes legal after all battles are resolved."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("a2", q=1, r=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
            make_unit("b2", q=2, r=3, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a2",),
                                defender_hexes=(HexCoord(2, 3),)),
            EndPhaseAction(player=PLAYER_A),
        )
        # Cannot end before resolving
        assert_action_illegal(engine, EndPhaseAction(player=PLAYER_A))

        do_actions(engine,
            ResolveBattleAction(player=PLAYER_A, battle_id=1),
            ResolveBattleAction(player=PLAYER_A, battle_id=2),
        )
        # Now can end
        assert_action_legal(engine, EndPhaseAction(player=PLAYER_A))

    def test_phase_advances_after_resolution_end(self):
        """After resolving all battles and ending phase, moves to next phase."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),
            ResolveBattleAction(player=PLAYER_A, battle_id=1),
            EndPhaseAction(player=PLAYER_A),  # end combat_a → move_b
        )
        assert engine.state.active_player == PLAYER_B

    def test_multi_unit_battle_resolution(self):
        """Multi-attacker battle resolves correctly with combined strength."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1, strength=4),
            make_unit("a2", q=1, r=2, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=5),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1", "a2"),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),
        )
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        ev = [e for e in events if isinstance(e, BattleResolved)][0]
        assert ev.attack_strength == 7  # 4 + 3
        assert ev.defense_strength == 5
        assert ev.result == "tie"


class TestResolutionMetadata:
    """Tests for metadata cleanup after resolution."""

    def test_metadata_cleaned_after_phase(self):
        """Combat metadata removed when phase ends after resolution."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),
            ResolveBattleAction(player=PLAYER_A, battle_id=1),
            EndPhaseAction(player=PLAYER_A),  # end combat_a
        )
        # Combat metadata should be cleaned up
        assert "combat_sub_phase" not in engine.state.metadata
        assert "battles" not in engine.state.metadata

    def test_units_survive_tie(self):
        """Units are not destroyed on tie result."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        do_actions(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",),
                                defender_hexes=(HexCoord(2, 1),)),
            EndPhaseAction(player=PLAYER_A),
            ResolveBattleAction(player=PLAYER_A, battle_id=1),
            EndPhaseAction(player=PLAYER_A),
        )
        # Both units should still exist
        assert engine.state.get_unit("a1") is not None
        assert engine.state.get_unit("b1") is not None
