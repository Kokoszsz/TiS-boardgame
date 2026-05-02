from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hexwar.core.hex import HexCoord

UnitId = str
Player = str


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

    def with_position(self, pos: HexCoord) -> Unit:
        return Unit(
            id=self.id,
            name=self.name,
            type_id=self.type_id,
            player=self.player,
            position=pos,
            stats=self.stats,
        )

    def with_stats(self, **updates: Any) -> Unit:
        new_stats = {**self.stats, **updates}
        return Unit(
            id=self.id,
            name=self.name,
            type_id=self.type_id,
            player=self.player,
            position=self.position,
            stats=new_stats,
        )
