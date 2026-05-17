"""Unit tests for HexCoord geometry methods."""
from __future__ import annotations

from hexwar.core.hex import HexCoord


class TestLineTo:
    def test_same_hex(self):
        h = HexCoord(2, 3)
        assert h.line_to(h) == [h]

    def test_adjacent_hex(self):
        a = HexCoord(0, 0)
        b = HexCoord(1, 0)
        path = a.line_to(b)
        assert path[0] == a
        assert path[-1] == b
        assert len(path) == 2

    def test_straight_line_east(self):
        a = HexCoord(0, 0)
        b = HexCoord(3, 0)
        path = a.line_to(b)
        assert len(path) == 4
        assert path == [HexCoord(0, 0), HexCoord(1, 0), HexCoord(2, 0), HexCoord(3, 0)]

    def test_diagonal_line(self):
        a = HexCoord(0, 0)
        b = HexCoord(0, 3)
        path = a.line_to(b)
        assert len(path) == 4
        assert path[0] == a
        assert path[-1] == b

    def test_includes_both_endpoints(self):
        a = HexCoord(1, 1)
        b = HexCoord(3, 2)
        path = a.line_to(b)
        assert path[0] == a
        assert path[-1] == b

    def test_all_hexes_adjacent(self):
        a = HexCoord(0, 0)
        b = HexCoord(3, 0)
        path = a.line_to(b)
        for i in range(len(path) - 1):
            assert path[i].distance(path[i + 1]) == 1


class TestRing:
    def test_radius_zero(self):
        h = HexCoord(2, 3)
        assert h.ring(0) == [h]

    def test_radius_one_count(self):
        h = HexCoord(0, 0)
        ring = h.ring(1)
        assert len(ring) == 6

    def test_radius_one_all_adjacent(self):
        h = HexCoord(0, 0)
        ring = h.ring(1)
        for coord in ring:
            assert h.distance(coord) == 1

    def test_radius_two_count(self):
        h = HexCoord(0, 0)
        ring = h.ring(2)
        assert len(ring) == 12

    def test_radius_two_all_at_distance(self):
        h = HexCoord(0, 0)
        ring = h.ring(2)
        for coord in ring:
            assert h.distance(coord) == 2

    def test_no_duplicates(self):
        h = HexCoord(0, 0)
        ring = h.ring(3)
        assert len(ring) == len(set(ring))


class TestArea:
    def test_radius_zero(self):
        h = HexCoord(2, 3)
        assert h.area(0) == {h}

    def test_radius_one_count(self):
        h = HexCoord(0, 0)
        area = h.area(1)
        assert len(area) == 7

    def test_radius_one_includes_center(self):
        h = HexCoord(0, 0)
        assert h in h.area(1)

    def test_radius_one_includes_all_neighbors(self):
        h = HexCoord(0, 0)
        area = h.area(1)
        for nb in h.neighbors():
            assert nb in area

    def test_radius_two_count(self):
        h = HexCoord(0, 0)
        area = h.area(2)
        assert len(area) == 19

    def test_all_within_distance(self):
        h = HexCoord(1, 1)
        r = 3
        area = h.area(r)
        for coord in area:
            assert h.distance(coord) <= r

    def test_non_origin_center(self):
        h = HexCoord(5, 5)
        area = h.area(1)
        assert len(area) == 7
        assert h in area
