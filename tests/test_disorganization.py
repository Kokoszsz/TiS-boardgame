"""Tests for disorganization rolls (rule 7.32, 14.1, 14.3)."""
from __future__ import annotations

from hexwar.core.actions import (
    DeclareAttackAction, EndPhaseAction, ResolveBattleAction,
    ResolveDisorgRollsAction,
)
from hexwar.core.battle import Battle, PostBattlePhase
from hexwar.core.combat_results import CombatResult
from hexwar.core.engine import Engine
from hexwar.core.events import DisorganizationRolled, UnitDisorganized
from hexwar.core.hex import HexCoord
from hexwar.core.rng import GameRNG
from hexwar.core.state import build_initial_state
from hexwar.systems.wb48.combat_resolution import ResolutionMixin
from hexwar.systems.wb48.crt import DISORG_THRESHOLD
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B, WB48System

from tests.conftest import do_actions, make_engine, make_map, make_unit


class SequenceRNG(GameRNG):
    """RNG that returns a fixed sequence of dice values for tests."""

    def __init__(self, dice_sequence: list[int]):
        super().__init__(seed=0)
        self._queue = list(dice_sequence)

    def roll_d6(self) -> int:
        return self._queue.pop(0)

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        return [self._queue.pop(0) for _ in range(count)]


def _engine_with_rng(units, rng: GameRNG) -> Engine:
    """Build engine with a custom rng."""
    state = build_initial_state(
        scenario_id="test", scenario_name="Test", system_id="test",
        hex_map=make_map(), units=units, active_player=PLAYER_A,
    )
    return Engine(state, WB48System(), rng)


def _make_battle(
    attacker_ids=("a1",),
    defender_ids=("b1",),
    result: CombatResult | None = None,
    retreat_paths: dict | None = None,
    post_phase: PostBattlePhase = PostBattlePhase.DISORG_ROLLS,
) -> Battle:
    return Battle(
        id=1,
        attacker_ids=attacker_ids,
        defender_hexes=(HexCoord(2, 1),),
        defender_ids=defender_ids,
        resolved=True,
        result=result or CombatResult(),
        retreat_paths=retreat_paths or {},
        post_phase=post_phase,
    )


# ---------------------------------------------------------------------------
# _compute_disorg_rolls (pure function tests)
# ---------------------------------------------------------------------------


class TestComputeDisorgRolls:

    def test_no_flags_no_retreat_no_rolls(self):
        engine = make_engine(units=[make_unit("a1"), make_unit("b1", player=PLAYER_B)])
        battle = _make_battle(result=CombatResult())
        mixin = ResolutionMixin()
        assert mixin._compute_disorg_rolls(engine.state, battle) == {}

    def test_star_flag_attacker_one_roll_per_participant(self):
        engine = make_engine(units=[
            make_unit("a1"), make_unit("a2"),
            make_unit("b1", player=PLAYER_B),
        ])
        battle = _make_battle(
            attacker_ids=("a1", "a2"),
            result=CombatResult(attacker_deorganized_roll=True),
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {"a1": 1, "a2": 1}

    def test_star_flag_defender_only(self):
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
        ])
        battle = _make_battle(result=CombatResult(defender_deorganized_roll=True))
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {"b1": 1}

    def test_actual_retreat_two_hexes_one_roll(self):
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
        ])
        battle = _make_battle(
            result=CombatResult(defender_retreat=2),
            retreat_paths={"b1": (HexCoord(3, 1), HexCoord(4, 1))},
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {"b1": 1}

    def test_actual_retreat_three_hexes_two_rolls(self):
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
        ])
        battle = _make_battle(
            result=CombatResult(defender_retreat=3),
            retreat_paths={"b1": (HexCoord(3, 1), HexCoord(4, 1), HexCoord(5, 1))},
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {"b1": 2}

    def test_actual_retreat_four_hexes_three_rolls(self):
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
        ])
        battle = _make_battle(
            result=CombatResult(defender_retreat=4),
            retreat_paths={"b1": tuple(HexCoord(3 + i, 1) for i in range(4))},
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {"b1": 3}

    def test_one_hex_retreat_yields_no_rolls(self):
        """Player chose B3 → 1 retreat + 2 PSB → only 1 actual hex → 0 rolls."""
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
        ])
        battle = _make_battle(
            result=CombatResult(defender_retreat=3),
            retreat_paths={"b1": (HexCoord(3, 1),)},
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {}

    def test_star_plus_retreat_stacks(self):
        """`*B3` for defender retreating 3 hexes → 1 (star) + 2 (B3) = 3 rolls."""
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
        ])
        battle = _make_battle(
            result=CombatResult(defender_retreat=3, defender_deorganized_roll=True),
            retreat_paths={"b1": (HexCoord(3, 1), HexCoord(4, 1), HexCoord(5, 1))},
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {"b1": 3}

    def test_skips_dead_units(self):
        """Eliminated unit (not in state) → no rolls owed."""
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
            # b2 in battle but not in state (eliminated)
        ])
        battle = _make_battle(
            defender_ids=("b1", "b2"),
            result=CombatResult(defender_deorganized_roll=True),
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {"b1": 1}

    def test_skips_already_disorganized(self):
        """Unit already D → no further rolls owed."""
        units = [
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B),
        ]
        engine = make_engine(units=units)
        # Mark b1 as disorganized
        b1 = engine.state.get_unit("b1")
        engine._state = engine.state.with_unit(b1.with_disorganized(True))

        battle = _make_battle(
            result=CombatResult(defender_deorganized_roll=True),
        )
        rolls = ResolutionMixin()._compute_disorg_rolls(engine.state, battle)
        assert rolls == {}


