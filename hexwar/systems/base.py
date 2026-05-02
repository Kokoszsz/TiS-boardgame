from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from hexwar.core.actions import Action
from hexwar.core.events import Event
from hexwar.core.rng import GameRNG
from hexwar.core.state import GameState
from hexwar.core.unit import Player, UnitTypeDef


@dataclass(frozen=True, slots=True)
class PhaseDef:
    id: str
    name: str
    player: Player
    allowed_actions: list[type] = field(default_factory=list)
    auto_advance: bool = False


class System(ABC):
    name: str
    version: str
    phases: list[PhaseDef]
    unit_types: dict[str, UnitTypeDef]

    @abstractmethod
    def legal_actions(self, state: GameState, player: Player) -> list[Action]:
        ...

    @abstractmethod
    def apply_action(
        self, state: GameState, action: Action, rng: GameRNG
    ) -> tuple[GameState, list[Event]]:
        ...

    @abstractmethod
    def victory(self, state: GameState) -> Player | None:
        ...

    def on_phase_enter(
        self, state: GameState, phase: PhaseDef
    ) -> tuple[GameState, list[Event]]:
        return state, []

    def on_phase_exit(
        self, state: GameState, phase: PhaseDef
    ) -> tuple[GameState, list[Event]]:
        return state, []

    def on_turn_start(
        self, state: GameState
    ) -> tuple[GameState, list[Event]]:
        return state, []
