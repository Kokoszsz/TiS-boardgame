"""
End-to-end scenario tests exercising full game flow.
Tests complete sequences: setup → move → combat declaration → resolve → post-battle → end.

Flow per phase:
- move_a: MoveAction(s) → EndPhaseAction
- combat_a DECLARATION sub-phase: DeclareAttackAction(s) → EndPhaseAction
- combat_a RESOLUTION sub-phase: ResolveBattleAction → post-battle actions → EndPhaseAction
"""

from __future__ import annotations

import pytest

from hexwar.core.actions import (
    Action,
    AssignCplLossAction,
    ChooseRetreatSplitAction,
    DeclareAttackAction,
    EndPhaseAction,
    MoveAction,
    PursuitAction,
    ResolveBattleAction,
    RetreatUnitAction,
    SkipPursuitAction,
)
from hexwar.core.battle import PostBattlePhase
from hexwar.core.hex import HexCoord
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B
from tests.conftest import (
    advance_to_phase,
    assert_action_legal,
    assert_unit_at,
    assert_unit_destroyed,
    assert_unit_exists,
    do_actions,
    make_engine,
    make_unit,
)


# -- Drivers ----------------------------------------------------------------


def _resolve_all_post_battle(engine, player, max_iter=30):
    """Drive post-battle phases to completion for given player.

    Picks first available action of each type. Returns when only EndPhaseAction
    (or no actions) remain. Raises if loop exceeds max_iter.
    """
    for _ in range(max_iter):
        legal = engine.get_legal_actions()
        non_end = [a for a in legal if not isinstance(a, EndPhaseAction)]
        if not non_end:
            return

        # Resolution priority: resolve unresolved battles first
        resolve = [a for a in legal if isinstance(a, ResolveBattleAction)]
        if resolve:
            do_actions(engine, resolve[0])
            continue

        # Split
        splits = [a for a in legal if isinstance(a, ChooseRetreatSplitAction)]
        if splits:
            do_actions(engine, splits[0])
            continue

        # CPL assignment
        cpls = [a for a in legal if isinstance(a, AssignCplLossAction)]
        if cpls:
            do_actions(engine, cpls[0])
            continue

        # Retreat
        retreats = [a for a in legal if isinstance(a, RetreatUnitAction)]
        if retreats:
            do_actions(engine, retreats[0])
            continue

        # Pursuit
        pursuits = [a for a in legal if isinstance(a, PursuitAction)]
        if pursuits:
            do_actions(engine, pursuits[0])
            continue

        # Skip pursuit
        skips = [a for a in legal if isinstance(a, SkipPursuitAction)]
        if skips:
            do_actions(engine, skips[0])
            continue

        pytest.fail(f"Unhandled legal actions: {legal}")
    pytest.fail(f"Post-battle loop exceeded {max_iter} iterations")


def _advance_to_combat_a(engine):
    """End move_a phase to reach combat_a DECLARATION sub-phase."""
    do_actions(engine, EndPhaseAction(player=PLAYER_A))


def _enter_resolution(engine, player=PLAYER_A):
    """Transition combat phase from DECLARATION to RESOLUTION."""
    do_actions(engine, EndPhaseAction(player=player))


# -- Scenarios --------------------------------------------------------------


class TestE2EAttackerWinsClean:
    """Attacker wins decisively, no friendly casualties, pursuit available."""

    def test_attacker_wins_can_pursuit(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=5),
                make_unit("B1", player=PLAYER_B, q=2, r=0, strength=1),
            ],
            seed=42,
        )

        # Movement phase
        do_actions(engine, MoveAction(PLAYER_A, "A1", HexCoord(1, 0)))
        _advance_to_combat_a(engine)

        # Declaration sub-phase
        do_actions(
            engine,
            DeclareAttackAction(PLAYER_A, ("A1",), (HexCoord(2, 0),)),
        )
        _enter_resolution(engine)

        # Resolution sub-phase: resolve battle
        do_actions(engine, ResolveBattleAction(PLAYER_A, battle_id=1))

        battle = engine.state.metadata["battles"][0]
        assert battle.resolved is True

        # Drive post-battle to completion
        _resolve_all_post_battle(engine, PLAYER_A)

        # All battles done
        for b in engine.state.metadata["battles"]:
            assert b.post_phase == PostBattlePhase.DONE

        # End combat_a phase, advance through strategic_move_a → move_b
        assert_action_legal(engine, EndPhaseAction(player=PLAYER_A))
        advance_to_phase(engine, "move_b")

        # Should now be in move_b
        assert engine.state.active_player == PLAYER_B


