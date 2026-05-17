from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field

from hexwar.core.combat_results import CombatResult
from hexwar.core.hex import HexCoord
from hexwar.core.unit import BattleId, UnitId


class Side(enum.Enum):
    ATTACKER = "attacker"
    DEFENDER = "defender"

    def opposite(self) -> Side:
        return Side.DEFENDER if self is Side.ATTACKER else Side.ATTACKER


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


_SPLIT_PHASE: dict[Side, PostBattlePhase] = {
    Side.ATTACKER: PostBattlePhase.ATTACKER_SPLIT,
    Side.DEFENDER: PostBattlePhase.DEFENDER_SPLIT,
}
_CPL_PHASE: dict[Side, PostBattlePhase] = {
    Side.ATTACKER: PostBattlePhase.ATTACKER_CPL,
    Side.DEFENDER: PostBattlePhase.DEFENDER_CPL,
}
_RETREAT_PHASE: dict[Side, PostBattlePhase] = {
    Side.ATTACKER: PostBattlePhase.ATTACKER_RETREAT,
    Side.DEFENDER: PostBattlePhase.DEFENDER_RETREAT,
}


def split_phase_for(side: Side) -> PostBattlePhase:
    return _SPLIT_PHASE[side]


def cpl_phase_for(side: Side) -> PostBattlePhase:
    return _CPL_PHASE[side]


def retreat_phase_for(side: Side) -> PostBattlePhase:
    return _RETREAT_PHASE[side]


def side_of_phase(phase: PostBattlePhase) -> Side | None:
    """Return owning side for side-specific phases. None for shared phases."""
    if phase in (PostBattlePhase.ATTACKER_SPLIT, PostBattlePhase.ATTACKER_CPL, PostBattlePhase.ATTACKER_RETREAT):
        return Side.ATTACKER
    if phase in (PostBattlePhase.DEFENDER_SPLIT, PostBattlePhase.DEFENDER_CPL, PostBattlePhase.DEFENDER_RETREAT):
        return Side.DEFENDER
    return None


@dataclass(frozen=True, slots=True)
class Battle:
    id: BattleId
    attacker_ids: tuple[UnitId, ...]
    defender_hexes: tuple[HexCoord, ...]
    defender_ids: tuple[UnitId, ...]
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
    units_needing_retreat: tuple[UnitId, ...] = ()
    retreat_paths: dict[UnitId, tuple[HexCoord, ...]] = field(default_factory=dict)
    eliminated_at: dict[UnitId, HexCoord] = field(default_factory=dict)
    combatant_origin: dict[UnitId, HexCoord] = field(default_factory=dict)
    pursuing_side: Side | None = None
    units_pursued: tuple[UnitId, ...] = ()

    def replace(self, **kwargs) -> Battle:
        return dataclasses.replace(self, **kwargs)

    def units(self, side: Side) -> tuple[UnitId, ...]:
        return self.attacker_ids if side is Side.ATTACKER else self.defender_ids

    def debt(self, side: Side) -> int:
        return self.attacker_debt if side is Side.ATTACKER else self.defender_debt

    def mandatory_cpl(self, side: Side) -> int:
        return self.attacker_mandatory_cpl if side is Side.ATTACKER else self.defender_mandatory_cpl

    def with_debt(self, side: Side, n: int) -> Battle:
        if side is Side.ATTACKER:
            return self.replace(attacker_debt=n)
        return self.replace(defender_debt=n)

    def with_mandatory_cpl(self, side: Side, n: int) -> Battle:
        if side is Side.ATTACKER:
            return self.replace(attacker_mandatory_cpl=n)
        return self.replace(defender_mandatory_cpl=n)
