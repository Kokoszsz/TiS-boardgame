from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field

from hexwar.core.combat_results import CombatResult
from hexwar.core.hex import HexCoord


class PostBattlePhase(enum.Enum):
    ATTACKER_SPLIT = "attacker_split"
    ATTACKER_CPL = "attacker_cpl"
    ATTACKER_RETREAT = "attacker_retreat"
    DEFENDER_SPLIT = "defender_split"
    DEFENDER_CPL = "defender_cpl"
    DEFENDER_RETREAT = "defender_retreat"
    MANDATORY_CPL = "mandatory_cpl"
    DISORG_ROLLS = "disorg_rolls"
    PURSUIT = "pursuit"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class Battle:
    id: int
    attacker_ids: tuple[str, ...]
    defender_hexes: tuple[HexCoord, ...]
    defender_ids: tuple[str, ...]
    resolved: bool = False
    result: CombatResult | None = None
    dice_roll: tuple[int, int] | None = None
    post_phase: PostBattlePhase = PostBattlePhase.DONE
    attacker_debt: int = 0
    defender_debt: int = 0
    attacker_mandatory_cpl: int = 0
    defender_mandatory_cpl: int = 0
    remaining_cpl_to_assign: int = 0
    remaining_retreat_steps: int = 0
    units_needing_retreat: tuple[str, ...] = ()
    retreat_paths: dict[str, tuple[HexCoord, ...]] = field(default_factory=dict)
    eliminated_at: dict[str, HexCoord] = field(default_factory=dict)
    combatant_origin: dict[str, HexCoord] = field(default_factory=dict)
    pursuing_side: str = ""
    units_pursued: tuple[str, ...] = ()

    def replace(self, **kwargs) -> Battle:
        return dataclasses.replace(self, **kwargs)
