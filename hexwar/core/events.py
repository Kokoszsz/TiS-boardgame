from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hexwar.core.hex import HexCoord
from hexwar.core.unit import Player, UnitId


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
class PhaseChanged(Event):
    phase_id: str
    phase_name: str
    active_player: Player


@dataclass(frozen=True, slots=True)
class TurnChanged(Event):
    turn: int
