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
class ChooseRetreatSplitAction(Action):
    """Player decides how to split An/Bn between retreat and unit losses."""
    battle_id: int
    side: str                # "attacker" or "defender"
    retreat_hexes: int       # how many hexes to retreat
    unit_losses: int         # how many units to destroy instead


@dataclass(frozen=True, slots=True)
class AssignCplLossAction(Action):
    """Player picks which unit dies (1 CPL = destroyed)."""
    battle_id: int
    unit_id: UnitId


@dataclass(frozen=True, slots=True)
class RetreatUnitAction(Action):
    """Move one unit one hex during retreat."""
    battle_id: int
    unit_id: UnitId
    target: HexCoord


@dataclass(frozen=True, slots=True)
class PursuitAction(Action):
    """Move one unit one hex along retreat path."""
    battle_id: int
    unit_id: UnitId
    target: HexCoord


@dataclass(frozen=True, slots=True)
class SkipPursuitAction(Action):
    battle_id: int


@dataclass(frozen=True, slots=True)
class ResolveDisorgRollsAction(Action):
    """Trigger auto-resolution of all owed disorganization rolls for a battle."""
    battle_id: int


@dataclass(frozen=True, slots=True)
class DeclareStrategicMovementAction(Action):
    unit_id: UnitId


@dataclass(frozen=True, slots=True)
class StrategicMoveAction(Action):
    unit_id: UnitId
    target: HexCoord


@dataclass(frozen=True, slots=True)
class EndPhaseAction(Action):
    pass
