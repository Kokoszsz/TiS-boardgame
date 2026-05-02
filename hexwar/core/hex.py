from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HexCoord:
    q: int
    r: int

    @property
    def s(self) -> int:
        return -self.q - self.r

    def neighbor(self, direction: int) -> HexCoord:
        dq, dr = _DIRECTIONS[direction % 6]
        return HexCoord(self.q + dq, self.r + dr)

    def neighbors(self) -> list[HexCoord]:
        return [self.neighbor(d) for d in range(6)]

    def distance(self, other: HexCoord) -> int:
        return max(
            abs(self.q - other.q),
            abs(self.r - other.r),
            abs(self.s - other.s),
        )

    def line_to(self, other: HexCoord) -> list[HexCoord]:
        n = self.distance(other)
        if n == 0:
            return [self]
        results: list[HexCoord] = []
        for i in range(n + 1):
            t = i / n
            fq = self.q + (other.q - self.q) * t
            fr = self.r + (other.r - self.r) * t
            results.append(_hex_round(fq, fr))
        return results

    def ring(self, radius: int) -> list[HexCoord]:
        if radius == 0:
            return [self]
        results: list[HexCoord] = []
        cur = HexCoord(self.q - radius, self.r + radius)
        for direction in range(6):
            for _ in range(radius):
                results.append(cur)
                cur = cur.neighbor(direction)
        return results

    def area(self, radius: int) -> set[HexCoord]:
        results: set[HexCoord] = set()
        for q in range(-radius, radius + 1):
            for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1):
                results.add(HexCoord(self.q + q, self.r + r))
        return results

    def __repr__(self) -> str:
        return f"Hex({self.q},{self.r})"


_DIRECTIONS = [
    (+1, 0),   # 0: East
    (+1, -1),  # 1: Northeast
    (0, -1),   # 2: Northwest
    (-1, 0),   # 3: West
    (-1, +1),  # 4: Southwest
    (0, +1),   # 5: Southeast
]


def _hex_round(fq: float, fr: float) -> HexCoord:
    fs = -fq - fr
    q = round(fq)
    r = round(fr)
    s = round(fs)
    q_diff = abs(q - fq)
    r_diff = abs(r - fr)
    s_diff = abs(s - fs)
    if q_diff > r_diff and q_diff > s_diff:
        q = -r - s
    elif r_diff > s_diff:
        r = -q - s
    return HexCoord(q, r)
