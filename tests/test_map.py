"""Unit tests for HexMap methods."""
from __future__ import annotations

from hexwar.core.hex import HexCoord
from hexwar.core.map import EdgeFeature, EdgeType, HexMap, TerrainLayer, TerrainType


class TestHasRiver:
    def test_river_detected(self):
        m = HexMap()
        a, b = HexCoord(0, 0), HexCoord(1, 0)
        m.set_edge(a, b, [EdgeFeature(EdgeType.RIVER)])
        assert m.has_river(a, b) is True

    def test_no_river(self):
        m = HexMap()
        a, b = HexCoord(0, 0), HexCoord(1, 0)
        assert m.has_river(a, b) is False

    def test_road_is_not_river(self):
        m = HexMap()
        a, b = HexCoord(0, 0), HexCoord(1, 0)
        m.set_edge(a, b, [EdgeFeature(EdgeType.ROAD)])
        assert m.has_river(a, b) is False

    def test_river_symmetric(self):
        m = HexMap()
        a, b = HexCoord(0, 0), HexCoord(1, 0)
        m.set_edge(a, b, [EdgeFeature(EdgeType.RIVER)])
        assert m.has_river(b, a) is True

    def test_multiple_features_river_present(self):
        m = HexMap()
        a, b = HexCoord(0, 0), HexCoord(1, 0)
        m.set_edge(a, b, [EdgeFeature(EdgeType.ROAD), EdgeFeature(EdgeType.RIVER)])
        assert m.has_river(a, b) is True
        assert m.has_road(a, b) is True


class TestRoadConnections:
    def test_no_roads(self):
        m = HexMap()
        m.set_terrain(HexCoord(0, 0), [TerrainLayer(TerrainType.PLAIN)])
        assert m.road_connections(HexCoord(0, 0)) == []

    def test_single_road(self):
        m = HexMap()
        a, b = HexCoord(0, 0), HexCoord(1, 0)
        m.set_edge(a, b, [EdgeFeature(EdgeType.ROAD)])
        conns = m.road_connections(a)
        assert b in conns

    def test_multiple_roads(self):
        m = HexMap()
        center = HexCoord(2, 2)
        nb1 = HexCoord(3, 2)
        nb2 = HexCoord(2, 3)
        m.set_edge(center, nb1, [EdgeFeature(EdgeType.ROAD)])
        m.set_edge(center, nb2, [EdgeFeature(EdgeType.ROAD)])
        conns = m.road_connections(center)
        assert nb1 in conns
        assert nb2 in conns
        assert len(conns) == 2

    def test_river_not_in_road_connections(self):
        m = HexMap()
        a, b = HexCoord(0, 0), HexCoord(1, 0)
        m.set_edge(a, b, [EdgeFeature(EdgeType.RIVER)])
        assert m.road_connections(a) == []
