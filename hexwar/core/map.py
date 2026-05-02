from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from hexwar.core.hex import HexCoord


class TerrainType(Enum):
    PLAIN = "plain"
    FOREST = "forest"
    HILL = "hill"
    CITY = "city"
    SWAMP = "swamp"
    MOUNTAIN = "mountain"
    WATER = "water"


class EdgeType(Enum):
    ROAD = "road"
    RAILWAY = "railway"
    RIVER = "river"
    BRIDGE = "bridge"


@dataclass(frozen=True, slots=True)
class TerrainLayer:
    type: TerrainType


@dataclass(frozen=True, slots=True)
class EdgeFeature:
    type: EdgeType


def _edge_key(a: HexCoord, b: HexCoord) -> frozenset[HexCoord]:
    return frozenset((a, b))


@dataclass
class HexMap:
    terrain: dict[HexCoord, list[TerrainLayer]] = field(default_factory=dict)
    edges: dict[frozenset[HexCoord], list[EdgeFeature]] = field(default_factory=dict)

    def set_terrain(self, coord: HexCoord, layers: list[TerrainLayer]) -> None:
        self.terrain[coord] = layers

    def get_terrain(self, coord: HexCoord) -> list[TerrainLayer]:
        return self.terrain.get(coord, [])

    def has_terrain_type(self, coord: HexCoord, t: TerrainType) -> bool:
        return any(layer.type == t for layer in self.get_terrain(coord))

    def set_edge(self, a: HexCoord, b: HexCoord, features: list[EdgeFeature]) -> None:
        self.edges[_edge_key(a, b)] = features

    def get_edge(self, a: HexCoord, b: HexCoord) -> list[EdgeFeature]:
        return self.edges.get(_edge_key(a, b), [])

    def has_road(self, a: HexCoord, b: HexCoord) -> bool:
        return any(f.type == EdgeType.ROAD for f in self.get_edge(a, b))

    def has_river(self, a: HexCoord, b: HexCoord) -> bool:
        return any(f.type == EdgeType.RIVER for f in self.get_edge(a, b))

    def is_passable(self, coord: HexCoord) -> bool:
        layers = self.get_terrain(coord)
        if not layers:
            return coord in self.terrain
        return not any(layer.type == TerrainType.WATER for layer in layers)

    def all_coords(self) -> set[HexCoord]:
        return set(self.terrain.keys())

    def road_connections(self, coord: HexCoord) -> list[HexCoord]:
        result = []
        for nb in coord.neighbors():
            if self.has_road(coord, nb):
                result.append(nb)
        return result
