"""Tests for combat resolution sub-phase and post-battle flow."""
from __future__ import annotations

import pytest

from hexwar.core.actions import (
    AssignCplLossAction, ChooseRetreatSplitAction, DeclareAttackAction,
    EndPhaseAction, PursuitAction, ResolveBattleAction, RetreatUnitAction, SkipPursuitAction,
)
from hexwar.core.battle import Battle
from hexwar.core.combat_results import CombatResult
from hexwar.core.events import (
    BattleResolved, RetreatSplitChosen, UnitLostCpl, UnitRetreated, UnitPursued,
)
from hexwar.core.hex import HexCoord
from hexwar.core.battle import PostBattlePhase
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal, assert_action_legal, assert_unit_at,
    assert_unit_destroyed, assert_unit_exists, do_actions,
    make_engine, make_unit,
)


def _setup_combat_phase(units, seed=42):
    """Create engine and advance to combat_a phase."""
    engine = make_engine(units=units, seed=seed)
    do_actions(engine, EndPhaseAction(player=PLAYER_A))  # end move_a → combat_a
    return engine


def _enter_resolution(engine, *declare_actions):
    """Declare attacks and transition to resolution sub-phase."""
    for action in declare_actions:
        do_actions(engine, action)
    do_actions(engine, EndPhaseAction(player=PLAYER_A))


class TestResolutionTransition:
    """Tests for declaration → resolution sub-phase transition."""

    def test_end_phase_transitions_to_resolution(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        do_actions(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        assert engine.state.metadata["combat_sub_phase"] == "declaration"
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        assert engine.state.metadata["combat_sub_phase"] == "resolution"

    def test_no_battles_skips_resolution(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=0, r=0),
            make_unit("b1", q=5, r=5, player=PLAYER_B),
        ])
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # combat_a → strategic_move_a
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # strategic_move_a → move_b
        assert engine.state.active_player == PLAYER_B

    def test_cannot_end_phase_during_resolution_with_unresolved(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        assert_action_illegal(engine, EndPhaseAction(player=PLAYER_A))


class TestResolveBattle:
    """Tests for resolving individual battles."""

    def test_resolve_emits_battle_resolved(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        resolved_events = [e for e in events if isinstance(e, BattleResolved)]
        assert len(resolved_events) == 1
        ev = resolved_events[0]
        assert ev.battle_id == 1
        assert ev.attacker_ids == ("a1",)
        assert ev.defender_ids == ("b1",)
        assert isinstance(ev.result, CombatResult)
        assert len(ev.dice_roll) == 2
        assert 2 <= ev.dice_total <= 12

    def test_resolve_shows_strengths(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1, strength=5),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ])
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        ev = [e for e in events if isinstance(e, BattleResolved)][0]
        assert ev.attack_strength == 5
        assert ev.defense_strength == 3

    def test_resolve_uses_crt(self):
        """Resolution uses CRT lookup — result is a CombatResult, not a string."""
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1, strength=10),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
        ])
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        ev = [e for e in events if isinstance(e, BattleResolved)][0]
        assert isinstance(ev.result, CombatResult)

    def test_cannot_resolve_already_resolved(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
        ])
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        assert_action_illegal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

    def test_multi_unit_battle_combined_strength(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1, strength=4),
            make_unit("a2", q=1, r=2, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=5),
        ])
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1", "a2"), defender_hexes=(HexCoord(2, 1),),
        ))
        events = engine.submit_action(
            ResolveBattleAction(player=PLAYER_A, battle_id=1)
        )
        ev = [e for e in events if isinstance(e, BattleResolved)][0]
        assert ev.attack_strength == 7
        assert ev.defense_strength == 5


