from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hexwar.core.hex import HexCoord
from hexwar.core.map import HexMap
from hexwar.core.unit import Player, Unit, UnitId


@dataclass(frozen=True)
class GameState:
    scenario_id: str
    scenario_name: str
    system_id: str
    hex_map: HexMap
    units: dict[UnitId, Unit] = field(default_factory=dict)
    units_by_hex: dict[HexCoord, tuple[UnitId, ...]] = field(default_factory=dict)
    turn: int = 1
    phase_index: int = 0
    active_player: Player = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_unit(self, unit_id: UnitId) -> Unit | None:
        return self.units.get(unit_id)

    def units_at(self, coord: HexCoord) -> list[Unit]:
        ids = self.units_by_hex.get(coord, ())
        return [self.units[uid] for uid in ids if uid in self.units]

    def units_of(self, player: Player) -> list[Unit]:
        return [u for u in self.units.values() if u.player == player]

    def with_unit_moved(self, unit_id: UnitId, new_pos: HexCoord) -> GameState:
        unit = self.units[unit_id]
        old_pos = unit.position
        new_unit = unit.with_position(new_pos)

        new_units = {**self.units, unit_id: new_unit}

        new_by_hex = dict(self.units_by_hex)
        old_list = tuple(uid for uid in new_by_hex.get(old_pos, ()) if uid != unit_id)
        if old_list:
            new_by_hex[old_pos] = old_list
        else:
            new_by_hex.pop(old_pos, None)
        new_by_hex[new_pos] = new_by_hex.get(new_pos, ()) + (unit_id,)

        return GameState(
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            system_id=self.system_id,
            hex_map=self.hex_map,
            units=new_units,
            units_by_hex=new_by_hex,
            turn=self.turn,
            phase_index=self.phase_index,
            active_player=self.active_player,
            metadata=self.metadata,
        )

    def with_unit_removed(self, unit_id: UnitId) -> GameState:
        unit = self.units[unit_id]
        pos = unit.position

        new_units = {uid: u for uid, u in self.units.items() if uid != unit_id}

        new_by_hex = dict(self.units_by_hex)
        remaining = tuple(uid for uid in new_by_hex.get(pos, ()) if uid != unit_id)
        if remaining:
            new_by_hex[pos] = remaining
        else:
            new_by_hex.pop(pos, None)

        return GameState(
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            system_id=self.system_id,
            hex_map=self.hex_map,
            units=new_units,
            units_by_hex=new_by_hex,
            turn=self.turn,
            phase_index=self.phase_index,
            active_player=self.active_player,
            metadata=self.metadata,
        )

    def with_phase(self, phase_index: int, active_player: Player) -> GameState:
        return GameState(
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            system_id=self.system_id,
            hex_map=self.hex_map,
            units=self.units,
            units_by_hex=self.units_by_hex,
            turn=self.turn,
            phase_index=phase_index,
            active_player=active_player,
            metadata=self.metadata,
        )

    def with_turn(self, turn: int) -> GameState:
        return GameState(
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            system_id=self.system_id,
            hex_map=self.hex_map,
            units=self.units,
            units_by_hex=self.units_by_hex,
            turn=turn,
            phase_index=self.phase_index,
            active_player=self.active_player,
            metadata=self.metadata,
        )

    def with_metadata(self, key: str, value: Any) -> GameState:
        new_metadata = {**self.metadata, key: value}
        return GameState(
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            system_id=self.system_id,
            hex_map=self.hex_map,
            units=self.units,
            units_by_hex=self.units_by_hex,
            turn=self.turn,
            phase_index=self.phase_index,
            active_player=self.active_player,
            metadata=new_metadata,
        )

    def with_unit_stats(self, unit_id: UnitId, **updates) -> GameState:
        unit = self.units[unit_id]
        new_unit = unit.with_stats(**updates)
        new_units = {**self.units, unit_id: new_unit}
        return GameState(
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            system_id=self.system_id,
            hex_map=self.hex_map,
            units=new_units,
            units_by_hex=self.units_by_hex,
            turn=self.turn,
            phase_index=self.phase_index,
            active_player=self.active_player,
            metadata=self.metadata,
        )


def build_initial_state(
    scenario_id: str,
    scenario_name: str,
    system_id: str,
    hex_map: HexMap,
    units: list[Unit],
    active_player: Player,
) -> GameState:
    units_dict = {u.id: u for u in units}
    by_hex: dict[HexCoord, tuple[UnitId, ...]] = {}
    for u in units:
        by_hex[u.position] = by_hex.get(u.position, ()) + (u.id,)

    return GameState(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        system_id=system_id,
        hex_map=hex_map,
        units=units_dict,
        units_by_hex=by_hex,
        turn=1,
        phase_index=0,
        active_player=active_player,
    )
