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
    disorganized: bool = False

    def with_position(self, pos: HexCoord) -> Unit:
        import dataclasses
        return dataclasses.replace(self, position=pos)

    def with_stats(self, **updates: Any) -> Unit:
        import dataclasses
        new_stats = {**self.stats, **updates}
        return dataclasses.replace(self, stats=new_stats)

    def with_disorganized(self, value: bool) -> Unit:
        import dataclasses
        return dataclasses.replace(self, disorganized=value)
