"""Functional tests for combat declaration system."""

import pytest

from hexwar.core.actions import (
    DeclareAttackAction, EndPhaseAction, UndeclareAttackAction,
)
from hexwar.core.events import AttackDeclared, AttackUndeclared
from hexwar.core.hex import HexCoord
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal,
    assert_action_legal,
    do_actions,
    make_engine,
    make_unit,
)


def _enter_combat_phase(engine):
    """Advance to combat_a phase."""
    do_actions(engine, EndPhaseAction(player=PLAYER_A))
    assert engine.current_phase.id == "combat_a"


class TestDeclarationBasic:
    def test_combat_phase_initializes_metadata(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        md = engine.state.metadata
        assert md["combat_sub_phase"] == "declaration"
        assert md["battles"] == []
        assert md["next_battle_id"] == 1

    def test_declare_single_attacker_single_defender(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=4),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        _enter_combat_phase(engine)
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        events = engine.submit_action(declare)
        assert any(isinstance(e, AttackDeclared) for e in events)
        event = next(e for e in events if isinstance(e, AttackDeclared))
        assert event.battle_id == 1
        assert event.attacker_ids == ("a1",)
        assert event.defender_ids == ("b1",)
        assert event.attack_ratio == "4:3"

    def test_declare_creates_battle_in_metadata(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        engine.submit_action(declare)
        battles = engine.state.metadata["battles"]
        assert len(battles) == 1
        assert battles[0].id == 1
        assert battles[0].attacker_ids == ("a1",)
        assert battles[0].defender_ids == ("b1",)

    def test_cannot_declare_non_adjacent(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=4, r=4),
        ])
        _enter_combat_phase(engine)
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(4, 4),),
        )
        assert_action_illegal(engine, declare)


class TestDeclarationMultiUnit:
    def test_fan_in_multiple_attackers_one_defender(self):
        """Multiple attacker hexes → one defender hex is valid."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=3),
            make_unit("a2", player=PLAYER_A, q=2, r=0, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=5),
        ])
        _enter_combat_phase(engine)
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1", "a2"),
            defender_hexes=(HexCoord(2, 1),),
        )
        assert_action_legal(engine, declare)
        events = engine.submit_action(declare)
        event = next(e for e in events if isinstance(e, AttackDeclared))
        assert event.attack_ratio == "6:5"

    def test_fan_out_one_attacker_hex_multiple_defenders(self):
        """One attacker hex → multiple defender hexes is valid."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=2, r=2, strength=4),
            make_unit("b1", player=PLAYER_B, q=3, r=2, strength=2),
            make_unit("b2", player=PLAYER_B, q=2, r=3, strength=2),
        ])
        _enter_combat_phase(engine)
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 3), HexCoord(3, 2)),
        )
        assert_action_legal(engine, declare)

    def test_many_to_many_forbidden(self):
        """Multiple attacker hexes → multiple defender hexes is FORBIDDEN."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=3),
            make_unit("a2", player=PLAYER_A, q=3, r=1, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
            make_unit("b2", player=PLAYER_B, q=2, r=0, strength=3),
        ])
        _enter_combat_phase(engine)
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1", "a2"),
            defender_hexes=(HexCoord(2, 1), HexCoord(2, 0)),
        )
        assert_action_illegal(engine, declare)


class TestDeclarationCommitment:
    def test_unit_cannot_be_committed_twice(self):
        """Rule 7.27: each unit attacks only once."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
            make_unit("b2", player=PLAYER_B, q=0, r=1, strength=3),
        ])
        _enter_combat_phase(engine)
        # Declare a1 attacking b1
        declare1 = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        engine.submit_action(declare1)
        # Try to also declare a1 attacking b2 — should be illegal
        declare2 = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(0, 1),),
        )
        assert_action_illegal(engine, declare2)

    def test_defender_cannot_be_committed_twice(self):
        """Rule 7.27: each unit is attacked only once."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=3),
            make_unit("a2", player=PLAYER_A, q=3, r=1, strength=3),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=3),
        ])
        _enter_combat_phase(engine)
        # a1 attacks b1
        declare1 = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        engine.submit_action(declare1)
        # a2 also tries to attack b1 — should be illegal
        declare2 = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a2",),
            defender_hexes=(HexCoord(2, 1),),
        )
        assert_action_illegal(engine, declare2)


class TestUndeclare:
    def test_undeclare_removes_battle(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        engine.submit_action(DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),)
        ))
        assert len(engine.state.metadata["battles"]) == 1

        events = engine.submit_action(UndeclareAttackAction(player=PLAYER_A, battle_id=1))
        assert any(isinstance(e, AttackUndeclared) for e in events)
        assert len(engine.state.metadata["battles"]) == 0

    def test_undeclare_frees_units(self):
        """After undeclare, units can be used in new declarations."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
            make_unit("b2", player=PLAYER_B, q=0, r=1),
        ])
        _enter_combat_phase(engine)
        engine.submit_action(DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),)
        ))
        # a1 is committed, can't attack b2
        declare_b2 = DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(0, 1),)
        )
        assert_action_illegal(engine, declare_b2)

        # Undeclare, now a1 is free
        engine.submit_action(UndeclareAttackAction(player=PLAYER_A, battle_id=1))
        assert_action_legal(engine, declare_b2)

    def test_undeclare_invalid_id_does_nothing(self):
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        # No such battle_id=99
        undeclare = UndeclareAttackAction(player=PLAYER_A, battle_id=99)
        assert_action_illegal(engine, undeclare)


