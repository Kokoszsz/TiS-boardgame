"""Unit tests for CombatResult parsing and victory determination."""
from __future__ import annotations

import pytest

from hexwar.core.combat_results import BattleOutcome, CombatResult


class TestMatchCasualties:
    def test_extracts_single_digit(self):
        assert CombatResult._match_casualties("-1") == 1

    def test_extracts_multi_digit(self):
        assert CombatResult._match_casualties("-12") == 12

    def test_no_casualties(self):
        assert CombatResult._match_casualties("-") == 0

    def test_no_casualties_empty(self):
        assert CombatResult._match_casualties("") == 0

    def test_casualties_with_retreat(self):
        assert CombatResult._match_casualties("A2-1") == 1

    def test_casualties_with_disorg(self):
        assert CombatResult._match_casualties("D-2") == 2


class TestMatchRetreat:
    def test_attacker_retreat(self):
        assert CombatResult._match_retreat("A2") == 2

    def test_defender_retreat(self):
        assert CombatResult._match_retreat("B3") == 3

    def test_no_retreat(self):
        assert CombatResult._match_retreat("-") == 0

    def test_retreat_with_casualties(self):
        assert CombatResult._match_retreat("A2-1") == 2

    def test_retreat_with_disorg(self):
        assert CombatResult._match_retreat("B1D") == 1


class TestDetermineVictory:
    def test_attacker_wins_defender_retreats(self):
        assert CombatResult.determine_victory("-", "B2") == BattleOutcome.ATTACKER_WIN

    def test_attacker_wins_defender_retreats_with_casualties(self):
        assert CombatResult.determine_victory("-1", "B3-1") == BattleOutcome.ATTACKER_WIN

    def test_defender_wins_attacker_retreats(self):
        assert CombatResult.determine_victory("A2", "-") == BattleOutcome.DEFENDER_WIN

    def test_defender_wins_attacker_retreats_with_casualties(self):
        assert CombatResult.determine_victory("A1-1", "-") == BattleOutcome.DEFENDER_WIN

    def test_tie_both_retreat(self):
        assert CombatResult.determine_victory("A1", "B1") == BattleOutcome.TIE

    def test_tie_no_effects(self):
        assert CombatResult.determine_victory("-", "-") == BattleOutcome.TIE

    def test_tie_both_casualties_only(self):
        assert CombatResult.determine_victory("-1", "-1") == BattleOutcome.TIE


class TestFromString:
    def test_simple_attacker_retreat(self):
        r = CombatResult.from_string("A2/-", ratio="1:1")
        assert r.attacker_retreat == 2
        assert r.defender_retreat == 0
        assert r.attacker_casualties == 0
        assert r.defender_casualties == 0
        assert r.outcome == BattleOutcome.DEFENDER_WIN
        assert r.ratio == "1:1"

    def test_simple_defender_retreat(self):
        r = CombatResult.from_string("-/B3", ratio="3:1")
        assert r.defender_retreat == 3
        assert r.attacker_retreat == 0
        assert r.outcome == BattleOutcome.ATTACKER_WIN

    def test_mutual_casualties(self):
        r = CombatResult.from_string("-1/-1", ratio="1:1")
        assert r.attacker_casualties == 1
        assert r.defender_casualties == 1
        assert r.outcome == BattleOutcome.TIE

    def test_retreat_with_casualties(self):
        r = CombatResult.from_string("A2-1/-", ratio="1:2")
        assert r.attacker_retreat == 2
        assert r.attacker_casualties == 1
        assert r.outcome == BattleOutcome.DEFENDER_WIN

    def test_defender_retreat_with_disorg_D(self):
        r = CombatResult.from_string("-/B2D", ratio="2:1")
        assert r.defender_retreat == 2
        assert r.defender_disorganized is True
        assert r.defender_disorganized_roll == 0
        assert r.outcome == BattleOutcome.ATTACKER_WIN

    def test_star_disorg_roll(self):
        r = CombatResult.from_string("*A1/-", ratio="1:2")
        assert r.attacker_disorganized_roll == 1
        assert r.attacker_retreat == 1
        assert r.outcome == BattleOutcome.DEFENDER_WIN

    def test_star_both_sides(self):
        r = CombatResult.from_string("*-1/*-1", ratio="1:1")
        assert r.attacker_disorganized_roll == 1
        assert r.defender_disorganized_roll == 1

    def test_immediate_disorg_attacker(self):
        r = CombatResult.from_string("DA3-2/-1", ratio="1:4")
        assert r.attacker_disorganized is True
        assert r.attacker_retreat == 3
        assert r.attacker_casualties == 2
        assert r.defender_casualties == 1

    def test_no_effects(self):
        r = CombatResult.from_string("-/-", ratio="1:1")
        assert r.attacker_casualties == 0
        assert r.defender_casualties == 0
        assert r.attacker_retreat == 0
        assert r.defender_retreat == 0
        assert r.outcome == BattleOutcome.TIE

    def test_defender_only_casualties(self):
        r = CombatResult.from_string("-1/B3-1", ratio="6:1")
        assert r.attacker_casualties == 1
        assert r.defender_retreat == 3
        assert r.defender_casualties == 1
        assert r.outcome == BattleOutcome.ATTACKER_WIN


class TestStrRoundTrip:
    def test_attacker_win_format(self):
        r = CombatResult.from_string("-/B2", ratio="3:1")
        s = str(r)
        assert "(Attacker victorious)" in s
        assert "B2" in s
        assert "3:1" in s

    def test_defender_win_format(self):
        r = CombatResult.from_string("A1/-", ratio="1:2")
        s = str(r)
        assert "(Defender victorious)" in s
        assert "A1" in s

    def test_tie_format(self):
        r = CombatResult.from_string("-1/-1", ratio="1:1")
        s = str(r)
        assert "(Tie)" in s

    def test_disorg_D_in_output(self):
        r = CombatResult.from_string("-/B2D", ratio="2:1")
        s = str(r)
        assert "D" in s

    def test_star_not_in_output_without_D(self):
        r = CombatResult.from_string("*A1/-", ratio="1:3")
        s = str(r)
        assert "A1" in s
        assert r.attacker_disorganized_roll == 1
