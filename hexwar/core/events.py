from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hexwar.core.battle import Side
from hexwar.core.combat_results import CombatResult
from hexwar.core.hex import HexCoord
from hexwar.core.unit import BattleId, Player, UnitId


@dataclass(frozen=True, slots=True)
class Event:
    pass


@dataclass(frozen=True, slots=True)
class UnitMoved(Event):
    unit_id: UnitId
    from_hex: HexCoord
    to_hex: HexCoord


@dataclass(frozen=True, slots=True)
class CombatResolved(Event):
    attacker_id: UnitId
    defender_id: UnitId
    result: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class UnitDestroyed(Event):
    unit_id: UnitId
    at_hex: HexCoord


@dataclass(frozen=True, slots=True)
class UnitEntrenched(Event):
    unit_id: UnitId
    at_hex: HexCoord


@dataclass(frozen=True, slots=True)
class PhaseChanged(Event):
    phase_id: str
    phase_name: str
    active_player: Player


@dataclass(frozen=True, slots=True)
class TurnChanged(Event):
    turn: int


@dataclass(frozen=True, slots=True)
class AttackDeclared(Event):
    battle_id: BattleId
    attacker_ids: tuple[UnitId, ...]
    defender_ids: tuple[UnitId, ...]
    attack_ratio: str


@dataclass(frozen=True, slots=True)
class AttackUndeclared(Event):
    battle_id: BattleId


@dataclass(frozen=True, slots=True)
class BattleResolved(Event):
    battle_id: BattleId
    attacker_ids: tuple[UnitId, ...]
    defender_ids: tuple[UnitId, ...]
    attack_strength: int
    defense_strength: int
    dice_roll: tuple[int, int]
    dice_total: int
    result: CombatResult
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return (
            f"Battle #{self.battle_id}: {self.attack_strength}v{self.defense_strength} "
            f"dice={self.dice_roll[0]}+{self.dice_roll[1]}={self.dice_total} → {self.result}"
        )


@dataclass(frozen=True, slots=True)
class RetreatSplitChosen(Event):
    battle_id: BattleId
    side: Side
    retreat_hexes: int
    unit_losses: int


@dataclass(frozen=True, slots=True)
class UnitLostCpl(Event):
    unit_id: UnitId
    battle_id: BattleId


@dataclass(frozen=True, slots=True)
class UnitRetreated(Event):
    unit_id: UnitId
    from_hex: HexCoord
    to_hex: HexCoord
    battle_id: BattleId


@dataclass(frozen=True, slots=True)
class UnitPursued(Event):
    unit_id: UnitId
    from_hex: HexCoord
    to_hex: HexCoord
    battle_id: BattleId


@dataclass(frozen=True, slots=True)
class UnitDisorganized(Event):
    unit_id: UnitId
    battle_id: BattleId


@dataclass(frozen=True, slots=True)
class DisorganizationRolled(Event):
    unit_id: UnitId
    battle_id: BattleId
    dice: tuple[int, int]
    total: int
    threshold: int
    became_disorganized: bool


@dataclass(frozen=True, slots=True)
class UnitReorganized(Event):
    unit_id: UnitId


@dataclass(frozen=True, slots=True)
class SMTagToggled(Event):
    unit_id: UnitId
    tagged: bool
