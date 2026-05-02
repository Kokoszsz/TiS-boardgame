from __future__ import annotations

from hexwar.core.actions import Action, AttackAction, EndPhaseAction, MoveAction
from hexwar.core.events import CombatResolved, Event, UnitDestroyed, UnitMoved
from hexwar.core.rng import GameRNG
from hexwar.core.state import GameState
from hexwar.core.unit import Player, UnitTypeDef
from hexwar.systems.base import PhaseDef, System

PLAYER_A = "player_a"
PLAYER_B = "player_b"


class TestSystem(System):
    name = "TestSystem"
    version = "0.1"

    def __init__(self):
        self.phases = [
            PhaseDef(id="move_a", name="Player A Movement", player=PLAYER_A,
                     allowed_actions=[MoveAction, EndPhaseAction]),
            PhaseDef(id="combat_a", name="Player A Combat", player=PLAYER_A,
                     allowed_actions=[AttackAction, EndPhaseAction]),
            PhaseDef(id="move_b", name="Player B Movement", player=PLAYER_B,
                     allowed_actions=[MoveAction, EndPhaseAction]),
            PhaseDef(id="combat_b", name="Player B Combat", player=PLAYER_B,
                     allowed_actions=[AttackAction, EndPhaseAction]),
        ]
        self.unit_types = {
            "infantry": UnitTypeDef(
                type_id="infantry", category="ground",
                stat_schema=["strength", "movement"],
            ),
            "tank": UnitTypeDef(
                type_id="tank", category="ground",
                stat_schema=["strength", "movement"],
            ),
        }

    def legal_actions(self, state: GameState, player: Player) -> list[Action]:
        phase = self.phases[state.phase_index]
        actions: list[Action] = []

        if MoveAction in phase.allowed_actions:
            for unit in state.units_of(player):
                move_range = unit.stats.get("movement", 1)
                reachable = unit.position.area(move_range)
                for target in reachable:
                    if target == unit.position:
                        continue
                    if target not in state.hex_map.all_coords():
                        continue
                    if not state.hex_map.is_passable(target):
                        continue
                    actions.append(MoveAction(player=player, unit_id=unit.id, target=target))

        if AttackAction in phase.allowed_actions:
            for unit in state.units_of(player):
                for nb in unit.position.neighbors():
                    enemies = [u for u in state.units_at(nb) if u.player != player]
                    for enemy in enemies:
                        actions.append(
                            AttackAction(player=player, attacker_id=unit.id, defender_id=enemy.id)
                        )

        return actions

    def apply_action(
        self, state: GameState, action: Action, rng: GameRNG
    ) -> tuple[GameState, list[Event]]:
        if isinstance(action, MoveAction):
            return self._apply_move(state, action)
        if isinstance(action, AttackAction):
            return self._apply_attack(state, action)
        return state, []

    def victory(self, state: GameState) -> Player | None:
        a_alive = any(u.player == PLAYER_A for u in state.units.values())
        b_alive = any(u.player == PLAYER_B for u in state.units.values())
        if a_alive and not b_alive:
            return PLAYER_A
        if b_alive and not a_alive:
            return PLAYER_B
        return None

    def _apply_move(
        self, state: GameState, action: MoveAction
    ) -> tuple[GameState, list[Event]]:
        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []
        old_pos = unit.position
        new_state = state.with_unit_moved(action.unit_id, action.target)
        return new_state, [UnitMoved(unit_id=action.unit_id, from_hex=old_pos, to_hex=action.target)]

    def _apply_attack(
        self, state: GameState, action: AttackAction
    ) -> tuple[GameState, list[Event]]:
        attacker = state.get_unit(action.attacker_id)
        defender = state.get_unit(action.defender_id)
        if attacker is None or defender is None:
            return state, []

        atk_str = attacker.stats.get("strength", 1)
        def_str = defender.stats.get("strength", 1)
        events: list[Event] = []

        if atk_str > def_str:
            result = "attacker_wins"
            new_state = state.with_unit_removed(action.defender_id)
            events.append(CombatResolved(
                attacker_id=action.attacker_id, defender_id=action.defender_id, result=result
            ))
            events.append(UnitDestroyed(unit_id=action.defender_id, at_hex=defender.position))
        elif def_str > atk_str:
            result = "defender_wins"
            new_state = state.with_unit_removed(action.attacker_id)
            events.append(CombatResolved(
                attacker_id=action.attacker_id, defender_id=action.defender_id, result=result
            ))
            events.append(UnitDestroyed(unit_id=action.attacker_id, at_hex=attacker.position))
        else:
            result = "tie"
            new_state = state
            events.append(CombatResolved(
                attacker_id=action.attacker_id, defender_id=action.defender_id, result=result
            ))

        return new_state, events