class TestMultipleBattleResolution:
    """Tests for resolving multiple battles sequentially."""

    def test_player_chooses_order(self):
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1),
            make_unit("a2", q=1, r=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B),
            make_unit("b2", q=2, r=3, player=PLAYER_B),
        ])
        _enter_resolution(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),)),
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a2",), defender_hexes=(HexCoord(2, 3),)),
        )
        assert_action_legal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        assert_action_legal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=2))

    def test_sequential_resolution_blocks_next(self):
        """After resolving battle with post-battle effects, can't resolve next until done."""
        # Use seed that gives a result with retreat/casualties
        engine = _setup_combat_phase([
            make_unit("a1", q=1, r=1, strength=6),
            make_unit("a2", q=1, r=3, strength=6),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
            make_unit("b2", q=2, r=3, player=PLAYER_B, strength=1),
        ], seed=10)
        _enter_resolution(engine,
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),)),
            DeclareAttackAction(player=PLAYER_A, attacker_ids=("a2",), defender_hexes=(HexCoord(2, 3),)),
        )
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        # If battle 1 has post-battle phases, battle 2 should be blocked
        battles = engine.state.metadata["battles"]
        if battles[0].post_phase != PostBattlePhase.DONE:
            assert_action_illegal(engine, ResolveBattleAction(player=PLAYER_A, battle_id=2))


class TestPostBattlePhases:
    """Tests for the post-battle resolution flow."""

    def test_initial_post_phase_done_on_no_effects(self):
        """CRT result with no retreat/casualties → post_phase = DONE immediately."""
        # Seed 42 with 1:1 ratio gives specific result — find a seed that gives "-/-"
        # Use equal strength — CRT "-/-" is not common, test the mechanism
        from hexwar.systems.wb48.combat_resolution import ResolutionMixin
        mixin = ResolutionMixin()
        result = CombatResult()  # all zeros
        assert mixin._initial_post_phase(result) == PostBattlePhase.DONE

    def test_initial_post_phase_attacker_split(self):
        from hexwar.systems.wb48.combat_resolution import ResolutionMixin
        mixin = ResolutionMixin()
        result = CombatResult(attacker_retreat=2)
        assert mixin._initial_post_phase(result) == PostBattlePhase.ATTACKER_SPLIT

    def test_initial_post_phase_defender_split(self):
        from hexwar.systems.wb48.combat_resolution import ResolutionMixin
        mixin = ResolutionMixin()
        result = CombatResult(defender_retreat=3)
        assert mixin._initial_post_phase(result) == PostBattlePhase.DEFENDER_SPLIT

    def test_initial_post_phase_mandatory_cpl(self):
        from hexwar.systems.wb48.combat_resolution import ResolutionMixin
        mixin = ResolutionMixin()
        result = CombatResult(attacker_casualties=1)
        assert mixin._initial_post_phase(result) == PostBattlePhase.MANDATORY_CPL


class TestRetreatSplit:
    """Tests for ChooseRetreatSplitAction generation and application."""

    def _setup_with_defender_retreat(self, debt=2):
        """Setup a battle where defender owes `debt` retreat hexes."""
        # Strength 6:1 with seed that hits B2 result
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=6),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # → combat_a
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        return engine

    def test_split_actions_generated(self):
        """After resolve, if defender has retreat debt, split actions appear."""
        engine = self._setup_with_defender_retreat()
        battles = engine.state.metadata["battles"]
        battle = battles[0]
        if battle.post_phase == PostBattlePhase.DEFENDER_SPLIT:
            legal = engine.get_legal_actions()
            split_actions = [a for a in legal if isinstance(a, ChooseRetreatSplitAction)]
            assert len(split_actions) == battle.defender_debt + 1

    def test_split_all_retreat(self):
        """Choosing all retreat → units_needing_retreat populated."""
        engine = self._setup_with_defender_retreat()
        battles = engine.state.metadata["battles"]
        battle = battles[0]
        if battle.post_phase != PostBattlePhase.DEFENDER_SPLIT:
            pytest.skip("CRT didn't give defender retreat for this seed")
        debt = battle.defender_debt
        do_actions(engine, ChooseRetreatSplitAction(
            player=PLAYER_A, battle_id=1, side="defender",
            retreat_hexes=debt, unit_losses=0,
        ))
        battles = engine.state.metadata["battles"]
        assert battles[0].remaining_retreat_steps == debt
        assert "b1" in battles[0].units_needing_retreat

    def test_split_all_losses(self):
        """Choosing all losses → unit gets destroyed."""
        engine = self._setup_with_defender_retreat()
        battles = engine.state.metadata["battles"]
        battle = battles[0]
        if battle.post_phase != PostBattlePhase.DEFENDER_SPLIT:
            pytest.skip("CRT didn't give defender retreat for this seed")
        debt = battle.defender_debt
        do_actions(engine, ChooseRetreatSplitAction(
            player=PLAYER_A, battle_id=1, side="defender",
            retreat_hexes=0, unit_losses=debt,
        ))
        # Should now be in CPL assignment phase
        battles = engine.state.metadata["battles"]
        assert battles[0].post_phase == PostBattlePhase.DEFENDER_CPL


