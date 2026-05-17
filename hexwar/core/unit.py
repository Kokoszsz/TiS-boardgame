from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, NewType

from hexwar.core.hex import HexCoord

UnitId = NewType("UnitId", str)
Player = NewType("Player", str)
BattleId = NewType("BattleId", int)


@dataclass(frozen=True, slots=True)
class UnitTypeDef:
    type_id: str
    category: str
    stat_schema: list[str]
    display_info: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Unit:
    id: UnitId
    name: str
    type_id: str
    player: Player
    position: HexCoord
    stats: dict[str, Any] = field(default_factory=dict)
    movement_max: float = 1.0
    movement_left: float = 0.0
    disorganized: bool = False
    last_active_turn: int = 0
    strategic_movement: bool = False

    def with_position(self, pos: HexCoord) -> Unit:
        return dataclasses.replace(self, position=pos)

    def with_stats(self, **updates: Any) -> Unit:
        new_stats = {**self.stats, **updates}
        return dataclasses.replace(self, stats=new_stats)

    def with_disorganized(self, value: bool) -> Unit:
        return dataclasses.replace(self, disorganized=value)

    def with_last_active_turn(self, turn: int) -> Unit:
        return dataclasses.replace(self, last_active_turn=turn)

    def with_movement_left(self, mp: float) -> Unit:
        return dataclasses.replace(self, movement_left=mp)

    def with_movement_max(self, mp: float) -> Unit:
        return dataclasses.replace(self, movement_max=mp)

    def with_strategic_movement(self, value: bool) -> Unit:
        return dataclasses.replace(self, movement_left=0, strategic_movement=value)