class TestE2EDefenderWins:
    """Defender wins. Attacker handles split/retreat/CPL."""

    def test_defender_wins_attacker_post_battle_resolves(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=1),
                make_unit("B1", player=PLAYER_B, q=2, r=0, strength=5),
            ],
            seed=42,
        )

        do_actions(engine, MoveAction(PLAYER_A, "A1", HexCoord(1, 0)))
        _advance_to_combat_a(engine)

        do_actions(
            engine,
            DeclareAttackAction(PLAYER_A, ("A1",), (HexCoord(2, 0),)),
        )
        _enter_resolution(engine)
        do_actions(engine, ResolveBattleAction(PLAYER_A, battle_id=1))

        # Drive whatever post-battle phases the result requires
        _resolve_all_post_battle(engine, PLAYER_A)

        battle = engine.state.metadata["battles"][0]
        assert battle.post_phase == PostBattlePhase.DONE

        # End combat_a → strategic_move_a → move_b
        advance_to_phase(engine, "move_b")
        assert engine.state.active_player == PLAYER_B


class TestE2EMultiUnitDeclaration:
    """Multiple attackers from different hexes attack same defender."""

    def test_multi_unit_declaration_both_attackers_recorded(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=2),
                make_unit("A2", player=PLAYER_A, q=0, r=1, strength=2),
                make_unit("B1", player=PLAYER_B, q=2, r=0, strength=3),
            ],
            seed=42,
        )

        do_actions(
            engine,
            MoveAction(PLAYER_A, "A1", HexCoord(1, 0)),
            MoveAction(PLAYER_A, "A2", HexCoord(1, 1)),
        )
        _advance_to_combat_a(engine)

        do_actions(
            engine,
            DeclareAttackAction(PLAYER_A, ("A1", "A2"), (HexCoord(2, 0),)),
        )

        # Battle recorded with both attackers
        battle = engine.state.metadata["battles"][0]
        assert "A1" in battle.attacker_ids
        assert "A2" in battle.attacker_ids

        _enter_resolution(engine)
        do_actions(engine, ResolveBattleAction(PLAYER_A, battle_id=1))
        _resolve_all_post_battle(engine, PLAYER_A)

        # Phase completes — through strategic to move_b
        advance_to_phase(engine, "move_b")
        assert engine.state.active_player == PLAYER_B


class TestE2EMultiUnitPursuit:
    """If A wins decisively with 2 attackers, both may pursue."""

    def test_two_attackers_pursuit_or_skip(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=3),
                make_unit("A2", player=PLAYER_A, q=0, r=1, strength=3),
                make_unit("B1", player=PLAYER_B, q=2, r=0, strength=1),
            ],
            seed=42,
        )

        do_actions(
            engine,
            MoveAction(PLAYER_A, "A1", HexCoord(1, 0)),
            MoveAction(PLAYER_A, "A2", HexCoord(1, 1)),
        )
        _advance_to_combat_a(engine)

        do_actions(
            engine,
            DeclareAttackAction(PLAYER_A, ("A1", "A2"), (HexCoord(2, 0),)),
        )
        _enter_resolution(engine)
        do_actions(engine, ResolveBattleAction(PLAYER_A, battle_id=1))

        battle = engine.state.metadata["battles"][0]

        # If A won and B was eliminated, expect PURSUIT phase
        if battle.result.victorious_attacker and engine.state.get_unit("B1") is None:
            assert battle.post_phase == PostBattlePhase.PURSUIT
            legal = engine.get_legal_actions()
            pursuit_actions = [a for a in legal if isinstance(a, PursuitAction)]
            skip_actions = [a for a in legal if isinstance(a, SkipPursuitAction)]
            assert pursuit_actions or skip_actions

        _resolve_all_post_battle(engine, PLAYER_A)
        assert engine.state.metadata["battles"][0].post_phase == PostBattlePhase.DONE


class TestE2EFullPhaseSequence:
    """Two simultaneous battles drive through full post-battle pipeline."""

    def test_two_battles_both_resolve_to_done(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=3),
                make_unit("A2", player=PLAYER_A, q=0, r=2, strength=3),
                make_unit("B1", player=PLAYER_B, q=2, r=0, strength=2),
                make_unit("B2", player=PLAYER_B, q=2, r=2, strength=2),
            ],
            seed=42,
        )

        do_actions(
            engine,
            MoveAction(PLAYER_A, "A1", HexCoord(1, 0)),
            MoveAction(PLAYER_A, "A2", HexCoord(1, 2)),
        )
        _advance_to_combat_a(engine)

        do_actions(
            engine,
            DeclareAttackAction(PLAYER_A, ("A1",), (HexCoord(2, 0),)),
            DeclareAttackAction(PLAYER_A, ("A2",), (HexCoord(2, 2),)),
        )
        _enter_resolution(engine)

        # Should have two battles
        battles = engine.state.metadata["battles"]
        assert len(battles) == 2

        # Drive everything to done
        _resolve_all_post_battle(engine, PLAYER_A, max_iter=60)

        for b in engine.state.metadata["battles"]:
            assert b.post_phase == PostBattlePhase.DONE

        # End combat_a → strategic_move_a → move_b
        advance_to_phase(engine, "move_b")
        assert engine.state.active_player == PLAYER_B


