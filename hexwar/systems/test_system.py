from __future__ import annotations

from hexwar.core.actions import Action, AttackAction, EndPhaseAction, EntrenchAction, MoveAction
from hexwar.core.events import CombatResolved, Event, UnitDestroyed, UnitEntrenched, UnitMoved
from hexwar.core.hex import HexCoord
from hexwar.core.map import TerrainType
from hexwar.core.pathfinding import reachable_hexes
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
                     allowed_actions=[MoveAction, EntrenchAction, EndPhaseAction]),
            PhaseDef(id="combat_a", name="Player A Combat", player=PLAYER_A,
                     allowed_actions=[AttackAction, EndPhaseAction]),
            PhaseDef(id="move_b", name="Player B Movement", player=PLAYER_B,
                     allowed_actions=[MoveAction, EntrenchAction, EndPhaseAction]),
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

    STACK_LIMIT = 6
    ZOC_UNIT_TYPES = {"infantry", "tank"}

    TERRAIN_COSTS: dict[TerrainType, float] = {
        TerrainType.PLAIN: 1,
        TerrainType.FOREST: 2,
        TerrainType.HILL: 2,
        TerrainType.CITY: 1,
        TerrainType.SWAMP: 3,
        TerrainType.MOUNTAIN: None,
        TerrainType.WATER: None,
    }

    def _movement_cost(self, state: GameState, from_hex: HexCoord, to_hex: HexCoord) -> float | None:
        if to_hex not in state.hex_map.all_coords():
            return None
        layers = state.hex_map.get_terrain(to_hex)
        if not layers:
            return None
        costs = [self.TERRAIN_COSTS.get(layer.type, 1) for layer in layers]
        if any(c is None for c in costs):
            return None
        cost = max(costs)
        if state.hex_map.has_road(from_hex, to_hex):
            cost = min(cost, 1)
        return cost

    def _is_blocked(self, state: GameState, coord: HexCoord) -> bool:
        return not state.hex_map.is_passable(coord)

    def _enemy_zoc_map(self, state: GameState, player: Player) -> dict[HexCoord, set[str]]:
        zoc: dict[HexCoord, set[str]] = {}
        for unit in state.units.values():
            if unit.player == player:
                continue
            if unit.type_id not in self.ZOC_UNIT_TYPES:
                continue
            for nb in unit.position.neighbors():
                zoc.setdefault(nb, set()).add(unit.id)
        return zoc

    def _movement_cost_with_zoc(
        self, state: GameState, from_hex: HexCoord, to_hex: HexCoord,
        player: Player, zoc_map: dict[HexCoord, set[str]],
    ) -> float | None:
        base_cost = self._movement_cost(state, from_hex, to_hex)
        if base_cost is None:
            return None
        from_sources = zoc_map.get(from_hex, set())
        to_sources = zoc_map.get(to_hex, set())
        if from_sources & to_sources:
            return None
        if to_sources:
            return float('inf')
        return base_cost

    def legal_actions(self, state: GameState, player: Player) -> list[Action]:
        phase = self.phases[state.phase_index]
        actions: list[Action] = []

        if MoveAction in phase.allowed_actions:
            remaining_mp = state.metadata.get("remaining_mp", {})
            zoc_map = self._enemy_zoc_map(state, player)
            for unit in state.units_of(player):
                base_mp = unit.stats.get("movement", 1)
                move_range = remaining_mp.get(unit.id, base_mp)
                if move_range <= 0:
                    continue
                already_moved = unit.id in remaining_mp
                cost_fn = lambda f, t: self._movement_cost_with_zoc(
                    state, f, t, player, zoc_map,
                )
                blocked_fn = lambda c: (
                    self._is_blocked(state, c)
                    or any(u.player != player for u in state.units_at(c))
                )
                reachable = reachable_hexes(
                    unit.position, move_range, cost_fn, blocked_fn,
                    allow_first_step_overrun=not already_moved,
                )
                for target in reachable:
                    units_there = state.units_at(target)
                    enemies = [u for u in units_there if u.player != player]
                    if enemies:
                        continue
                    friendly_stack = sum(
                        u.stats.get("stack_size", 1) for u in units_there if u.player == player
                    )
                    unit_stack = unit.stats.get("stack_size", 1)
                    if friendly_stack + unit_stack > self.STACK_LIMIT:
                        continue
                    actions.append(MoveAction(player=player, unit_id=unit.id, target=target))

        if EntrenchAction in phase.allowed_actions:
            remaining_mp = state.metadata.get("remaining_mp", {})
            entrenched_hexes = state.metadata.get("entrenched", {})
            for unit in state.units_of(player):
                if unit.id in remaining_mp:
                    continue
                if unit.position in entrenched_hexes:
                    continue
                terrain = state.hex_map.get_terrain(unit.position)
                if terrain and any(layer.type == TerrainType.SWAMP for layer in terrain):
                    continue
                actions.append(EntrenchAction(player=player, unit_id=unit.id))

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
        if isinstance(action, EntrenchAction):
            return self._apply_entrench(state, action)
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

    def on_phase_enter(
        self, state: GameState, phase: PhaseDef
    ) -> tuple[GameState, list[Event]]:
        return state.with_metadata("remaining_mp", {}), []

    def _apply_move(
        self, state: GameState, action: MoveAction
    ) -> tuple[GameState, list[Event]]:
        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []
        old_pos = unit.position
        player = unit.player

        remaining_mp = state.metadata.get("remaining_mp", {})
        base_mp = unit.stats.get("movement", 1)
        current_mp = remaining_mp.get(unit.id, base_mp)
        already_moved = unit.id in remaining_mp

        zoc_map = self._enemy_zoc_map(state, player)
        cost_fn = lambda f, t: self._movement_cost_with_zoc(state, f, t, player, zoc_map)
        blocked_fn = lambda c: self._is_blocked(state, c)
        reachable = reachable_hexes(
            old_pos, current_mp, cost_fn, blocked_fn,
            allow_first_step_overrun=not already_moved,
        )
        new_mp = reachable.get(action.target, 0)

        new_state = state.with_unit_moved(action.unit_id, action.target)
        new_remaining = {**new_state.metadata.get("remaining_mp", {}), action.unit_id: new_mp}
        new_state = new_state.with_metadata("remaining_mp", new_remaining)

        entrenched = dict(new_state.metadata.get("entrenched", {}))
        if action.target in entrenched and entrenched[action.target] != player:
            del entrenched[action.target]
            new_state = new_state.with_metadata("entrenched", entrenched)
        if old_pos in entrenched and entrenched[old_pos] == player:
            friendly_left = any(u.player == player for u in new_state.units_at(old_pos))
            if not friendly_left:
                del entrenched[old_pos]
                new_state = new_state.with_metadata("entrenched", entrenched)

        return new_state, [UnitMoved(unit_id=action.unit_id, from_hex=old_pos, to_hex=action.target)]

    def _apply_entrench(
        self, state: GameState, action: EntrenchAction
    ) -> tuple[GameState, list[Event]]:
        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []
        entrenched = dict(state.metadata.get("entrenched", {}))
        entrenched[unit.position] = unit.player
        new_state = state.with_metadata("entrenched", entrenched)
        remaining_mp = {**new_state.metadata.get("remaining_mp", {}), action.unit_id: 0}
        new_state = new_state.with_metadata("remaining_mp", remaining_mp)
        return new_state, [UnitEntrenched(unit_id=action.unit_id, at_hex=unit.position)]

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