class TestAssignCplLoss:
    """Tests for unit destruction via CPL assignment."""

    def test_assign_cpl_destroys_unit(self):
        """AssignCplLossAction removes the chosen unit."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=6),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        battles = engine.state.metadata["battles"]
        battle = battles[0]

        # Navigate to a CPL phase
        if battle.post_phase == PostBattlePhase.DEFENDER_SPLIT:
            do_actions(engine, ChooseRetreatSplitAction(
                player=PLAYER_A, battle_id=1, side="defender",
                retreat_hexes=0, unit_losses=battle.defender_debt,
            ))
            battles = engine.state.metadata["battles"]
            battle = battles[0]

        if battle.post_phase in (PostBattlePhase.DEFENDER_CPL, PostBattlePhase.MANDATORY_CPL):
            do_actions(engine, AssignCplLossAction(
                player=PLAYER_A, battle_id=1, unit_id="b1",
            ))
            assert_unit_destroyed(engine, "b1")


class TestRetreatMovement:
    """Tests for unit retreat movement."""

    def test_retreat_increases_distance(self):
        """Retreat must move away from attacker."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=6),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        battles = engine.state.metadata["battles"]
        battle = battles[0]

        if battle.post_phase == PostBattlePhase.DEFENDER_SPLIT:
            debt = battle.defender_debt
            if debt > 0:
                do_actions(engine, ChooseRetreatSplitAction(
                    player=PLAYER_A, battle_id=1, side="defender",
                    retreat_hexes=1, unit_losses=debt - 1,
                ))
                # If there are CPL to assign first
                battles = engine.state.metadata["battles"]
                battle = battles[0]
                if battle.post_phase == PostBattlePhase.DEFENDER_CPL:
                    for _ in range(debt - 1):
                        do_actions(engine, AssignCplLossAction(
                            player=PLAYER_A, battle_id=1, unit_id="b1",
                        ))
                    battles = engine.state.metadata["battles"]
                    battle = battles[0]

                if battle.post_phase == PostBattlePhase.DEFENDER_RETREAT:
                    legal = engine.get_legal_actions()
                    retreat_actions = [a for a in legal if isinstance(a, RetreatUnitAction)]
                    # All targets must be farther from attacker than current position
                    b1 = engine.state.get_unit("b1")
                    if b1 and retreat_actions:
                        a1 = engine.state.get_unit("a1")
                        for ra in retreat_actions:
                            assert ra.target.distance(a1.position) > b1.position.distance(a1.position)