# ---------------------------------------------------------------------------
# ResolveDisorgRollsAction handler tests (controlled rng)
# ---------------------------------------------------------------------------


class TestApplyResolveDisorgRolls:

    def _setup(self, battle: Battle, rng: GameRNG, b_disorg=False):
        units = [
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ]
        engine = _engine_with_rng(units, rng)
        # Drop into combat_a resolution sub-phase with our battle.
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # move_a → combat_a
        engine._state = engine.state.with_metadata("battles", [battle])
        engine._state = engine.state.with_metadata("combat_sub_phase", "resolution")
        if b_disorg:
            b1 = engine.state.get_unit("b1")
            engine._state = engine.state.with_unit(b1.with_disorganized(True))
        return engine

    def test_total_below_threshold_no_disorg(self):
        """2d6 = 9 < 10 threshold → no disorganization."""
        battle = _make_battle(result=CombatResult(defender_deorganized_roll=True))
        rng = SequenceRNG([4, 5])  # total 9
        engine = self._setup(battle, rng)
        events = engine.submit_action(
            ResolveDisorgRollsAction(player=PLAYER_A, battle_id=1)
        )
        rolled = [e for e in events if isinstance(e, DisorganizationRolled)]
        assert len(rolled) == 1
        assert rolled[0].total == 9
        assert rolled[0].became_disorganized is False
        assert not engine.state.get_unit("b1").disorganized
        assert not any(isinstance(e, UnitDisorganized) for e in events)

    def test_total_meets_threshold_disorganizes(self):
        """2d6 = 10 ≥ 10 threshold → disorganization."""
        battle = _make_battle(result=CombatResult(defender_deorganized_roll=True))
        rng = SequenceRNG([5, 5])  # total 10
        engine = self._setup(battle, rng)
        events = engine.submit_action(
            ResolveDisorgRollsAction(player=PLAYER_A, battle_id=1)
        )
        rolled = [e for e in events if isinstance(e, DisorganizationRolled)]
        assert rolled[0].became_disorganized is True
        assert engine.state.get_unit("b1").disorganized
        d_events = [e for e in events if isinstance(e, UnitDisorganized)]
        assert len(d_events) == 1
        assert d_events[0].unit_id == "b1"
        assert d_events[0].battle_id == 1

    def test_first_fail_skips_remaining_rolls(self):
        """B3 = 2 rolls. First fails → second skipped."""
        battle = _make_battle(
            result=CombatResult(defender_retreat=3),
            retreat_paths={"b1": (HexCoord(3, 1), HexCoord(4, 1), HexCoord(5, 1))},
        )
        rng = SequenceRNG([6, 6, 1, 1])  # only first pair consumed
        engine = self._setup(battle, rng)
        events = engine.submit_action(
            ResolveDisorgRollsAction(player=PLAYER_A, battle_id=1)
        )
        rolled = [e for e in events if isinstance(e, DisorganizationRolled)]
        assert len(rolled) == 1  # short-circuited after first failure
        assert rolled[0].became_disorganized is True

    def test_two_safe_rolls_no_disorg(self):
        """B3 = 2 rolls. Both succeed → no D."""
        battle = _make_battle(
            result=CombatResult(defender_retreat=3),
            retreat_paths={"b1": (HexCoord(3, 1), HexCoord(4, 1), HexCoord(5, 1))},
        )
        rng = SequenceRNG([1, 1, 2, 2])
        engine = self._setup(battle, rng)
        events = engine.submit_action(
            ResolveDisorgRollsAction(player=PLAYER_A, battle_id=1)
        )
        rolled = [e for e in events if isinstance(e, DisorganizationRolled)]
        assert len(rolled) == 2
        assert all(not r.became_disorganized for r in rolled)
        assert not engine.state.get_unit("b1").disorganized

    def test_threshold_constant(self):
        """DISORG_THRESHOLD propagates into event."""
        battle = _make_battle(result=CombatResult(defender_deorganized_roll=True))
        rng = SequenceRNG([1, 1])
        engine = self._setup(battle, rng)
        events = engine.submit_action(
            ResolveDisorgRollsAction(player=PLAYER_A, battle_id=1)
        )
        rolled = [e for e in events if isinstance(e, DisorganizationRolled)]
        assert rolled[0].threshold == DISORG_THRESHOLD


