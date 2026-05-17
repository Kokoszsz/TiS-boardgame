from __future__ import annotations

import math

from hexwar.core.actions import (
    Action, AssignCplLossAction, ChooseRetreatSplitAction,
    EndPhaseAction, PursuitAction, ResolveBattleAction,
    ResolveDisorgRollsAction, RetreatUnitAction, SkipPursuitAction,
)
from hexwar.core.battle import (
    Battle, PostBattlePhase, Side, cpl_phase_for, retreat_phase_for,
    side_of_phase, split_phase_for,
)
from hexwar.core.combat_results import BattleOutcome, CombatResult
from hexwar.core.events import (
    BattleResolved, DisorganizationRolled, Event, RetreatSplitChosen,
    UnitDisorganized, UnitLostCpl, UnitPursued, UnitRetreated,
)
from hexwar.core.hex import HexCoord
from hexwar.core.rng import GameRNG
from hexwar.core.state import GameState
from hexwar.core.unit import BattleId, Player, UnitId
from hexwar.systems.wb48.combat_declaration import CombatSubPhase
from hexwar.systems.wb48.crt import DISORG_THRESHOLD, lookup_crt


class ResolutionMixin:

    @staticmethod
    def _effective_strength(unit) -> int:
        """Rule 14.2: disorganized unit fights at half strength, rounded up."""
        raw = unit.stats.get("strength", 1)
        if unit.disorganized:
            return math.ceil(raw / 2)
        return raw

    def _mark_combat_active(
        self, state: GameState, unit_ids: tuple[UnitId, ...],
    ) -> GameState:
        for uid in unit_ids:
            unit = state.get_unit(uid)
            if unit is not None:
                state = state.with_unit(unit.with_last_active_turn(state.turn))
        return state

    def _apply_end_combat_subphase(
        self, state: GameState, action: EndPhaseAction
    ) -> tuple[GameState, list[Event]]:
        """Transitions from declaration to resolution sub-phase."""
        combat_sub_phase = state.metadata.get("combat_sub_phase")
        if combat_sub_phase == CombatSubPhase.DECLARATION:
            state = state.with_metadata("combat_sub_phase", CombatSubPhase.RESOLUTION)
        return state, []

    def _legal_resolve_actions(self, state: GameState, player: Player) -> list[ResolveBattleAction]:
        """One ResolveBattleAction per unresolved battle."""
        battles: list[Battle] = state.metadata.get("battles", [])
        return [
            ResolveBattleAction(player=player, battle_id=b.id)
            for b in battles if not b.resolved
        ]

    def _apply_resolve_battle(
        self, state: GameState, action: ResolveBattleAction, rng: GameRNG
    ) -> tuple[GameState, list[Event]]:
        """Resolve a single battle via CRT lookup."""
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle = None
        battle_idx = None
        for i, b in enumerate(battles):
            if b.id == action.battle_id and not b.resolved:
                battle = b
                battle_idx = i
                break
        if battle is None:
            return state, []

        attacker_ids = battle.attacker_ids
        defender_ids = battle.defender_ids

        atk_str = sum(
            self._effective_strength(state.get_unit(uid))
            for uid in attacker_ids if state.get_unit(uid)
        )
        def_str = sum(
            self._effective_strength(state.get_unit(uid))
            for uid in defender_ids if state.get_unit(uid)
        )

        state = self._mark_combat_active(state, attacker_ids)
        state = self._mark_combat_active(state, defender_ids)

        dice = rng.roll_dice(2, 6)
        die1, die2 = dice[0], dice[1]
        dice_total = die1 + die2

        combat_result = lookup_crt(atk_str, def_str, dice_total)

        # Apply immediate disorganization (D flag)
        immediate_disorg_events: list[Event] = []
        _disorganize_units = []
        if combat_result.attacker_disorganized:
            _disorganize_units.extend(attacker_ids)
        if combat_result.defender_disorganized:
            _disorganize_units.extend(defender_ids)
        for uid in _disorganize_units:
            state, evs = self._disorganize_unit(state, uid, action.battle_id)
            immediate_disorg_events.extend(evs)

        if combat_result.outcome == BattleOutcome.ATTACKER_WIN:
            pursuing_side: Side | None = Side.ATTACKER
        elif combat_result.outcome == BattleOutcome.DEFENDER_WIN:
            pursuing_side = Side.DEFENDER
        else:
            pursuing_side = None

        updated_battle = battle.replace(
            resolved=True,
            result=combat_result,
            dice_roll=(die1, die2),
            post_phase=self._initial_post_phase(combat_result),
            attacker_debt=combat_result.attacker_retreat,
            defender_debt=combat_result.defender_retreat,
            attacker_mandatory_cpl=combat_result.attacker_casualties,
            defender_mandatory_cpl=combat_result.defender_casualties,
            pursuing_side=pursuing_side,
        )
        updated_battle = updated_battle.replace(
            post_phase=self._skip_empty_phase(state, updated_battle)
        )
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
            result=combat_result,
        )
        return state, [event] + immediate_disorg_events

    # ------------------------------------------------------------------
    # Post-battle resolution
    # ------------------------------------------------------------------

    def _disorganize_unit(
        self, state: GameState, unit_id: UnitId, battle_id: BattleId,
    ) -> tuple[GameState, list[Event]]:
        """Mark unit as disorganized. Return event for UI."""
        unit = state.get_unit(unit_id)
        if not unit or unit.disorganized:
            return state, []
        updated_unit = unit.with_disorganized(True).with_last_active_turn(state.turn)
        state = state.with_unit(updated_unit)
        event = UnitDisorganized(unit_id=unit_id, battle_id=battle_id)
        return state, [event]

    def _compute_disorg_rolls(
        self, state: GameState, battle: Battle,
    ) -> dict[UnitId, int]:
        """Per-unit rolls owed. Skips dead and already-disorganized units.

        Sources (stack per unit):
          - '*' flag on side: +1 roll for every surviving participant
          - actual retreat hexes: 2 → +1, 3 → +2, 4-5 → +3 (rule 7.32)
        """
        if not battle.result:
            return {}
        result = battle.result
        rolls: dict[UnitId, int] = {}
        for unit_ids, star_flag in [
            (battle.attacker_ids, result.attacker_disorganized_roll),
            (battle.defender_ids, result.defender_disorganized_roll),
        ]:
            for uid in unit_ids:
                unit = state.get_unit(uid)
                if unit is None or unit.disorganized:
                    continue
                n = 0
                if star_flag:
                    n += 1
                actual = len(battle.retreat_paths.get(uid, ()))
                if actual == 2:
                    n += 1
                elif actual == 3:
                    n += 2
                elif actual >= 4:
                    n += 3
                if n > 0:
                    rolls[uid] = n
        return rolls

    def _legal_disorg_actions(
        self, state: GameState, player: Player, battle: Battle,
    ) -> list[ResolveDisorgRollsAction]:
        return [ResolveDisorgRollsAction(player=player, battle_id=battle.id)]

    def _apply_resolve_disorg_rolls(
        self, state: GameState, action: ResolveDisorgRollsAction, rng: GameRNG,
    ) -> tuple[GameState, list[Event]]:
        """Auto-resolve all disorganization rolls owed for a battle.

        Rolls 2d6 per owed roll. >= DISORG_THRESHOLD → unit becomes
        disorganized; subsequent rolls for that unit skipped.
        """
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle_idx = next(i for i, b in enumerate(battles) if b.id == action.battle_id)
        battle = battles[battle_idx]

        rolls_owed = self._compute_disorg_rolls(state, battle)
        events: list[Event] = []

        for uid, n in rolls_owed.items():
            for _ in range(n):
                dice = rng.roll_dice(2, 6)
                total = dice[0] + dice[1]
                failed = total >= DISORG_THRESHOLD
                events.append(DisorganizationRolled(
                    unit_id=uid, battle_id=battle.id,
                    dice=(dice[0], dice[1]), total=total,
                    threshold=DISORG_THRESHOLD,
                    became_disorganized=failed,
                ))
                if failed:
                    unit = state.get_unit(uid)
                    if unit and not unit.disorganized:
                        state = state.with_unit(unit.with_disorganized(True))
                        events.append(UnitDisorganized(unit_id=uid, battle_id=battle.id))
                    break

        updated = battle.replace(post_phase=PostBattlePhase.PURSUIT)
        updated = updated.replace(post_phase=self._skip_empty_phase(state, updated))
        battles[battle_idx] = updated
        state = state.with_metadata("battles", battles)
        return state, events

    def _initial_post_phase(self, result: CombatResult) -> PostBattlePhase:
        if result.attacker_retreat > 0:
            return PostBattlePhase.ATTACKER_SPLIT
        if result.defender_retreat > 0:
            return PostBattlePhase.DEFENDER_SPLIT
        if result.attacker_casualties > 0 or result.defender_casualties > 0:
            return PostBattlePhase.MANDATORY_CPL
        if result.attacker_disorganized_roll or result.defender_disorganized_roll:
            return PostBattlePhase.DISORG_ROLLS
        return PostBattlePhase.DONE

    def _find_active_post_battle(self, state: GameState) -> Battle | None:
        """Find first battle that is resolved but not post_phase=='done'."""
        for battle in state.metadata.get("battles", []):
            if battle.resolved and battle.post_phase != PostBattlePhase.DONE:
                return battle
        return None

    def _legal_post_battle_actions(
        self, state: GameState, player: Player, battle: Battle,
    ) -> list[Action]:
        """Return legal actions for current post-battle phase of a battle."""
        post_phase = battle.post_phase
        if post_phase == PostBattlePhase.ATTACKER_SPLIT:
            return self._legal_retreat_split_actions(state, player, battle, Side.ATTACKER)
        if post_phase == PostBattlePhase.DEFENDER_SPLIT:
            return self._legal_retreat_split_actions(state, player, battle, Side.DEFENDER)
        if post_phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL, PostBattlePhase.MANDATORY_CPL):
            return self._legal_assign_cpl_actions(state, player, battle)
        if post_phase in (PostBattlePhase.ATTACKER_RETREAT, PostBattlePhase.DEFENDER_RETREAT):
            return self._legal_retreat_actions(state, player, battle)
        if post_phase == PostBattlePhase.DISORG_ROLLS:
            return self._legal_disorg_actions(state, player, battle)
        if post_phase == PostBattlePhase.PURSUIT:
            return self._legal_pursuit_actions(state, player, battle)
        return []

    def _legal_retreat_split_actions(
        self, state: GameState, player: Player, battle: Battle, side: Side,
    ) -> list[ChooseRetreatSplitAction]:
        """Generate all valid retreat/loss splits for a side.

        E.g. debt=3 → (retreat=3,loss=0), (2,1), (1,2), (0,3)
        """
        debt = battle.debt(side)
        return [
            ChooseRetreatSplitAction(
                player=player,
                battle_id=battle.id,
                side=side,
                retreat_hexes=r,
                unit_losses=debt - r,
            )
            for r in range(debt + 1)
        ]

    def _legal_assign_cpl_actions(
        self, state: GameState, player: Player, battle: Battle,
    ) -> list[AssignCplLossAction]:
        """Return one AssignCplLossAction per eligible unit that can die."""
        post_phase = battle.post_phase
        side = side_of_phase(post_phase)
        if side is not None:
            unit_ids = battle.units(side)
        elif post_phase == PostBattlePhase.MANDATORY_CPL:
            if battle.mandatory_cpl(Side.ATTACKER) > 0:
                unit_ids = battle.units(Side.ATTACKER)
            else:
                unit_ids = battle.units(Side.DEFENDER)
        else:
            return []

        return [
            AssignCplLossAction(player=player, battle_id=battle.id, unit_id=uid)
            for uid in unit_ids
            if state.get_unit(uid) is not None
        ]

    def _legal_retreat_actions(
        self, state: GameState, player: Player, battle: Battle,
    ) -> list[RetreatUnitAction]:
        """Return valid retreat destinations for each unit that still needs to retreat."""
        actions: list[RetreatUnitAction] = []
        for uid in battle.units_needing_retreat:
            if state.get_unit(uid) is None:
                continue
            if len(battle.retreat_paths.get(uid, ())) >= battle.remaining_retreat_steps:
                continue
            for hex_coord in self._valid_retreat_hexes(state, uid, battle):
                actions.append(RetreatUnitAction(
                    player=player, battle_id=battle.id,
                    unit_id=uid, target=hex_coord,
                ))
        return actions

    def _retreat_source_hexes(self, state: GameState, battle: Battle) -> list[HexCoord]:
        """Get hex positions to retreat AWAY from (attacker hexes for defender, vice versa)."""
        if battle.post_phase == PostBattlePhase.DEFENDER_RETREAT:
            return [
                state.get_unit(uid).position
                for uid in battle.attacker_ids
                if state.get_unit(uid)
            ]
        else:
            return list(battle.defender_hexes)

    def _valid_retreat_hexes(
        self, state: GameState, unit_id: UnitId, battle: Battle,
    ) -> list[HexCoord]:
        """Compute valid hexes a unit can retreat to (one step).

        Must move away from attacking units. Can't enter enemy ZOC,
        impassable terrain, enemy-occupied hex, or exceed stacking.
        """
        unit = state.get_unit(unit_id)
        if unit is None:
            return []

        source_hexes = self._retreat_source_hexes(state, battle)
        current_dist = min(unit.position.distance(s) for s in source_hexes)
        zoc_map = self.enemy_zoc_map(state, unit.player)

        valid = []
        for nb in unit.position.neighbors():
            if nb not in state.hex_map.all_coords():
                continue
            if not state.hex_map.is_passable(nb):
                continue
            # Must increase distance from attackers
            nb_dist = min(nb.distance(s) for s in source_hexes)
            if nb_dist <= current_dist:
                continue
            # Can't enter enemy ZOC (7.39)
            # TODO: 7.42 — with real CPL, allow ZOC entry at cost of 1 CPL per hex
            if zoc_map.get(nb):
                continue
            # Can't enter enemy-occupied hex
            if any(u.player != unit.player for u in state.units_at(nb)):
                continue
            # Stacking limit (7.44)
            friendly_stack = sum(
                u.stats.get("stack_size", 1) for u in state.units_at(nb)
                if u.player == unit.player
            )
            unit_stack = unit.stats.get("stack_size", 1)
            if friendly_stack + unit_stack > self.STACK_LIMIT:
                continue
            valid.append(nb)
        return valid

    def _legal_pursuit_actions(
        self, state: GameState, player: Player, battle: Battle,
    ) -> list[PursuitAction | SkipPursuitAction]:
        """Pursuit: one move to death hex or hex adjacent to death hex. Then DONE."""
        pursuer = battle.pursuing_side
        if pursuer is None:
            return [SkipPursuitAction(player=player, battle_id=battle.id)]

        pursuer_ids = battle.units(pursuer)

        # Target hexes: retreat path hexes (follow retreater) + 7.57 neighbor bonus
        # only on fully-eliminated origin hexes.
        target_hexes: set[HexCoord] = set()

        loser_ids = battle.units(pursuer.opposite())
        hex_to_originals: dict[HexCoord, list[UnitId]] = {}
        for uid in loser_ids:
            origin = battle.combatant_origin.get(uid)
            if origin is not None:
                hex_to_originals.setdefault(origin, []).append(uid)

        # Follow-retreater pursuit: origin hex + intermediate path hexes (skip final
        # position, where retreater still sits with enemy units).
        for origin_hex in hex_to_originals:
            target_hexes.add(origin_hex)
        for path in battle.retreat_paths.values():
            for hex_ in path[:-1]:
                target_hexes.add(hex_)

        # Rule 7.57: when ALL originals on a hex were eliminated and no enemy
        # remains there, pursuit may also enter neighbors of that hex.
        for origin_hex, originals in hex_to_originals.items():
            all_eliminated = all(uid in battle.eliminated_at for uid in originals)
            enemy_remaining_units_on_hex = state.units_at(origin_hex)
            if all_eliminated and not any(u for u in enemy_remaining_units_on_hex if u.player != player):
                for nb in origin_hex.neighbors():
                    if nb in state.hex_map.all_coords() and state.hex_map.is_passable(nb):
                        target_hexes.add(nb)


        if not target_hexes:
            return [SkipPursuitAction(player=player, battle_id=battle.id)]

        actions: list[PursuitAction | SkipPursuitAction] = []
        for uid in pursuer_ids:
            if uid in battle.units_pursued:
                continue
            unit = state.get_unit(uid)
            if unit is None:
                continue
            if unit.disorganized:
                continue
            for hex_coord in target_hexes:
                if any(u.player != unit.player for u in state.units_at(hex_coord)):
                    continue
                actions.append(PursuitAction(
                    player=player, battle_id=battle.id,
                    unit_id=uid, target=hex_coord,
                ))
        actions.append(SkipPursuitAction(player=player, battle_id=battle.id))
        return actions

    def _apply_retreat_split(
        self, state: GameState, action: ChooseRetreatSplitAction,
    ) -> tuple[GameState, list[Event]]:
        """Player chose how to split An/Bn between retreat hexes and unit losses."""
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle_idx = next(i for i, b in enumerate(battles) if b.id == action.battle_id)
        battle = battles[battle_idx]

        side = action.side
        side_units = tuple(uid for uid in battle.units(side) if state.get_unit(uid))

        mandatory = battle.mandatory_cpl(side)
        total_losses = action.unit_losses + mandatory

        if total_losses > 0:
            next_phase = cpl_phase_for(side)
        elif action.retreat_hexes > 0:
            next_phase = retreat_phase_for(side)
        else:
            next_phase = self._next_phase_after_side(battle, side)

        updated = battle.replace(
            remaining_cpl_to_assign=total_losses,
            remaining_retreat_steps=action.retreat_hexes,
            units_needing_retreat=side_units if action.retreat_hexes > 0 else (),
            post_phase=next_phase,
        ).with_mandatory_cpl(side, 0)
        state, updated, encircled_events = self._eliminate_encircled(state, updated)
        updated = updated.replace(post_phase=self._skip_empty_phase(state, updated))
        battles[battle_idx] = updated
        state = state.with_metadata("battles", battles)

        events: list[Event] = [RetreatSplitChosen(
            battle_id=action.battle_id,
            side=action.side,
            retreat_hexes=action.retreat_hexes,
            unit_losses=action.unit_losses,
        )]
        events.extend(encircled_events)
        return state, events

    def _eliminate_encircled(
        self, state: GameState, battle: Battle,
    ) -> tuple[GameState, Battle, list[Event]]:
        """Eliminate units in retreat phase that have no valid retreat hex.

        Encircled units suffer 1 CPL loss (per house rule for stuck retreats).
        Returns updated state, battle (with units_needing_retreat filtered and
        eliminated_at expanded), and events for each elimination.
        """
        if battle.post_phase not in (
            PostBattlePhase.ATTACKER_RETREAT, PostBattlePhase.DEFENDER_RETREAT,
        ):
            return state, battle, []

        events: list[Event] = []
        new_needing: list[UnitId] = []
        new_eliminated = dict(battle.eliminated_at)
        for uid in battle.units_needing_retreat:
            unit = state.get_unit(uid)
            if unit is None:
                continue
            if not self._valid_retreat_hexes(state, uid, battle):
                new_eliminated[uid] = unit.position
                state = state.with_unit_removed(uid)
                events.append(UnitLostCpl(unit_id=uid, battle_id=battle.id))
            else:
                new_needing.append(uid)
        battle = battle.replace(
            units_needing_retreat=tuple(new_needing),
            eliminated_at=new_eliminated,
        )
        return state, battle, events

    def _next_phase_after_side(self, battle: Battle, side: Side) -> PostBattlePhase:
        """Determine next phase after a side's split/cpl/retreat is done."""
        if side is Side.ATTACKER and battle.debt(Side.DEFENDER) > 0:
            return PostBattlePhase.DEFENDER_SPLIT
        if battle.mandatory_cpl(Side.ATTACKER) > 0 or battle.mandatory_cpl(Side.DEFENDER) > 0:
            return PostBattlePhase.MANDATORY_CPL
        return PostBattlePhase.DISORG_ROLLS

    def _skip_empty_phase(self, state: GameState, battle: Battle) -> PostBattlePhase:
        """Skip post-battle phases that have no eligible units. Loops until stable."""
        phase = battle.post_phase
        while True:
            if phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL):
                side = side_of_phase(phase)
                if not any(state.get_unit(uid) for uid in battle.units(side)):
                    if battle.remaining_retreat_steps > 0:
                        phase = retreat_phase_for(side)
                    else:
                        phase = self._next_phase_after_side(battle, side)
                    continue
            if phase == PostBattlePhase.MANDATORY_CPL:
                has_atk = battle.mandatory_cpl(Side.ATTACKER) > 0 and any(
                    state.get_unit(uid) for uid in battle.units(Side.ATTACKER)
                )
                has_def = battle.mandatory_cpl(Side.DEFENDER) > 0 and any(
                    state.get_unit(uid) for uid in battle.units(Side.DEFENDER)
                )
                if not has_atk and not has_def:
                    phase = PostBattlePhase.PURSUIT
                    continue
            if phase in (PostBattlePhase.ATTACKER_RETREAT, PostBattlePhase.DEFENDER_RETREAT):
                alive_retreaters = [uid for uid in battle.units_needing_retreat if state.get_unit(uid)]
                if not alive_retreaters:
                    phase = self._next_phase_after_side(battle, side_of_phase(phase))
                    continue
            if phase == PostBattlePhase.DISORG_ROLLS:
                probe = battle.replace(post_phase=phase)
                if not self._compute_disorg_rolls(state, probe):
                    phase = PostBattlePhase.PURSUIT
                    continue
            if phase == PostBattlePhase.PURSUIT:
                if battle.pursuing_side is None:
                    phase = PostBattlePhase.DONE
                    continue
                # Rule 14.3: disorganized units cannot pursue.
                able = [
                    uid for uid in battle.units(battle.pursuing_side)
                    if (u := state.get_unit(uid)) is not None and not u.disorganized
                ]
                if not able:
                    phase = PostBattlePhase.DONE
                    continue
            break
        return phase

    def _apply_assign_cpl_loss(
        self, state: GameState, action: AssignCplLossAction,
    ) -> tuple[GameState, list[Event]]:
        """Destroy chosen unit (1 CPL = dead). Decrement remaining_cpl_to_assign."""
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle_idx = next(i for i, b in enumerate(battles) if b.id == action.battle_id)
        battle = battles[battle_idx]

        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []

        # Record where unit died for pursuit targeting
        new_eliminated = dict(battle.eliminated_at)
        new_eliminated[action.unit_id] = unit.position
        battle = battle.replace(eliminated_at=new_eliminated)

        state = state.with_unit_removed(action.unit_id)
        events: list[Event] = [UnitLostCpl(unit_id=action.unit_id, battle_id=action.battle_id)]

        remaining = battle.remaining_cpl_to_assign - 1

        if remaining <= 0:
            if battle.post_phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL):
                side = side_of_phase(battle.post_phase)
                if battle.remaining_retreat_steps > 0:
                    next_phase = retreat_phase_for(side)
                else:
                    next_phase = self._next_phase_after_side(battle, side)
            elif battle.post_phase == PostBattlePhase.MANDATORY_CPL:
                atk_remaining = battle.mandatory_cpl(Side.ATTACKER)
                def_remaining = battle.mandatory_cpl(Side.DEFENDER)
                if atk_remaining > 0:
                    atk_remaining -= 1
                else:
                    def_remaining -= 1
                if atk_remaining > 0 or def_remaining > 0:
                    next_phase = PostBattlePhase.MANDATORY_CPL
                else:
                    next_phase = PostBattlePhase.DISORG_ROLLS
                battle = battle.with_mandatory_cpl(Side.ATTACKER, atk_remaining).with_mandatory_cpl(Side.DEFENDER, def_remaining)
            else:
                next_phase = PostBattlePhase.DISORG_ROLLS
            updated = battle.replace(remaining_cpl_to_assign=0, post_phase=next_phase)
        else:
            updated = battle.replace(remaining_cpl_to_assign=remaining)

        # Eliminate encircled if we transitioned to a retreat phase
        state, updated, encircled_events = self._eliminate_encircled(state, updated)
        events.extend(encircled_events)
        # Skip phases where no units can act
        updated = updated.replace(post_phase=self._skip_empty_phase(state, updated))
        battles[battle_idx] = updated
        state = state.with_metadata("battles", battles)
        return state, events

    def _apply_retreat_unit(
        self, state: GameState, action: RetreatUnitAction,
    ) -> tuple[GameState, list[Event]]:
        """Move one unit one hex during retreat. Record path for pursuit."""
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle_idx = next(i for i, b in enumerate(battles) if b.id == action.battle_id)
        battle = battles[battle_idx]

        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []

        old_pos = unit.position
        state = state.with_unit_moved(action.unit_id, action.target)

        # Record retreat path
        retreat_paths = dict(battle.retreat_paths)
        path = list(retreat_paths.get(action.unit_id, ()))
        path.append(action.target)
        retreat_paths[action.unit_id] = tuple(path)

        # Check if all units done retreating (each unit retreats remaining_retreat_steps hexes)
        all_done = all(
            len(retreat_paths.get(uid, ())) >= battle.remaining_retreat_steps
            for uid in battle.units_needing_retreat
            if state.get_unit(uid) is not None
        )

        if all_done:
            next_phase = self._next_phase_after_side(battle, side_of_phase(battle.post_phase))
            updated = battle.replace(retreat_paths=retreat_paths, post_phase=next_phase, remaining_retreat_steps=0)
        else:
            updated = battle.replace(retreat_paths=retreat_paths)

        battles[battle_idx] = updated
        state = state.with_metadata("battles", battles)

        event = UnitRetreated(
            unit_id=action.unit_id, from_hex=old_pos,
            to_hex=action.target, battle_id=action.battle_id,
        )
        return state, [event]

    def _apply_pursuit(
        self, state: GameState, action: PursuitAction,
    ) -> tuple[GameState, list[Event]]:
        """Move pursuing unit one hex. DONE when all pursuers have moved or been skipped."""
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle_idx = next(i for i, b in enumerate(battles) if b.id == action.battle_id)
        battle = battles[battle_idx]

        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []

        old_pos = unit.position
        state = state.with_unit_moved(action.unit_id, action.target)

        new_pursued = battle.units_pursued + (action.unit_id,)
        pursuer_ids = battle.units(battle.pursuing_side)
        all_done = all(
            uid in new_pursued or state.get_unit(uid) is None
            for uid in pursuer_ids
        )
        updated = battle.replace(
            units_pursued=new_pursued,
            post_phase=PostBattlePhase.DONE if all_done else PostBattlePhase.PURSUIT,
        )
        battles[battle_idx] = updated
        state = state.with_metadata("battles", battles)

        event = UnitPursued(
            unit_id=action.unit_id, from_hex=old_pos,
            to_hex=action.target, battle_id=action.battle_id,
        )
        return state, [event]

    def _apply_skip_pursuit(
        self, state: GameState, action: SkipPursuitAction,
    ) -> tuple[GameState, list[Event]]:
        """Player declines pursuit. Set post_phase = DONE."""
        battles: list[Battle] = list(state.metadata.get("battles", []))
        battle_idx = next(i for i, b in enumerate(battles) if b.id == action.battle_id)
        battle = battles[battle_idx]

        updated = battle.replace(post_phase=PostBattlePhase.DONE)
        battles[battle_idx] = updated
        state = state.with_metadata("battles", battles)
        return state, []