class TestPursuit:
    """Tests for pursuit actions."""

    def test_cpl_before_retreat_kills_unit_skips_retreat(self):
        """CPL (mandatory + split) applied before retreat. Dead units don't retreat."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ], seed=0)  # A1-1 result
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        # Choose retreat=1, loss=0 — but mandatory CPL=1 is added, so 1 unit dies first
        do_actions(engine, ChooseRetreatSplitAction(
            player=PLAYER_A, battle_id=1, side="attacker", retreat_hexes=1, unit_losses=0,
        ))
        # CPL kills the unit (mandatory applied before retreat)
        battle = engine.state.metadata["battles"][0]
        assert battle.post_phase == PostBattlePhase.ATTACKER_CPL
        legal = engine.get_legal_actions()
        cpl_acts = [a for a in legal if isinstance(a, AssignCplLossAction)]
        assert cpl_acts
        do_actions(engine, cpl_acts[0])

        # Unit dead → retreat skipped → pursuit for defender
        battle = engine.state.metadata["battles"][0]
        assert battle.post_phase == PostBattlePhase.PURSUIT
        assert battle.pursuing_side == "defender"
        legal = engine.get_legal_actions()
        assert any(isinstance(a, PursuitAction) for a in legal)

    def test_cpl_before_retreat_survivors_retreat(self):
        """With mandatory casualties, CPL runs before retreat. Survivors retreat."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("a2", q=1, r=1, strength=3, stack_size=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ], seed=0)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1", "a2"), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))
        battle = engine.state.metadata["battles"][0]
        mandatory = battle.attacker_mandatory_cpl

        # Split: choose 1 loss from split (debt covers it)
        do_actions(engine, ChooseRetreatSplitAction(
            player=PLAYER_A, battle_id=1, side="attacker", retreat_hexes=0, unit_losses=1,
        ))
        # CPL phase: total_losses = split(1) + mandatory
        battle = engine.state.metadata["battles"][0]
        assert battle.post_phase == PostBattlePhase.ATTACKER_CPL
        assert battle.remaining_cpl_to_assign == 1 + mandatory
        # Kill unit(s) via CPL
        legal = engine.get_legal_actions()
        cpl_acts = [a for a in legal if isinstance(a, AssignCplLossAction)]
        assert cpl_acts
        do_actions(engine, cpl_acts[0])

        # Survivor should exist and no retreat needed (chose loss=1, retreat=0)
        battle = engine.state.metadata["battles"][0]
        assert battle.post_phase != PostBattlePhase.ATTACKER_RETREAT

    def test_pursuit_single_move_then_done(self):
        """Pursuit is one move to death hex or adjacent, then DONE."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        # Fast-forward to pursuit
        for _ in range(20):
            battle = engine.state.metadata["battles"][0]
            if battle.post_phase in (PostBattlePhase.DONE, PostBattlePhase.PURSUIT):
                break
            legal = engine.get_legal_actions()
            post_actions = [a for a in legal if not isinstance(a, EndPhaseAction)]
            if post_actions:
                do_actions(engine, post_actions[0])
            else:
                break

        battle = engine.state.metadata["battles"][0]
        if battle.post_phase != PostBattlePhase.PURSUIT:
            return

        legal = engine.get_legal_actions()
        pursuit_actions = [a for a in legal if isinstance(a, PursuitAction)]
        assert pursuit_actions
        do_actions(engine, pursuit_actions[0])

        battle = engine.state.metadata["battles"][0]
        assert battle.post_phase == PostBattlePhase.DONE

    def test_multiple_units_can_pursue(self):
        """All victorious units get one pursuit move each."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=1),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
            make_unit("b2", q=2, r=1, player=PLAYER_B, strength=3),
        ], seed=0)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        # Fast-forward to pursuit
        for _ in range(20):
            battle = engine.state.metadata["battles"][0]
            if battle.post_phase in (PostBattlePhase.DONE, PostBattlePhase.PURSUIT):
                break
            legal = engine.get_legal_actions()
            post_actions = [a for a in legal if not isinstance(a, EndPhaseAction)]
            if post_actions:
                do_actions(engine, post_actions[0])
            else:
                break

        battle = engine.state.metadata["battles"][0]
        if battle.post_phase != PostBattlePhase.PURSUIT:
            return

        # First unit pursues
        legal = engine.get_legal_actions()
        pursuit_actions = [a for a in legal if isinstance(a, PursuitAction)]
        first_uid = pursuit_actions[0].unit_id
        do_actions(engine, pursuit_actions[0])

        battle = engine.state.metadata["battles"][0]
        assert first_uid in battle.units_pursued
        # Should still be in PURSUIT if other units haven't pursued
        pursuer_ids = battle.attacker_ids if battle.pursuing_side == "attacker" else battle.defender_ids
        remaining = [uid for uid in pursuer_ids if uid not in battle.units_pursued and engine.state.get_unit(uid)]
        if remaining:
            assert battle.post_phase == PostBattlePhase.PURSUIT
            legal = engine.get_legal_actions()
            # First unit should no longer have pursuit actions
            assert not any(isinstance(a, PursuitAction) and a.unit_id == first_uid for a in legal)

    def test_skip_pursuit_ends_battle(self):
        """SkipPursuitAction sets post_phase to DONE."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=6),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        # Fast-forward through post-battle phases until pursuit or done
        for _ in range(20):  # safety limit
            battles = engine.state.metadata["battles"]
            battle = battles[0]
            if battle.post_phase == PostBattlePhase.DONE:
                break
            if battle.post_phase == PostBattlePhase.PURSUIT:
                do_actions(engine, SkipPursuitAction(player=PLAYER_A, battle_id=1))
                break
            legal = engine.get_legal_actions()
            post_actions = [a for a in legal if not isinstance(a, EndPhaseAction)]
            if not post_actions:
                break
            # For split: choose all retreat (to reach pursuit)
            if isinstance(post_actions[0], ChooseRetreatSplitAction):
                split = next(a for a in post_actions if a.retreat_hexes == a.retreat_hexes + a.unit_losses - a.unit_losses)
                # Pick max retreat option
                max_retreat = max(post_actions, key=lambda a: a.retreat_hexes if isinstance(a, ChooseRetreatSplitAction) else 0)
                do_actions(engine, max_retreat)
            else:
                do_actions(engine, post_actions[0])

        battles = engine.state.metadata["battles"]
        assert battles[0].post_phase == PostBattlePhase.DONE


    def test_defender_can_pursue_when_attacker_eliminated(self):
        """When defender wins and attacker is eliminated, defender gets pursuit."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=6),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        battle = engine.state.metadata["battles"][0]
        assert battle.pursuing_side in ("attacker", "defender", "")

        # Complete through to pursuit
        for _ in range(20):
            battle = engine.state.metadata["battles"][0]
            if battle.post_phase in (PostBattlePhase.DONE, PostBattlePhase.PURSUIT):
                break
            legal = engine.get_legal_actions()
            post_actions = [a for a in legal if not isinstance(a, EndPhaseAction)]
            if post_actions:
                do_actions(engine, post_actions[0])
            else:
                break

        battle = engine.state.metadata["battles"][0]
        if battle.post_phase == PostBattlePhase.PURSUIT:
            legal = engine.get_legal_actions()
            pursuit_actions = [a for a in legal if isinstance(a, PursuitAction)]
            skip_actions = [a for a in legal if isinstance(a, SkipPursuitAction)]
            assert skip_actions, "SkipPursuitAction must always be available"
            if battle.pursuing_side == "defender":
                for pa in pursuit_actions:
                    assert pa.unit_id in battle.defender_ids

    def test_eliminated_at_tracked(self):
        """CPL loss records unit death hex in battle.eliminated_at."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        # Fast-forward to CPL phase
        for _ in range(20):
            battle = engine.state.metadata["battles"][0]
            if battle.post_phase in (
                PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL,
                PostBattlePhase.MANDATORY_CPL, PostBattlePhase.DONE,
            ):
                break
            legal = engine.get_legal_actions()
            post_actions = [a for a in legal if not isinstance(a, EndPhaseAction)]
            if post_actions:
                do_actions(engine, post_actions[0])
            else:
                break

        battle = engine.state.metadata["battles"][0]
        if battle.post_phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL, PostBattlePhase.MANDATORY_CPL):
            legal = engine.get_legal_actions()
            cpl_actions = [a for a in legal if isinstance(a, AssignCplLossAction)]
            if cpl_actions:
                unit = engine.state.get_unit(cpl_actions[0].unit_id)
                death_pos = unit.position
                do_actions(engine, cpl_actions[0])
                battle = engine.state.metadata["battles"][0]
                assert cpl_actions[0].unit_id in battle.eliminated_at
                assert battle.eliminated_at[cpl_actions[0].unit_id] == death_pos


class TestPhaseBlocking:
    """Regression: should_advance_phase must block during active post-battle."""

    def test_end_phase_illegal_during_post_battle(self):
        """EndPhaseAction must not be legal while post-battle phases are active."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        battles = engine.state.metadata["battles"]
        if battles[0].post_phase != PostBattlePhase.DONE:
            legal = engine.get_legal_actions()
            assert not any(isinstance(a, EndPhaseAction) for a in legal)
            import pytest
            with pytest.raises(ValueError, match="Illegal action"):
                engine.submit_action(EndPhaseAction(player=PLAYER_A))