# ---------------------------------------------------------------------------
# Phase flow tests
# ---------------------------------------------------------------------------


class TestPhaseFlow:

    def test_skip_empty_phase_skips_disorg_with_no_rolls(self):
        """Battle with no rolls owed → DISORG_ROLLS skipped to PURSUIT."""
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        mixin = ResolutionMixin()
        battle = _make_battle(
            result=CombatResult(),  # no star, no retreat
            post_phase=PostBattlePhase.DISORG_ROLLS,
        ).replace(pursuing_side="attacker")
        next_phase = mixin._skip_empty_phase(engine.state, battle)
        assert next_phase == PostBattlePhase.PURSUIT

    def test_skip_disorg_and_pursuit_when_all_pursuers_disorg(self):
        """DISORG_ROLLS skipped (no rolls) + PURSUIT skipped (all pursuers D) → DONE."""
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        a1 = engine.state.get_unit("a1")
        engine._state = engine.state.with_unit(a1.with_disorganized(True))
        mixin = ResolutionMixin()
        battle = _make_battle(
            result=CombatResult(),
            post_phase=PostBattlePhase.DISORG_ROLLS,
        ).replace(pursuing_side="attacker")
        next_phase = mixin._skip_empty_phase(engine.state, battle)
        assert next_phase == PostBattlePhase.DONE

    def test_skip_empty_phase_holds_disorg_with_rolls(self):
        engine = make_engine(units=[
            make_unit("a1"),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        mixin = ResolutionMixin()
        battle = _make_battle(
            result=CombatResult(defender_deorganized_roll=True),
            post_phase=PostBattlePhase.DISORG_ROLLS,
        )
        next_phase = mixin._skip_empty_phase(engine.state, battle)
        assert next_phase == PostBattlePhase.DISORG_ROLLS

    def test_initial_post_phase_star_only_routes_to_disorg(self):
        mixin = ResolutionMixin()
        result = CombatResult(attacker_deorganized_roll=True)
        assert mixin._initial_post_phase(result) == PostBattlePhase.DISORG_ROLLS


# ---------------------------------------------------------------------------
# Pursuit interaction (rule 14.3)
# ---------------------------------------------------------------------------


class TestPursuitFiltersDisorganized:

    def test_disorganized_unit_excluded_from_pursuit(self):
        """Rule 14.3: D unit cannot pursue."""
        engine = make_engine(units=[
            make_unit("a1", q=1, r=1),
            make_unit("a2", q=1, r=2),
            make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        # Mark a1 disorganized
        a1 = engine.state.get_unit("a1")
        engine._state = engine.state.with_unit(a1.with_disorganized(True))

        mixin = ResolutionMixin()
        battle = _make_battle(
            attacker_ids=("a1", "a2"),
            post_phase=PostBattlePhase.PURSUIT,
            retreat_paths={"b1": (HexCoord(3, 1),)},
        ).replace(
            pursuing_side="attacker",
            combatant_origin={"b1": HexCoord(2, 1)},
        )
        actions = mixin._legal_pursuit_actions(engine.state, PLAYER_A, battle)
        # a1 (D) excluded; a2 may generate pursuit actions
        pursuit_unit_ids = {a.unit_id for a in actions if hasattr(a, "unit_id")}
        assert "a1" not in pursuit_unit_ids
