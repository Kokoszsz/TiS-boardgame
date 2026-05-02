from __future__ import annotations

import random


class GameRNG:
    def __init__(self, seed: int = 0):
        self._seed = seed
        self._rng = random.Random(seed)

    @property
    def seed(self) -> int:
        return self._seed

    def roll_d6(self) -> int:
        return self._rng.randint(1, 6)

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        return [self._rng.randint(1, sides) for _ in range(count)]

    def get_state(self) -> tuple:
        return self._rng.getstate()

    def set_state(self, state: tuple) -> None:
        self._rng.setstate(state)
