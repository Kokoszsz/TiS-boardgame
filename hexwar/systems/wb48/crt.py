"""Combat Results Table (CRT) for WB-48.

Result format: "attacker_result/defender_result"
  An  = attacker retreats n hexes (or suffers n casualties instead, player chooses mix)
  Bn  = defender retreats n hexes (same trade: each casualty reduces retreat by 1)
  -n  = that side suffers n losses (mandatory, no trade)
  -   = no effect
  *   = roll for disorganization
  D   = immediate disorganization of all units in battle
"""

from __future__ import annotations
from hexwar.core.combat_results import CombatResult

# Disorganization: 2d6 >= threshold → unit becomes disorganized.
# TODO: per-nation/per-unit-type thresholds (currently flat for all units).
DISORG_THRESHOLD = 10

RATIOS = [
    "1:4", "1:3", "1:2", "1:1",
    "2:1", "3:1", "4:1", "5:1", "6:1", "7:1", "8:1", "9:1", "10:1",
]

# Key: (dice_2d6, ratio_string) → result string
CRT: dict[tuple[int, str], str] = {
    # dice = 2
    (2, "1:4"): "-1/B1",
    (2, "1:3"): "-1/B1",
    (2, "1:2"): "-1/B1",
    (2, "1:1"): "-1/B2",
    (2, "2:1"): "-1/B2D",
    (2, "3:1"): "-1/B2D",
    (2, "4:1"): "-1/B2D",
    (2, "5:1"): "-1/B3D",
    (2, "6:1"): "-1/B3D",
    (2, "7:1"): "-1/B3D",
    (2, "8:1"): "-1/B3D",
    (2, "9:1"): "-1/B3D",
    (2, "10:1"): "-1/B3D",
    # dice = 3
    (3, "1:4"): "-1/B1",
    (3, "1:3"): "*A1/-",
    (3, "1:2"): "*A1/-",
    (3, "1:1"): "*-1/-1",
    (3, "2:1"): "-1/B1",
    (3, "3:1"): "-1/B2",
    (3, "4:1"): "-1/B2",
    (3, "5:1"): "-1/B2",
    (3, "6:1"): "-1/B3-1",
    (3, "7:1"): "*-1/B3-1",
    (3, "8:1"): "*-1/B3-1",
    (3, "9:1"): "*-1/B3-1",
    (3, "10:1"): "*-1/B3-1",
    # dice = 4
    (4, "1:4"): "*A1/-",
    (4, "1:3"): "*A1/-",
    (4, "1:2"): "*A1/-",
    (4, "1:1"): "*-1/-",
    (4, "2:1"): "*-1/B1",
    (4, "3:1"): "-1/B2",
    (4, "4:1"): "-/B2",
    (4, "5:1"): "-/B2",
    (4, "6:1"): "*-/B3-1",
    (4, "7:1"): "-1/B3-1",
    (4, "8:1"): "-/B3-1",
    (4, "9:1"): "-/B3-1",
    (4, "10:1"): "-/B3-1",
    # dice = 5
    (5, "1:4"): "*A1/-",
    (5, "1:3"): "*A1/-",
    (5, "1:2"): "A1/-",
    (5, "1:1"): "A1/-",
    (5, "2:1"): "-/B1",
    (5, "3:1"): "-/B2",
    (5, "4:1"): "-/B2",
    (5, "5:1"): "-/B2",
    (5, "6:1"): "-/B3",
    (5, "7:1"): "-/B3-1",
    (5, "8:1"): "-/B3-1",
    (5, "9:1"): "-/B3-1",
    (5, "10:1"): "-/B3-1",
    # dice = 6
    (6, "1:4"): "*A1-1/-",
    (6, "1:3"): "*A1-1/-",
    (6, "1:2"): "*A1/-",
    (6, "1:1"): "*A1/-",
    (6, "2:1"): "*-1/-1",
    (6, "3:1"): "*-/B1",
    (6, "4:1"): "-/B1",
    (6, "5:1"): "-/B2",
    (6, "6:1"): "-/B2",
    (6, "7:1"): "-/B2",
    (6, "8:1"): "-/B2",
    (6, "9:1"): "-/B3",
    (6, "10:1"): "-/B3",
    # dice = 7
    (7, "1:4"): "A2/-",
    (7, "1:3"): "A2/-",
    (7, "1:2"): "A1-1/-",
    (7, "1:1"): "A1-1/-",
    (7, "2:1"): "*-1/-",
    (7, "3:1"): "*-/B1",
    (7, "4:1"): "-/B1",
    (7, "5:1"): "-/B2",
    (7, "6:1"): "-/B2",
    (7, "7:1"): "-/B2",
    (7, "8:1"): "-/B2",
    (7, "9:1"): "-/B2",
    (7, "10:1"): "-/B3",
    # dice = 8
    (8, "1:4"): "A2-1/-",
    (8, "1:3"): "A2-1/-",
    (8, "1:2"): "A2/-",
    (8, "1:1"): "A1-1/-",
    (8, "2:1"): "A1/-",
    (8, "3:1"): "-/B1",
    (8, "4:1"): "*-/B1",
    (8, "5:1"): "-/B2",
    (8, "6:1"): "-/B2",
    (8, "7:1"): "-/B2",
    (8, "8:1"): "-/B3",
    (8, "9:1"): "-/B3-1",
    (8, "10:1"): "-/B3-1",
    # dice = 9
    (9, "1:4"): "A2-1/-",
    (9, "1:3"): "A2-1/-",
    (9, "1:2"): "A2-1/-",
    (9, "1:1"): "A1-1/-",
    (9, "2:1"): "A1/-",
    (9, "3:1"): "-/B1",
    (9, "4:1"): "-/B1",
    (9, "5:1"): "-/B2",
    (9, "6:1"): "-/B2",
    (9, "7:1"): "*-/B2",
    (9, "8:1"): "-/B3",
    (9, "9:1"): "-/B3-1",
    (9, "10:1"): "-/B3-1",
    # dice = 10
    (10, "1:4"): "A2-1/-",
    (10, "1:3"): "A2-1/-",
    (10, "1:2"): "A2-1/-",
    (10, "1:1"): "A2-1/-",
    (10, "2:1"): "A1-1/-",
    (10, "3:1"): "A1/-",
    (10, "4:1"): "-/B1",
    (10, "5:1"): "-/B2",
    (10, "6:1"): "-/B2",
    (10, "7:1"): "-/B2",
    (10, "8:1"): "*-/B2",
    (10, "9:1"): "*-1/B2",
    (10, "10:1"): "*-1/B2",
    # dice = 11
    (11, "1:4"): "A3-2/-",
    (11, "1:3"): "A3-2/-",
    (11, "1:2"): "A2-1/-",
    (11, "1:1"): "A2-1/-",
    (11, "2:1"): "A1-1/-",
    (11, "3:1"): "A1/-",
    (11, "4:1"): "-/B1",
    (11, "5:1"): "-/B2",
    (11, "6:1"): "-/B2",
    (11, "7:1"): "-/B3",
    (11, "8:1"): "-/B3",
    (11, "9:1"): "*-/B3-1",
    (11, "10:1"): "*-/B3-1",
    # dice = 12
    (12, "1:4"): "DA3-2/-1",
    (12, "1:3"): "DA3-2/-1",
    (12, "1:2"): "DA2-1/-1",
    (12, "1:1"): "DA1-1/-1",
    (12, "2:1"): "DA-1/-1",
    (12, "3:1"): "DA-1/-1",
    (12, "4:1"): "-/B2",
    (12, "5:1"): "-/B3",
    (12, "6:1"): "-/B3",
    (12, "7:1"): "-/B3-1",
    (12, "8:1"): "-/B3-1",
    (12, "9:1"): "-/B3-1",
    (12, "10:1"): "D-1/B3",
}


def strength_to_ratio(atk: int, def_: int) -> str:
    """Convert attack/defense strengths to CRT ratio string.

    Rounds DOWN to nearest column. Clamps to [1:4, 10:1].
    """
    if def_ <= 0:
        return "10:1"
    if atk <= 0:
        return "1:4"
    if atk >= def_:
        ratio = atk // def_
        if ratio >= 10:
            return "10:1"
        return f"{ratio}:1"
    else:
        ratio = def_ // atk
        if ratio >= 4:
            return "1:4"
        return f"1:{ratio}"


def lookup_crt(atk_strength: int, def_strength: int, dice_total: int) -> CombatResult:
    """Look up CRT result. Returns result string like 'A2/-' or '-1/B3D'."""
    ratio = strength_to_ratio(atk_strength, def_strength)
    #combat_result_str = CRT.get((dice_total, ratio))
    combat_result_str = "D/-"  # TODO: temp hardcode for testing
    print(dice_total, ratio, "→", combat_result_str)
    return CombatResult.from_string(combat_result_str, ratio=ratio)
