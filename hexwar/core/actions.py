from __future__ import annotations

from dataclasses import dataclass

from hexwar.core.hex import HexCoord
from hexwar.core.unit import Player, UnitId


@dataclass(frozen=True, slots=True)
class Action:
    player: Player


@dataclass(frozen=True, slots=True)
class MoveAction(Action):
    unit_id: UnitId
    target: HexCoord


@dataclass(frozen=True, slots=True)
class AttackAction(Action):
    attacker_id: UnitId
    defender_id: UnitId


@dataclass(frozen=True, slots=True)
class EntrenchAction(Action):
    unit_id: UnitId


@dataclass(frozen=True, slots=True)
class DeclareAttackAction(Action):
    attacker_ids: tuple[UnitId, ...]
    defender_hexes: tuple[HexCoord, ...]


@dataclass(frozen=True, slots=True)
class UndeclareAttackAction(Action):
    battle_id: int


@dataclass(frozen=True, slots=True)
class ResolveBattleAction(Action):
    battle_id: int


@dataclass(frozen=True, slots=True)
class EndPhaseAction(Action):
    pass