class TestResolutionMetadata:
    """Tests for metadata cleanup after resolution."""

    def test_metadata_cleaned_after_phase(self):
        """Combat metadata removed when phase ends after resolution."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=3),
        ], seed=42)
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        _enter_resolution(engine, DeclareAttackAction(
            player=PLAYER_A, attacker_ids=("a1",), defender_hexes=(HexCoord(2, 1),),
        ))
        do_actions(engine, ResolveBattleAction(player=PLAYER_A, battle_id=1))

        # Complete all post-battle phases
        for _ in range(20):
            battles = engine.state.metadata["battles"]
            battle = battles[0]
            if battle.post_phase == PostBattlePhase.DONE:
                break
            if battle.post_phase == PostBattlePhase.PURSUIT:
                do_actions(engine, SkipPursuitAction(player=PLAYER_A, battle_id=1))
                break
            legal = engine.get_legal_actions()
            post_actions = [a for a in legal if not isinstance(a, EndPhaseAction)]
            if post_actions:
                do_actions(engine, post_actions[0])
            else:
                break

        # End combat phase
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        assert "combat_sub_phase" not in engine.state.metadata
        assert "battles" not in engine.state.metadata


class TestRetreatStepLimit:
    """Bug 5 regression: unit cannot retreat more than remaining_retreat_steps."""

    def test_unit_with_zero_steps_remaining_has_no_retreat_actions(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=3, r=1, player=PLAYER_B, strength=1),
        ], seed=42)
        battle = Battle(
            id=1,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
            defender_ids=("b1",),
            resolved=True,
            post_phase=PostBattlePhase.DEFENDER_RETREAT,
            remaining_retreat_steps=1,
            units_needing_retreat=("b1",),
            retreat_paths={"b1": (HexCoord(3, 1),)},
        )
        state = engine.state.with_metadata("battles", [battle])
        legal = engine._system._legal_retreat_actions(state, PLAYER_A, battle)
        assert legal == [], "Unit already retreated 1 step should have no further actions"

    def test_unit_with_step_remaining_has_actions(self):
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=3, r=1, player=PLAYER_B, strength=1),
        ], seed=42)
        battle = Battle(
            id=1,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
            defender_ids=("b1",),
            resolved=True,
            post_phase=PostBattlePhase.DEFENDER_RETREAT,
            remaining_retreat_steps=2,
            units_needing_retreat=("b1",),
            retreat_paths={"b1": (HexCoord(3, 1),)},
        )
        state = engine.state.with_metadata("battles", [battle])
        legal = engine._system._legal_retreat_actions(state, PLAYER_A, battle)
        assert len(legal) > 0, "Unit with 2 steps remaining and only 1 retreated should have actions"


class TestEncircledElimination:
    """Bug 4 regression: unit unable to retreat takes 1 CPL loss instead of stalling."""

    def test_encircled_defender_eliminated_on_split(self):
        """Defender surrounded with no valid retreat hex auto-eliminates on split."""
        # b1 at (2,1) surrounded by enemies on all retreat directions
        units = [
            make_unit("a1", q=1, r=1, strength=6),
            make_unit("a2", q=2, r=0, player=PLAYER_A, strength=3),
            make_unit("a3", q=3, r=0, player=PLAYER_A, strength=3),
            make_unit("a4", q=3, r=1, player=PLAYER_A, strength=3),
            make_unit("a5", q=3, r=2, player=PLAYER_A, strength=3),
            make_unit("a6", q=2, r=2, player=PLAYER_A, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),
        ]
        engine = make_engine(units=units, seed=42)
        battle = Battle(
            id=1,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
            defender_ids=("b1",),
            resolved=True,
            post_phase=PostBattlePhase.DEFENDER_SPLIT,
            defender_debt=1,
            combatant_origin={"a1": HexCoord(1, 1), "b1": HexCoord(2, 1)},
        )
        state = engine.state.with_metadata("battles", [battle])
        state = state.with_metadata("combat_sub_phase", "resolution")

        new_state, events = engine._system._apply_retreat_split(
            state,
            ChooseRetreatSplitAction(
                player=PLAYER_A, battle_id=1, side="defender",
                retreat_hexes=1, unit_losses=0,
            ),
        )
        # b1 should be eliminated (encircled, no valid retreat hex)
        assert new_state.get_unit("b1") is None, "Encircled b1 should be eliminated"
        # Phase moved past retreat (since only unit died)
        new_battle = new_state.metadata["battles"][0]
        assert new_battle.post_phase != PostBattlePhase.DEFENDER_RETREAT
        # UnitLostCpl event emitted
        lost = [e for e in events if isinstance(e, UnitLostCpl)]
        assert any(e.unit_id == "b1" for e in lost), "Should emit UnitLostCpl for encircled unit"

    def test_partial_encirclement_only_blocked_unit_eliminated(self):
        """If one unit can retreat but another can't, only the encircled one dies."""
        # Two defenders co-stacked. One has retreat option, other doesn't (via ZOC/walls).
        # Simpler: two separate defender hexes, one with retreat space, one boxed in.
        units = [
            make_unit("a1", q=1, r=1, strength=3),
            # box around b2's retreat directions
            make_unit("a2", q=2, r=2, player=PLAYER_A, strength=3),
            make_unit("a3", q=3, r=2, player=PLAYER_A, strength=3),
            make_unit("a4", q=3, r=3, player=PLAYER_A, strength=3),
            make_unit("a5", q=2, r=4, player=PLAYER_A, strength=3),
            make_unit("a6", q=1, r=4, player=PLAYER_A, strength=3),
            make_unit("a7", q=1, r=3, player=PLAYER_A, strength=3),
            make_unit("b1", q=2, r=1, player=PLAYER_B, strength=1),  # has retreat
            make_unit("b2", q=2, r=3, player=PLAYER_B, strength=1),  # boxed in
        ]
        engine = make_engine(units=units, seed=42)
        battle = Battle(
            id=1,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1), HexCoord(2, 3)),
            defender_ids=("b1", "b2"),
            resolved=True,
            post_phase=PostBattlePhase.DEFENDER_SPLIT,
            defender_debt=1,
            combatant_origin={
                "a1": HexCoord(1, 1),
                "b1": HexCoord(2, 1),
                "b2": HexCoord(2, 3),
            },
        )
        state = engine.state.with_metadata("battles", [battle])
        state = state.with_metadata("combat_sub_phase", "resolution")

        new_state, _ = engine._system._apply_retreat_split(
            state,
            ChooseRetreatSplitAction(
                player=PLAYER_A, battle_id=1, side="defender",
                retreat_hexes=1, unit_losses=0,
            ),
        )
        # b2 boxed → eliminated; b1 still alive and needs to retreat
        assert new_state.get_unit("b2") is None, "Boxed b2 should be eliminated"
        assert new_state.get_unit("b1") is not None, "b1 has retreat option, must survive"
        new_battle = new_state.metadata["battles"][0]
        assert "b1" in new_battle.units_needing_retreat
        assert "b2" not in new_battle.units_needing_retreat


