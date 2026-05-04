from __future__ import annotations

from itertools import combinations

from hexwar.core.actions import (
    Action, AttackAction, DeclareAttackAction, EndPhaseAction,
    EntrenchAction, MoveAction, ResolveBattleAction, UndeclareAttackAction,
)
from hexwar.core.events import (
    AttackDeclared, AttackUndeclared, BattleResolved, CombatResolved, Event,
    UnitDestroyed, UnitEntrenched, UnitMoved,
)
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
                     allowed_actions=[DeclareAttackAction, UndeclareAttackAction, EndPhaseAction]),
            PhaseDef(id="move_b", name="Player B Movement", player=PLAYER_B,
                     allowed_actions=[MoveAction, EntrenchAction, EndPhaseAction]),
            PhaseDef(id="combat_b", name="Player B Combat", player=PLAYER_B,
                     allowed_actions=[DeclareAttackAction, UndeclareAttackAction, EndPhaseAction]),
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

        if DeclareAttackAction in phase.allowed_actions:
            combat_sub_phase = state.metadata.get("combat_sub_phase")
            if combat_sub_phase == "declaration":
                actions.extend(self._legal_declare_actions(state, player))
                actions.extend(self._legal_undeclare_actions(state, player))
            elif combat_sub_phase == "resolution":
                actions.extend(self._legal_resolve_actions(state, player))

        if AttackAction in phase.allowed_actions:
            for unit in state.units_of(player):
                for nb in unit.position.neighbors():
                    enemies = [u for u in state.units_at(nb) if u.player != player]
                    for enemy in enemies:
                        actions.append(
                            AttackAction(player=player, attacker_id=unit.id, defender_id=enemy.id)
                        )

        # EndPhaseAction: only if declaration is complete (or no combat phase)
        if DeclareAttackAction in phase.allowed_actions:
            combat_sub_phase = state.metadata.get("combat_sub_phase")
            if combat_sub_phase == "declaration":
                if state.metadata.get("declaration_complete", False):
                    actions.append(EndPhaseAction(player=player))
            elif combat_sub_phase == "resolution":
                # Can end phase only when all battles resolved
                unresolved = [b for b in state.metadata.get("battles", [])
                              if not b.get("resolved")]
                if not unresolved:
                    actions.append(EndPhaseAction(player=player))
        else:
            actions.append(EndPhaseAction(player=player))

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
        if isinstance(action, DeclareAttackAction):
            return self._apply_declare_attack(state, action)
        if isinstance(action, UndeclareAttackAction):
            return self._apply_undeclare_attack(state, action)
        if isinstance(action, ResolveBattleAction):
            return self._apply_resolve_battle(state, action, rng)
        if isinstance(action, EndPhaseAction):
            return self._apply_end_phase(state, action)
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
        new_state = state.with_metadata("remaining_mp", {})
        if phase.id in ("combat_a", "combat_b"):
            new_state = self._init_combat_declaration(new_state, phase.player)
        return new_state, []

    def on_phase_exit(
        self, state: GameState, phase: PhaseDef
    ) -> tuple[GameState, list[Event]]:
        if phase.id in ("combat_a", "combat_b"):
            state = self._cleanup_combat_metadata(state)
        return state, []

    def should_advance_phase(self, state: GameState) -> bool:
        """Block phase advance during declaration sub-phase when there are
        battles to resolve. Skip resolution if no battles were declared."""
        combat_sub_phase = state.metadata.get("combat_sub_phase")
        if combat_sub_phase == "declaration":
            battles = state.metadata.get("battles", [])
            if battles:
                return False  # Must go through resolution
        return True

    # ------------------------------------------------------------------
    # Combat declaration system
    # ------------------------------------------------------------------

    def _init_combat_declaration(self, state: GameState, player: Player) -> GameState:
        obligated_attackers, obligated_enemies = self._compute_obligations(state, player)
        state = state.with_metadata("combat_sub_phase", "declaration")
        state = state.with_metadata("battles", [])
        state = state.with_metadata("next_battle_id", 1)
        state = state.with_metadata("committed_attackers", set())
        state = state.with_metadata("committed_defenders", set())
        state = state.with_metadata("obligated_attackers", obligated_attackers)
        state = state.with_metadata("obligated_enemies", obligated_enemies)
        state = state.with_metadata("declaration_complete", len(obligated_attackers) == 0 and len(obligated_enemies) == 0)
        return state

    def _cleanup_combat_metadata(self, state: GameState) -> GameState:
        for key in ("combat_sub_phase", "battles", "next_battle_id",
                    "committed_attackers", "committed_defenders",
                    "obligated_attackers", "obligated_enemies", "declaration_complete"):
            md = dict(state.metadata)
            md.pop(key, None)
            state = GameState(
                scenario_id=state.scenario_id, scenario_name=state.scenario_name,
                system_id=state.system_id, hex_map=state.hex_map, units=state.units,
                units_by_hex=state.units_by_hex,
                active_player=state.active_player, turn=state.turn,
                phase_index=state.phase_index, metadata=md,
            )
        return state

    def _compute_obligations(
        self, state: GameState, player: Player
    ) -> tuple[set[str], set[str]]:
        """Compute which units MUST attack and which enemies MUST be attacked.

        Rule 7.21: All enemy units in your ZOC must be attacked.
        Rule 7.22: All your units with enemies in their ZOC must attack.
        Exception: units in field fortifications (entrenched) per 9.23.
        """
        entrenched_hexes = state.metadata.get("entrenched", {})
        obligated_attackers: set[str] = set()
        obligated_enemies: set[str] = set()

        for unit in state.units_of(player):
            # Exception: entrenched units don't have to attack
            if unit.position in entrenched_hexes and entrenched_hexes[unit.position] == player:
                continue
            has_enemy_in_zoc = False
            for nb in unit.position.neighbors():
                enemies = [u for u in state.units_at(nb) if u.player != player]
                if enemies:
                    has_enemy_in_zoc = True
                    for enemy in enemies:
                        obligated_enemies.add(enemy.id)
            if has_enemy_in_zoc:
                obligated_attackers.add(unit.id)

        return obligated_attackers, obligated_enemies

    def _check_declaration_complete(self, state: GameState) -> bool:
        """Check if all obligations are satisfied."""
        obligated_attackers = state.metadata.get("obligated_attackers", set())
        obligated_enemies = state.metadata.get("obligated_enemies", set())
        committed_attackers = state.metadata.get("committed_attackers", set())
        committed_defenders = state.metadata.get("committed_defenders", set())
        return (obligated_attackers <= committed_attackers and
                obligated_enemies <= committed_defenders)

    def _validate_topology(self, attacker_ids: tuple[str, ...], defender_hexes: tuple[HexCoord, ...], state: GameState) -> bool:
        """Validate battle topology: fan-in OR fan-out, NOT many-to-many.

        Fan-in: multiple attacker hexes → ONE defender hex ✓
        Fan-out: ONE attacker hex → multiple defender hexes ✓
        Many-to-many: multiple attacker hexes → multiple defender hexes ✗
        """
        attacker_hexes = set()
        for uid in attacker_ids:
            unit = state.get_unit(uid)
            if unit:
                attacker_hexes.add(unit.position)
        if len(attacker_hexes) > 1 and len(defender_hexes) > 1:
            return False
        return True

    def _get_defender_ids_for_hexes(
        self, state: GameState, defender_hexes: tuple[HexCoord, ...], player: Player
    ) -> tuple[str, ...]:
        """Rule 7.24: all enemy units on target hexes must be attacked together."""
        defender_ids = []
        for hex_coord in defender_hexes:
            for unit in state.units_at(hex_coord):
                if unit.player != player:
                    defender_ids.append(unit.id)
        return tuple(defender_ids)

    def _compute_ratio(self, state: GameState, attacker_ids: tuple[str, ...], defender_ids: tuple[str, ...]) -> str:
        """Compute attack strength ratio string."""
        atk_str = sum(state.get_unit(uid).stats.get("strength", 1) for uid in attacker_ids if state.get_unit(uid))
        def_str = sum(state.get_unit(uid).stats.get("strength", 1) for uid in defender_ids if state.get_unit(uid))
        if def_str == 0:
            return "auto"
        return f"{atk_str}:{def_str}"

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

    # ------------------------------------------------------------------
    # Declaration apply methods
    # ------------------------------------------------------------------

    def _apply_declare_attack(
        self, state: GameState, action: DeclareAttackAction
    ) -> tuple[GameState, list[Event]]:
        player = action.player
        attacker_ids = action.attacker_ids
        defender_hexes = action.defender_hexes

        # Validate topology
        if not self._validate_topology(attacker_ids, defender_hexes, state):
            return state, []

        # Validate attackers belong to player and are not committed
        committed_attackers = set(state.metadata.get("committed_attackers", set()))
        for uid in attacker_ids:
            unit = state.get_unit(uid)
            if unit is None or unit.player != player:
                return state, []
            if uid in committed_attackers:
                return state, []

        # Validate defenders exist on target hexes
        defender_ids = self._get_defender_ids_for_hexes(state, defender_hexes, player)
        if not defender_ids:
            return state, []

        # Validate defenders are not already committed
        committed_defenders = set(state.metadata.get("committed_defenders", set()))
        for did in defender_ids:
            if did in committed_defenders:
                return state, []

        # Validate adjacency: each attacker must be adjacent to at least one defender hex
        for uid in attacker_ids:
            unit = state.get_unit(uid)
            neighbors = set(unit.position.neighbors())
            if not any(dh in neighbors for dh in defender_hexes):
                return state, []

        # Rule 7.27: each unit attacks only once (already checked via committed sets)

        # Create battle
        battle_id = state.metadata.get("next_battle_id", 1)
        battle = {
            "id": battle_id,
            "attacker_ids": attacker_ids,
            "defender_hexes": defender_hexes,
            "defender_ids": defender_ids,
        }

        battles = list(state.metadata.get("battles", []))
        battles.append(battle)

        new_committed_attackers = committed_attackers | set(attacker_ids)
        new_committed_defenders = committed_defenders | set(defender_ids)

        state = state.with_metadata("battles", battles)
        state = state.with_metadata("next_battle_id", battle_id + 1)
        state = state.with_metadata("committed_attackers", new_committed_attackers)
        state = state.with_metadata("committed_defenders", new_committed_defenders)
        state = state.with_metadata("declaration_complete", self._check_declaration_complete(state))

        ratio = self._compute_ratio(state, attacker_ids, defender_ids)
        event = AttackDeclared(
            battle_id=battle_id,
            attacker_ids=attacker_ids,
            defender_ids=defender_ids,
            attack_ratio=ratio,
        )
        return state, [event]

    def _apply_undeclare_attack(
        self, state: GameState, action: UndeclareAttackAction
    ) -> tuple[GameState, list[Event]]:
        battles = list(state.metadata.get("battles", []))
        battle = None
        for b in battles:
            if b["id"] == action.battle_id:
                battle = b
                break
        if battle is None:
            return state, []

        battles.remove(battle)

        committed_attackers = set(state.metadata.get("committed_attackers", set()))
        committed_defenders = set(state.metadata.get("committed_defenders", set()))
        committed_attackers -= set(battle["attacker_ids"])
        committed_defenders -= set(battle["defender_ids"])

        state = state.with_metadata("battles", battles)
        state = state.with_metadata("committed_attackers", committed_attackers)
        state = state.with_metadata("committed_defenders", committed_defenders)
        state = state.with_metadata("declaration_complete", self._check_declaration_complete(state))

        return state, [AttackUndeclared(battle_id=action.battle_id)]

    # ------------------------------------------------------------------
    # Legal actions for declaration sub-phase
    # ------------------------------------------------------------------

    def _legal_declare_actions(self, state: GameState, player: Player) -> list[DeclareAttackAction]:
        """Generate all valid DeclareAttackAction combinations.

        For each uncommitted friendly unit adjacent to enemies, enumerate
        valid attacker subsets × defender hex subsets respecting topology.
        """
        committed_attackers = state.metadata.get("committed_attackers", set())
        committed_defenders = state.metadata.get("committed_defenders", set())

        # Find available attackers (friendly, uncommitted, adjacent to enemy)
        available_attackers: list[str] = []
        attacker_to_enemy_hexes: dict[str, set[HexCoord]] = {}

        for unit in state.units_of(player):
            if unit.id in committed_attackers:
                continue
            enemy_hexes: set[HexCoord] = set()
            for nb in unit.position.neighbors():
                enemies = [u for u in state.units_at(nb) if u.player != player]
                # Filter out already committed defenders
                uncommitted_enemies = [u for u in enemies if u.id not in committed_defenders]
                if uncommitted_enemies:
                    enemy_hexes.add(nb)
            if enemy_hexes:
                available_attackers.append(unit.id)
                attacker_to_enemy_hexes[unit.id] = enemy_hexes

        if not available_attackers:
            return []

        actions: list[DeclareAttackAction] = []
        seen: set[tuple[tuple[str, ...], tuple[HexCoord, ...]]] = set()

        # Generate combinations: for each subset of attackers (1 to all available),
        # find common reachable defender hexes, then for each subset of those hexes
        # validate topology.
        max_attackers = min(len(available_attackers), 6)  # practical limit
        for size in range(1, max_attackers + 1):
            for attacker_combo in combinations(available_attackers, size):
                # Common enemy hexes reachable by ALL attackers in combo
                common_hexes = attacker_to_enemy_hexes[attacker_combo[0]].copy()
                for uid in attacker_combo[1:]:
                    common_hexes &= attacker_to_enemy_hexes[uid]

                # Also include individual reachable hexes for fan-in
                all_reachable_hexes: set[HexCoord] = set()
                for uid in attacker_combo:
                    all_reachable_hexes |= attacker_to_enemy_hexes[uid]

                # Check topology: if attackers on multiple hexes, only 1 defender hex allowed (fan-in)
                attacker_positions = set()
                for uid in attacker_combo:
                    unit = state.get_unit(uid)
                    if unit:
                        attacker_positions.add(unit.position)

                if len(attacker_positions) > 1:
                    # Fan-in: only single defender hex allowed, must be reachable by all
                    for dh in common_hexes:
                        # Check defenders on this hex not committed
                        defenders = self._get_defender_ids_for_hexes(state, (dh,), player)
                        if not defenders or any(d in committed_defenders for d in defenders):
                            continue
                        key = (tuple(sorted(attacker_combo)), (dh,))
                        if key not in seen:
                            seen.add(key)
                            actions.append(DeclareAttackAction(
                                player=player,
                                attacker_ids=tuple(sorted(attacker_combo)),
                                defender_hexes=(dh,),
                            ))
                else:
                    # Single attacker hex: fan-out allowed (multiple defender hexes)
                    for dh_size in range(1, len(all_reachable_hexes) + 1):
                        for dh_combo in combinations(sorted(all_reachable_hexes), dh_size):
                            # Check each defender hex is adjacent to at least one attacker
                            valid = True
                            for dh in dh_combo:
                                if not any(dh in attacker_to_enemy_hexes.get(uid, set()) for uid in attacker_combo):
                                    valid = False
                                    break
                            if not valid:
                                continue
                            defenders = self._get_defender_ids_for_hexes(state, dh_combo, player)
                            if not defenders or any(d in committed_defenders for d in defenders):
                                continue
                            key = (tuple(sorted(attacker_combo)), tuple(sorted(dh_combo)))
                            if key not in seen:
                                seen.add(key)
                                actions.append(DeclareAttackAction(
                                    player=player,
                                    attacker_ids=tuple(sorted(attacker_combo)),
                                    defender_hexes=tuple(sorted(dh_combo)),
                                ))

        return actions

    def _legal_undeclare_actions(self, state: GameState, player: Player) -> list[UndeclareAttackAction]:
        """Generate UndeclareAttackAction for each existing battle."""
        battles = state.metadata.get("battles", [])
        return [UndeclareAttackAction(player=player, battle_id=b["id"]) for b in battles]

    # ------------------------------------------------------------------
    # Resolution sub-phase
    # ------------------------------------------------------------------

    def _apply_end_phase(
        self, state: GameState, action: EndPhaseAction
    ) -> tuple[GameState, list[Event]]:
        """Handle EndPhaseAction routed by engine when should_advance_phase=False.
        Transitions from declaration to resolution sub-phase."""
        combat_sub_phase = state.metadata.get("combat_sub_phase")
        if combat_sub_phase == "declaration":
            state = state.with_metadata("combat_sub_phase", "resolution")
        return state, []

    def _legal_resolve_actions(self, state: GameState, player: Player) -> list[ResolveBattleAction]:
        """One ResolveBattleAction per unresolved battle."""
        battles = state.metadata.get("battles", [])
        return [
            ResolveBattleAction(player=player, battle_id=b["id"])
            for b in battles if not b.get("resolved")
        ]

    def _apply_resolve_battle(
        self, state: GameState, action: ResolveBattleAction, rng: GameRNG
    ) -> tuple[GameState, list[Event]]:
        """Resolve a single battle. Currently always results in a tie."""
        battles = list(state.metadata.get("battles", []))
        battle = None
        battle_idx = None
        for i, b in enumerate(battles):
            if b["id"] == action.battle_id and not b.get("resolved"):
                battle = b
                battle_idx = i
                break
        if battle is None:
            return state, []

        attacker_ids = battle["attacker_ids"]
        defender_ids = battle["defender_ids"]

        # Compute strengths
        atk_str = sum(
            state.get_unit(uid).stats.get("strength", 1)
            for uid in attacker_ids if state.get_unit(uid)
        )
        def_str = sum(
            state.get_unit(uid).stats.get("strength", 1)
            for uid in defender_ids if state.get_unit(uid)
        )

        # Roll 2d6
        dice = rng.roll_dice(2, 6)
        die1, die2 = dice[0], dice[1]
        dice_total = die1 + die2

        # For now: always tie
        result = "tie"

        # Mark battle as resolved
        updated_battle = dict(battle)
        updated_battle["resolved"] = True
        updated_battle["result"] = result
        updated_battle["dice_roll"] = (die1, die2)
        battles[battle_idx] = updated_battle
        state = state.with_metadata("battles", battles)

        event = BattleResolved(
            battle_id=action.battle_id,
            attacker_ids=attacker_ids,
            defender_ids=defender_ids,
            attack_strength=atk_str,
            defense_strength=def_str,
            dice_roll=(die1, die2),
            dice_total=dice_total,
            result=result,
        )
        return state, [event]
