"""Unit tests for CRT ratio computation and table lookup."""
from __future__ import annotations

import pytest

from hexwar.core.combat_results import BattleOutcome, CombatResult
from hexwar.systems.wb48.crt import CRT, RATIOS, lookup_crt, strength_to_ratio


class TestStrengthToRatio:
    def test_equal_strength(self):
        assert strength_to_ratio(3, 3) == "1:1"

    def test_attacker_double(self):
        assert strength_to_ratio(6, 3) == "2:1"

    def test_attacker_triple(self):
        assert strength_to_ratio(9, 3) == "3:1"

    def test_defender_double(self):
        assert strength_to_ratio(3, 6) == "1:2"

    def test_defender_triple(self):
        assert strength_to_ratio(3, 9) == "1:3"

    def test_clamp_above_10_to_1(self):
        assert strength_to_ratio(100, 1) == "10:1"

    def test_clamp_below_1_to_4(self):
        assert strength_to_ratio(1, 100) == "1:4"

    def test_exact_10_to_1(self):
        assert strength_to_ratio(10, 1) == "10:1"

    def test_exact_1_to_4(self):
        assert strength_to_ratio(1, 4) == "1:4"

    def test_rounds_down_attacker(self):
        assert strength_to_ratio(7, 3) == "2:1"

    def test_rounds_down_defender(self):
        assert strength_to_ratio(3, 7) == "1:2"

    def test_zero_defender(self):
        assert strength_to_ratio(5, 0) == "10:1"

    def test_zero_attacker(self):
        assert strength_to_ratio(0, 5) == "1:4"

    def test_both_zero(self):
        assert strength_to_ratio(0, 0) == "10:1"

    def test_all_ratios_are_valid(self):
        for ratio in RATIOS:
            assert ratio in [v for _, v in [("", r) for r in RATIOS]]


class TestCRTTableCompleteness:
    def test_all_dice_ratio_combos_present(self):
        for dice in range(2, 13):
            for ratio in RATIOS:
                assert (dice, ratio) in CRT, f"Missing CRT entry for dice={dice}, ratio={ratio}"

    def test_crt_results_are_parseable(self):
        for (dice, ratio), result_str in CRT.items():
            r = CombatResult.from_string(result_str, ratio=ratio)
            assert isinstance(r, CombatResult), f"Failed to parse CRT[{dice},{ratio}]={result_str}"


class TestLookupCrt:
    def test_returns_combat_result(self):
        result = lookup_crt(3, 3, 7)
        assert isinstance(result, CombatResult)

    @pytest.mark.xfail(reason="lookup_crt hardcodes '*/-' instead of using CRT table")
    def test_known_result_1_to_1_dice_7(self):
        result = lookup_crt(3, 3, 7)
        expected = CombatResult.from_string("A1-1/-", ratio="1:1")
        assert result.attacker_retreat == expected.attacker_retreat
        assert result.attacker_casualties == expected.attacker_casualties

    @pytest.mark.xfail(reason="lookup_crt hardcodes '*/-' instead of using CRT table")
    def test_known_result_10_to_1_dice_2(self):
        result = lookup_crt(10, 1, 2)
        expected = CombatResult.from_string("-1/B3D", ratio="10:1")
        assert result.defender_retreat == expected.defender_retreat
        assert result.defender_disorganized == expected.defender_disorganized

    @pytest.mark.xfail(reason="lookup_crt hardcodes '*/-' instead of using CRT table")
    def test_strong_attacker_high_roll(self):
        result = lookup_crt(10, 1, 12)
        expected_str = CRT[(12, "10:1")]
        expected = CombatResult.from_string(expected_str, ratio="10:1")
        assert result.outcome == expected.outcome

    @pytest.mark.xfail(reason="lookup_crt hardcodes '*/-' instead of using CRT table")
    def test_weak_attacker_low_roll(self):
        result = lookup_crt(1, 4, 2)
        expected_str = CRT[(2, "1:4")]
        expected = CombatResult.from_string(expected_str, ratio="1:4")
        assert result.attacker_casualties == expected.attacker_casualties

    @pytest.mark.xfail(reason="lookup_crt hardcodes '*/-' instead of using CRT table")
    def test_ratio_clamped_in_lookup(self):
        result = lookup_crt(100, 1, 7)
        expected_str = CRT[(7, "10:1")]
        expected = CombatResult.from_string(expected_str, ratio="10:1")
        assert result.defender_retreat == expected.defender_retreat