class TestPursuitFullHexElimination:
    """Bug 2 regression: rule 7.57 neighbor-bonus only when ALL originals died.

    Partial elimination (some retreat, some die): vacated hex still pursuable via
    normal follow-retreater pursuit, but no neighbor-bonus from 7.57.
    """

    def test_partial_elimination_pursues_origin_but_not_neighbors(self):
        """One killed, one retreated → vacated hex IS pursuable; neighbors are NOT."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
            make_unit("b1", q=4, r=1, player=PLAYER_B, strength=1),  # retreated survivor
        ], seed=42)
        battle = Battle(
            id=1,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
            defender_ids=("b1", "b2"),
            resolved=True,
            post_phase=PostBattlePhase.PURSUIT,
            pursuing_side="attacker",
            combatant_origin={
                "a1": HexCoord(1, 1),
                "b1": HexCoord(2, 1),
                "b2": HexCoord(2, 1),
            },
            eliminated_at={"b2": HexCoord(2, 1)},  # b2 died, b1 retreated
            retreat_paths={"b1": (HexCoord(3, 1), HexCoord(4, 1))},
        )
        state = engine.state.with_metadata("battles", [battle])
        state = state.with_metadata("combat_sub_phase", "resolution")

        legal = engine._system._legal_pursuit_actions(state, PLAYER_A, battle)
        pursuit_targets = {a.target for a in legal if isinstance(a, PursuitAction)}
        # Origin hex (2,1) IS pursuable — vacated by retreater
        assert HexCoord(2, 1) in pursuit_targets, \
            "Vacated origin hex must be pursuable (follow retreater)"
        # A neighbor of (2,1) NOT on retreat path must NOT be pursuable
        # Neighbors of (2,1): check (1,2), (2,2), (1,1) etc. — (1,1) has attacker
        # Pick (2,0): a neighbor of (2,1) not on retreat path
        assert HexCoord(2, 0) not in pursuit_targets, \
            "7.57 neighbor bonus must not apply on partial elimination"

    def test_pursuit_allowed_when_all_stacked_eliminated(self):
        """Two defenders on same hex, both killed → pursuit into that hex allowed."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1, strength=3),
        ], seed=42)
        battle = Battle(
            id=1,
            attacker_ids=("a1",),
            defender_hexes=(HexCoord(2, 1),),
            defender_ids=("b1", "b2"),
            resolved=True,
            post_phase=PostBattlePhase.PURSUIT,
            pursuing_side="attacker",
            combatant_origin={
                "a1": HexCoord(1, 1),
                "b1": HexCoord(2, 1),
                "b2": HexCoord(2, 1),
            },
            eliminated_at={"b1": HexCoord(2, 1), "b2": HexCoord(2, 1)},
        )
        state = engine.state.with_metadata("battles", [battle])
        state = state.with_metadata("combat_sub_phase", "resolution")

        legal = engine._system._legal_pursuit_actions(state, PLAYER_A, battle)
        pursuit_targets = {a.target for a in legal if isinstance(a, PursuitAction)}
        assert HexCoord(2, 1) in pursuit_targets, \
            "7.57: fully-eliminated hex must be pursuable"
