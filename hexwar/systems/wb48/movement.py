from __future__ import annotations

from hexwar.core.actions import DeclareStrategicMovementAction, EntrenchAction, MoveAction, StrategicMoveAction
from hexwar.core.events import Event, SMTagToggled, UnitEntrenched, UnitMoved
from hexwar.core.hex import HexCoord
from hexwar.core.map import TerrainType
from hexwar.core.pathfinding import reachable_hexes
from hexwar.core.state import GameState
from hexwar.core.unit import Player


class MovementMixin:
    STACK_LIMIT: int
    ZOC_UNIT_TYPES: set[str]
    TERRAIN_COSTS: dict[TerrainType, float | None]

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

    def enemy_zoc_map(self, state: GameState, player: Player) -> dict[HexCoord, set[str]]:
        zoc: dict[HexCoord, set[str]] = {}
        for unit in state.units.values():
            if unit.player == player:
                continue
            if unit.type_id not in self.ZOC_UNIT_TYPES:
                continue
            zoc.setdefault(unit.position, set()).add(unit.id)
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
        if from_sources:
            return base_cost + 1
        return base_cost
    
    def _move_targets_for_unit(
        self, state, player, unit, mp, *,
        allow_overrun: bool, block_zoc_entry: bool = False,
    ) -> list[HexCoord]:
        """Compute legal move targets for one unit with given MP + overrun rule.

        block_zoc_entry: if True, ZOC entry is impassable (rule 11.22 for SM).
            Default False keeps the standard "ZOC entry consumes all MP" rule.
        """
        if mp <= 0:
            return []
        zoc_map = self.enemy_zoc_map(state, player)
        base_cost_fn = lambda f, t: self._movement_cost_with_zoc(state, f, t, player, zoc_map)
        if block_zoc_entry:
            def cost_fn(f, t):
                c = base_cost_fn(f, t)
                return None if c == float('inf') else c
        else:
            cost_fn = base_cost_fn
        blocked_fn = lambda c: (
            self._is_blocked(state, c)
            or any(u.player != player for u in state.units_at(c))
        )
        reachable = reachable_hexes(
            unit.position, mp, cost_fn, blocked_fn,
            allow_first_step_overrun=allow_overrun,
        )
        valid = []
        unit_stack = unit.stats.get("stack_size", 1)
        for target in reachable:
            units_there = state.units_at(target)
            if any(u.player != player for u in units_there):
                continue
            friendly_stack = sum(
                u.stats.get("stack_size", 1) for u in units_there if u.player == player
            )
            if friendly_stack + unit_stack > self.STACK_LIMIT:
                continue
            valid.append(target)
        return valid


    def _legal_move_actions(self, state: GameState, player: Player) -> list[MoveAction]:
        actions: list[MoveAction] = []
        for unit in state.units_of(player):
            already_moved = unit.movement_left < unit.movement_max
            targets = self._move_targets_for_unit(
                state, player, unit, unit.movement_left,
                allow_overrun=not already_moved,
            )
            actions.extend(MoveAction(player=player, unit_id=unit.id, target=t) for t in targets)
        return actions



    def _legal_entrench_actions(self, state: GameState, player: Player) -> list[EntrenchAction]:
        actions: list[EntrenchAction] = []
        entrenched_hexes = state.metadata.get("entrenched", {})
        for unit in state.units_of(player):
            if unit.movement_left < unit.movement_max:
                continue
            if unit.position in entrenched_hexes:
                continue
            terrain = state.hex_map.get_terrain(unit.position)
            if terrain and any(layer.type == TerrainType.SWAMP for layer in terrain):
                continue
            actions.append(EntrenchAction(player=player, unit_id=unit.id))
        return actions

    def _apply_move(
        self, state: GameState, action: MoveAction
    ) -> tuple[GameState, list[Event]]:
        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []
        old_pos = unit.position
        player = unit.player

        current_mp = unit.movement_left
        already_moved = unit.movement_left < unit.movement_max

        zoc_map = self.enemy_zoc_map(state, player)
        cost_fn = lambda f, t: self._movement_cost_with_zoc(state, f, t, player, zoc_map)
        blocked_fn = lambda c: self._is_blocked(state, c)
        reachable = reachable_hexes(
            old_pos, current_mp, cost_fn, blocked_fn,
            allow_first_step_overrun=not already_moved,
        )
        new_mp = reachable.get(action.target, 0)

        new_state = state.with_unit_moved(action.unit_id, action.target)
        moved_unit = new_state.get_unit(action.unit_id).with_movement_left(new_mp)
        new_state = new_state.with_unit(moved_unit)

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
        new_state = new_state.with_unit(unit.with_movement_left(0))
        return new_state, [UnitEntrenched(unit_id=action.unit_id, at_hex=unit.position)]
    
    def _legal_declare_sm_actions(
        self, state: GameState, player: Player,
    ) -> list[DeclareStrategicMovementAction]:
        """Units eligible for SM tagging: own, unmoved/un-entrenched, not in enemy ZOC.

        Per rule 11.12. Toggle action — always offered for eligible units
        (player may tag or untag).
        """
        actions: list[DeclareStrategicMovementAction] = []
        zoc_map = self.enemy_zoc_map(state, player)
        for unit in state.units_of(player):
            # Already-tagged units stay tagged-toggleable, even if zero MP.
            # For untagged units: require full MP (proxy for "did not move/entrench").
            if not unit.strategic_movement:
                if unit.movement_left < unit.movement_max:
                    continue
                if unit.position in zoc_map:
                    continue
            actions.append(DeclareStrategicMovementAction(
                player=player, unit_id=unit.id,
            ))
        return actions

    def _declare_strategic_movement(
        self, state: GameState, action: DeclareStrategicMovementAction,
    ) -> tuple[GameState, list[Event]]:
        """Toggle SM tag on unit. Engine guarantees action was in legal set.

        Does NOT touch movement_left — tagging is a flag, not movement.
        Tagged unit stays at full MP through movement phase (proxy for
        "did not move"), then gets MP-2 budget in SM phase.
        """
        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []
        new_unit = unit.with_strategic_movement(not unit.strategic_movement)
        new_state = state.with_unit(new_unit)
        return new_state, [SMTagToggled(
            unit_id=action.unit_id, tagged=new_unit.strategic_movement,
        )]