class TestE2EBothPlayersTurnCycle:
    """Full turn cycle: A's movement+combat then B's movement+combat."""

    def test_both_players_can_complete_turn_with_combat(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=3),
                make_unit("B1", player=PLAYER_B, q=4, r=0, strength=3),
            ],
            seed=42,
        )

        # --- A's movement
        do_actions(engine, MoveAction(PLAYER_A, "A1", HexCoord(1, 0)))
        # Advance through combat (no contact) + strategic to B's turn
        advance_to_phase(engine, "move_b")

        # --- B's movement
        assert engine.state.active_player == PLAYER_B
        do_actions(engine, MoveAction(PLAYER_B, "B1", HexCoord(3, 0)))
        # Advance through combat + strategic to next turn
        advance_to_phase(engine, "move_a")

        # Cycle back to A
        assert engine.state.active_player == PLAYER_A


class TestE2ENoCombat:
    """Movement phase without contact skips combat entirely."""

    def test_no_combat_when_units_not_adjacent(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0),
                make_unit("B1", player=PLAYER_B, q=5, r=5),
            ],
            seed=42,
        )

        advance_to_phase(engine, "move_b")  # skip A's move/combat/strategic
        assert engine.state.active_player == PLAYER_B


class TestE2EMandatoryDeclaration:
    """Adjacent enemy unit forces declaration before EndPhaseAction allowed."""

    def test_must_declare_when_adjacent_enemy_exists(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=3),
                make_unit("B1", player=PLAYER_B, q=1, r=0, strength=3),
            ],
            seed=42,
        )

        # Skip movement
        do_actions(engine, EndPhaseAction(player=PLAYER_A))

        # In combat_a, must have either declare actions or be allowed to end
        # if no mandatory attack rule (depends on system).
        # Decloration: should have a declare option for A1 → B1
        legal = engine.get_legal_actions()
        declares = [a for a in legal if isinstance(a, DeclareAttackAction)]
        assert declares, "Expected declare action available with adjacent enemy"


class TestE2ECombatChain:
    """Resolve sequence: A attacks, then B counterattacks next turn."""

    def test_a_attacks_then_b_attacks_next_turn(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=4),
                make_unit("B1", player=PLAYER_B, q=2, r=0, strength=4),
            ],
            seed=42,
        )

        # A's turn: attack
        do_actions(engine, MoveAction(PLAYER_A, "A1", HexCoord(1, 0)))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(
            engine,
            DeclareAttackAction(PLAYER_A, ("A1",), (HexCoord(2, 0),)),
        )
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, ResolveBattleAction(PLAYER_A, battle_id=1))
        _resolve_all_post_battle(engine, PLAYER_A)
        advance_to_phase(engine, "move_b")

        # Should be B's turn now
        assert engine.state.active_player == PLAYER_B

        # If both units survived, B may attack
        a_alive = engine.state.get_unit("A1") is not None
        b_alive = engine.state.get_unit("B1") is not None

        if a_alive and b_alive:
            a_pos = engine.state.get_unit("A1").position
            b_pos = engine.state.get_unit("B1").position
            # Check if still adjacent (could have retreated)
            from hexwar.core.hex import hex_distance
            if hex_distance(a_pos, b_pos) == 1:
                # B can declare counterattack
                do_actions(engine, EndPhaseAction(player=PLAYER_B))  # skip move
                legal = engine.get_legal_actions()
                declares = [a for a in legal if isinstance(a, DeclareAttackAction)]
                assert declares, "B should be able to declare counterattack"


class TestE2EBattleMetadataPersistence:
    """Battle objects persist through resolution and post-battle."""

    def test_battle_id_consistent_across_phases(self):
        engine = make_engine(
            units=[
                make_unit("A1", player=PLAYER_A, q=0, r=0, strength=3),
                make_unit("B1", player=PLAYER_B, q=2, r=0, strength=3),
            ],
            seed=42,
        )

        do_actions(engine, MoveAction(PLAYER_A, "A1", HexCoord(1, 0)))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(
            engine,
            DeclareAttackAction(PLAYER_A, ("A1",), (HexCoord(2, 0),)),
        )

        battle = engine.state.metadata["battles"][0]
        assert battle.id == 1
        assert battle.resolved is False

        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, ResolveBattleAction(PLAYER_A, battle_id=1))

        battle = engine.state.metadata["battles"][0]
        assert battle.id == 1
        assert battle.resolved is True
        assert battle.result is not None
        assert battle.dice_roll is not None
