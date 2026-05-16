from __future__ import annotations

from itertools import combinations

from hexwar.core.actions import DeclareAttackAction, UndeclareAttackAction
from hexwar.core.battle import Battle
from hexwar.core.events import AttackDeclared, AttackUndeclared, Event
from hexwar.core.hex import HexCoord
from hexwar.core.state import GameState
from hexwar.core.unit import Player

SUB_PHASE_DECLARATION = "declaration"
SUB_PHASE_RESOLUTION = "resolution"


class DeclarationMixin:

    def _init_combat_declaration(self, state: GameState, player: Player) -> GameState:
        obligated_attackers, obligated_enemies = self._compute_obligations(state, player)
        state = state.with_metadata("combat_sub_phase", SUB_PHASE_DECLARATION)
        state = state.with_metadata("battles", [])
        state = state.with_metadata("next_battle_id", 1)
        state = state.with_metadata("committed_attackers", set())
        state = state.with_metadata("committed_defenders", set())
        state = state.with_metadata("obligated_attackers", obligated_attackers)
        state = state.with_metadata("obligated_enemies", obligated_enemies)
        state = state.with_metadata("declaration_complete", len(obligated_attackers) == 0 and len(obligated_enemies) == 0)
        return state

    def _cleanup_combat_metadata(self, state: GameState) -> GameState:
        return state.with_metadata_dropped(
            "combat_sub_phase", "battles", "next_battle_id",
            "committed_attackers", "committed_defenders",
            "obligated_attackers", "obligated_enemies", "declaration_complete",
        )

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

        Fan-in: multiple attacker hexes → ONE defender hex
        Fan-out: ONE attacker hex → multiple defender hexes
        Many-to-many: multiple attacker hexes → multiple defender hexes
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

    # ------------------------------------------------------------------
    # Apply methods
    # ------------------------------------------------------------------

    def _apply_declare_attack(
        self, state: GameState, action: DeclareAttackAction
    ) -> tuple[GameState, list[Event]]:
        player = action.player
        attacker_ids = action.attacker_ids
        defender_hexes = action.defender_hexes

        if not self._validate_topology(attacker_ids, defender_hexes, state):
            return state, []

        committed_attackers = set(state.metadata.get("committed_attackers", set()))
        for uid in attacker_ids:
            unit = state.get_unit(uid)
            if unit is None or unit.player != player:
                return state, []
            if uid in committed_attackers:
                return state, []

        defender_ids = self._get_defender_ids_for_hexes(state, defender_hexes, player)
        if not defender_ids:
            return state, []

        committed_defenders = set(state.metadata.get("committed_defenders", set()))
        for did in defender_ids:
            if did in committed_defenders:
                return state, []

        for uid in attacker_ids:
            unit = state.get_unit(uid)
            neighbors = set(unit.position.neighbors())
            if not any(dh in neighbors for dh in defender_hexes):
                return state, []

        battle_id = state.metadata.get("next_battle_id", 1)
        combatant_origin: dict[str, HexCoord] = {}
        for uid in attacker_ids:
            unit = state.get_unit(uid)
            if unit is not None:
                combatant_origin[uid] = unit.position
        for uid in defender_ids:
            unit = state.get_unit(uid)
            if unit is not None:
                combatant_origin[uid] = unit.position
        battle = Battle(
            id=battle_id,
            attacker_ids=attacker_ids,
            defender_hexes=defender_hexes,
            defender_ids=defender_ids,
            combatant_origin=combatant_origin,
        )

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
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle = None
        for b in battles:
            if b.id == action.battle_id:
                battle = b
                break
        if battle is None:
            return state, []

        battles.remove(battle)

        committed_attackers = set(state.metadata.get("committed_attackers", set()))
        committed_defenders = set(state.metadata.get("committed_defenders", set()))
        committed_attackers -= set(battle.attacker_ids)
        committed_defenders -= set(battle.defender_ids)

        state = state.with_metadata("battles", battles)
        state = state.with_metadata("committed_attackers", committed_attackers)
        state = state.with_metadata("committed_defenders", committed_defenders)
        state = state.with_metadata("declaration_complete", self._check_declaration_complete(state))

        return state, [AttackUndeclared(battle_id=action.battle_id)]

    # ------------------------------------------------------------------
    # Legal action generation
    # ------------------------------------------------------------------

    def _legal_declare_actions(self, state: GameState, player: Player) -> list[DeclareAttackAction]:
        """Generate all valid DeclareAttackAction combinations."""
        committed_attackers = state.metadata.get("committed_attackers", set())
        committed_defenders = state.metadata.get("committed_defenders", set())

        available_attackers: list[str] = []
        attacker_to_enemy_hexes: dict[str, set[HexCoord]] = {}

        for unit in state.units_of(player):
            if unit.id in committed_attackers:
                continue
            enemy_hexes: set[HexCoord] = set()
            for nb in unit.position.neighbors():
                enemies = [u for u in state.units_at(nb) if u.player != player]
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

        max_attackers = min(len(available_attackers), 6)
        for size in range(1, max_attackers + 1):
            for attacker_combo in combinations(available_attackers, size):
                attacker_positions = set()
                for uid in attacker_combo:
                    unit = state.get_unit(uid)
                    if unit:
                        attacker_positions.add(unit.position)

                if len(attacker_positions) > 1:
                    self._fan_in_actions(
                        state, player, attacker_combo, attacker_to_enemy_hexes,
                        committed_defenders, seen, actions,
                    )
                else:
                    self._fan_out_actions(
                        state, player, attacker_combo, attacker_to_enemy_hexes,
                        committed_defenders, seen, actions,
                    )

        return actions

    def _fan_in_actions(
        self, state: GameState, player: Player,
        attacker_combo: tuple[str, ...],
        attacker_to_enemy_hexes: dict[str, set[HexCoord]],
        committed_defenders: set[str],
        seen: set[tuple[tuple[str, ...], tuple[HexCoord, ...]]],
        out: list[DeclareAttackAction],
    ) -> None:
        """Multiple attacker hexes → single defender hex."""
        common_hexes = attacker_to_enemy_hexes[attacker_combo[0]].copy()
        for uid in attacker_combo[1:]:
            common_hexes &= attacker_to_enemy_hexes[uid]

        for dh in common_hexes:
            defenders = self._get_defender_ids_for_hexes(state, (dh,), player)
            if not defenders or any(d in committed_defenders for d in defenders):
                continue
            key = (tuple(sorted(attacker_combo)), (dh,))
            if key not in seen:
                seen.add(key)
                out.append(DeclareAttackAction(
                    player=player,
                    attacker_ids=tuple(sorted(attacker_combo)),
                    defender_hexes=(dh,),
                ))

    def _fan_out_actions(
        self, state: GameState, player: Player,
        attacker_combo: tuple[str, ...],
        attacker_to_enemy_hexes: dict[str, set[HexCoord]],
        committed_defenders: set[str],
        seen: set[tuple[tuple[str, ...], tuple[HexCoord, ...]]],
        out: list[DeclareAttackAction],
    ) -> None:
        """Single attacker hex → one or more defender hexes."""
        all_reachable: set[HexCoord] = set()
        for uid in attacker_combo:
            all_reachable |= attacker_to_enemy_hexes[uid]

        for dh_size in range(1, len(all_reachable) + 1):
            for dh_combo in combinations(sorted(all_reachable), dh_size):
                if not all(
                    any(dh in attacker_to_enemy_hexes.get(uid, set()) for uid in attacker_combo)
                    for dh in dh_combo
                ):
                    continue
                defenders = self._get_defender_ids_for_hexes(state, dh_combo, player)
                if not defenders or any(d in committed_defenders for d in defenders):
                    continue
                key = (tuple(sorted(attacker_combo)), tuple(sorted(dh_combo)))
                if key not in seen:
                    seen.add(key)
                    out.append(DeclareAttackAction(
                        player=player,
                        attacker_ids=tuple(sorted(attacker_combo)),
                        defender_hexes=tuple(sorted(dh_combo)),
                    ))

    def _legal_undeclare_actions(self, state: GameState, player: Player) -> list[UndeclareAttackAction]:
        """Generate UndeclareAttackAction for each existing battle."""
        battles = state.metadata.get("battles", [])
        return [UndeclareAttackAction(player=player, battle_id=b.id) for b in battles]
