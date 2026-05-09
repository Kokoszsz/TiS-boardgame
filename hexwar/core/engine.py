from __future__ import annotations

from dataclasses import dataclass, field

from hexwar.core.actions import Action, EndPhaseAction
from hexwar.core.events import Event, PhaseChanged, TurnChanged
from hexwar.core.rng import GameRNG
from hexwar.core.state import GameState
from hexwar.core.unit import Player
from hexwar.systems.base import PhaseDef, System


@dataclass
class HistoryEntry:
    action: Action
    state_before: GameState
    state_after: GameState
    events: list[Event]


class Engine:
    def __init__(self, state: GameState, system: System, rng: GameRNG):
        self._state = state
        self._system = system
        self._rng = rng
        self._history: list[HistoryEntry] = []
        self._initial_state = state

    @property
    def state(self) -> GameState:
        return self._state

    @property
    def system(self) -> System:
        return self._system

    @property
    def current_phase(self) -> PhaseDef:
        return self._system.phases[self._state.phase_index]

    def get_legal_actions(self) -> list[Action]:
        return self._system.legal_actions(self._state, self._state.active_player)

    def submit_action(self, action: Action) -> list[Event]:
        if action.player != self._state.active_player:
            raise ValueError(
                f"Not {action.player}'s turn. Active: {self._state.active_player}"
            )

        state_before = self._state
        all_events: list[Event] = []

        if isinstance(action, EndPhaseAction):
            if self._system.should_advance_phase(self._state):
                events = self._advance_phase()
                all_events.extend(events)
            else:
                # System wants to handle EndPhaseAction itself (e.g. sub-phase transition)
                legal = self.get_legal_actions()
                if not any(self._actions_equal(action, la) for la in legal):
                    raise ValueError(f"Illegal action: {action}")
                new_state, events = self._system.apply_action(
                    self._state, action, self._rng
                )
                self._state = new_state
                all_events.extend(events)
        else:
            legal = self.get_legal_actions()
            if not any(self._actions_equal(action, la) for la in legal):
                raise ValueError(f"Illegal action: {action}")
            new_state, events = self._system.apply_action(
                self._state, action, self._rng
            )
            self._state = new_state
            all_events.extend(events)

        self._history.append(
            HistoryEntry(
                action=action,
                state_before=state_before,
                state_after=self._state,
                events=all_events,
            )
        )

        winner = self._system.victory(self._state)
        if winner is not None:
            all_events.append(
                PhaseChanged(phase_id="game_over", phase_name="Game Over", active_player=winner)
            )

        return all_events

    def undo(self) -> GameState | None:
        if not self._history:
            return None
        entry = self._history.pop()
        self._state = entry.state_before
        return self._state

    def get_history(self) -> list[HistoryEntry]:
        return list(self._history)

    def _advance_phase(self) -> list[Event]:
        events: list[Event] = []

        phase = self.current_phase
        exit_state, exit_events = self._system.on_phase_exit(self._state, phase)
        self._state = exit_state
        events.extend(exit_events)

        next_index = self._state.phase_index + 1

        if next_index >= len(self._system.phases):
            next_index = 0
            new_turn = self._state.turn + 1
            self._state = self._state.with_turn(new_turn)
            events.append(TurnChanged(turn=new_turn))

            turn_state, turn_events = self._system.on_turn_start(self._state)
            self._state = turn_state
            events.extend(turn_events)

        new_phase = self._system.phases[next_index]
        self._state = self._state.with_phase(next_index, new_phase.player)

        enter_state, enter_events = self._system.on_phase_enter(self._state, new_phase)
        self._state = enter_state
        events.extend(enter_events)

        events.append(
            PhaseChanged(
                phase_id=new_phase.id,
                phase_name=new_phase.name,
                active_player=new_phase.player,
            )
        )

        return events

    @staticmethod
    def _actions_equal(a: Action, b: Action) -> bool:
        return a == b