class TestObligations:
    def test_obligated_attackers_computed(self):
        """Units adjacent to enemy must attack (rule 7.22)."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        assert "a1" in engine.state.metadata["obligated_attackers"]

    def test_obligated_enemies_computed(self):
        """Enemies in your ZOC must be attacked (rule 7.21)."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        assert "b1" in engine.state.metadata["obligated_enemies"]

    def test_entrenched_unit_not_obligated(self):
        """Exception 9.23: units in field fortifications don't have to attack."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        # Manually set entrenchment for a1
        from hexwar.core.actions import EntrenchAction
        engine.submit_action(EntrenchAction(player=PLAYER_A, unit_id="a1"))
        _enter_combat_phase(engine)
        assert "a1" not in engine.state.metadata["obligated_attackers"]

    def test_end_phase_blocked_when_obligations_unmet(self):
        """EndPhaseAction not in legal_actions until all obligations satisfied."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        end = EndPhaseAction(player=PLAYER_A)
        assert_action_illegal(engine, end)

    def test_end_phase_allowed_when_obligations_met(self):
        """EndPhaseAction appears after all obligations satisfied."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        _enter_combat_phase(engine)
        # Declare the required attack
        engine.submit_action(DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),)
        ))
        end = EndPhaseAction(player=PLAYER_A)
        assert_action_legal(engine, end)

    def test_no_obligations_when_no_adjacent_enemies(self):
        """No obligations when units are far apart."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=0, r=0),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        _enter_combat_phase(engine)
        assert engine.state.metadata["declaration_complete"] is True
        end = EndPhaseAction(player=PLAYER_A)
        assert_action_legal(engine, end)


class TestRule724AllUnitsOnHex:
    def test_all_enemies_on_hex_attacked_together(self):
        """Rule 7.24: can't pick individual units, all on hex are targeted."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=1, r=1, strength=5),
            make_unit("b1", player=PLAYER_B, q=2, r=1, strength=2),
            make_unit("b2", player=PLAYER_B, q=2, r=1, strength=2),
        ])
        _enter_combat_phase(engine)
        declare = DeclareAttackAction(
            player=PLAYER_A,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
        )
        events = engine.submit_action(declare)
        event = next(e for e in events if isinstance(e, AttackDeclared))
        # Both b1 and b2 are on hex (2,1), both must be defenders
        assert "b1" in event.defender_ids
        assert "b2" in event.defender_ids
        assert event.attack_ratio == "5:4"  # 5 vs 2+2


class TestMetadataCleanup:
    def test_combat_metadata_cleaned_on_phase_exit(self):
        """Combat metadata removed when leaving combat phase."""
        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=0, r=0),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        _enter_combat_phase(engine)
        assert "combat_sub_phase" in engine.state.metadata
        # End the combat phase (no obligations since units far apart)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        assert "combat_sub_phase" not in engine.state.metadata
        assert "battles" not in engine.state.metadata

    def test_movement_works_after_combat_phase(self):
        """Units can move in next movement phase after combat cleanup.

        Regression: _cleanup_combat_metadata was dropping units_by_hex,
        making units_at() return empty and blocking all unit selection/movement.
        """
        from hexwar.core.actions import MoveAction

        engine = make_engine(units=[
            make_unit("a1", player=PLAYER_A, q=0, r=0),
            make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        # Full cycle: move_a -> combat_a -> strategic_move_a -> move_b
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # -> combat_a
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # -> strategic_move_a
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # -> move_b
        assert engine.current_phase.id == "move_b"
        assert len(engine.state.units_by_hex) > 0
        assert len(engine.state.units_at(HexCoord(5, 5))) == 1
        legal = engine.get_legal_actions()
        moves = [a for a in legal if isinstance(a, MoveAction)]
        assert len(moves) > 0

        # Continue: move_b -> combat_b -> strategic_move_b -> move_a (turn 2)
        do_actions(engine, EndPhaseAction(player=PLAYER_B))  # -> combat_b
        do_actions(engine, EndPhaseAction(player=PLAYER_B))  # -> strategic_move_b
        do_actions(engine, EndPhaseAction(player=PLAYER_B))  # -> move_a (turn 2)
        assert engine.current_phase.id == "move_a"
        assert engine.state.turn == 2
        assert len(engine.state.units_by_hex) > 0
        legal2 = engine.get_legal_actions()
        moves2 = [a for a in legal2 if isinstance(a, MoveAction)]
        assert len(moves2) > 0
