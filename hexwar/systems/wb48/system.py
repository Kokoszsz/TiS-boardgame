from __future__ import annotations

from hexwar.core.actions import (
    Action, AssignCplLossAction, ChooseRetreatSplitAction,
    DeclareAttackAction, DeclareStrategicMovementAction, EndPhaseAction,
    EntrenchAction, MoveAction, PursuitAction, ResolveBattleAction,
    RetreatUnitAction, SkipPursuitAction, UndeclareAttackAction,
)
from hexwar.core.events import Event
from hexwar.core.map import TerrainType
from hexwar.core.rng import GameRNG
from hexwar.core.state import GameState
from hexwar.core.unit import Player, UnitTypeDef
from hexwar.systems.base import PhaseDef, System
from hexwar.systems.wb48.combat_declaration import (
    SUB_PHASE_DECLARATION, SUB_PHASE_RESOLUTION, DeclarationMixin,
)
from hexwar.core.battle import PostBattlePhase
from hexwar.systems.wb48.combat_resolution import ResolutionMixin
from hexwar.systems.wb48.movement import MovementMixin

PLAYER_A = "player_a"
PLAYER_B = "player_b"


class WB48System(MovementMixin, DeclarationMixin, ResolutionMixin, System):
    name = "WB48System"
    version = "0.1"

    STACK_LIMIT = 6
    ZOC_UNIT_TYPES = {"infantry", "tank"}

    TERRAIN_COSTS: dict[TerrainType, float | None] = {
        TerrainType.PLAIN: 1,
        TerrainType.FOREST: 2,
        TerrainType.HILL: 2,
        TerrainType.CITY: 1,
        TerrainType.SWAMP: 3,
        TerrainType.MOUNTAIN: None,
        TerrainType.WATER: None,
    }

    def __init__(self):
        self.phases = [
            PhaseDef(id="move_a", name="Player A Movement", player=PLAYER_A,
                     phase_type="movement",
                     allowed_actions=[MoveAction, EntrenchAction, EndPhaseAction]),
            PhaseDef(id="combat_a", name="Player A Combat", player=PLAYER_A,
                     phase_type="combat",
                     allowed_actions=[DeclareAttackAction, UndeclareAttackAction, EndPhaseAction]),
            PhaseDef(id="move_b", name="Player B Movement", player=PLAYER_B,
                     phase_type="movement",
                     allowed_actions=[MoveAction, EntrenchAction, EndPhaseAction]),
            PhaseDef(id="combat_b", name="Player B Combat", player=PLAYER_B,
                     phase_type="combat",
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

    def legal_actions(self, state: GameState, player: Player) -> list[Action]:
        phase = self.phases[state.phase_index]
        actions: list[Action] = []

        if MoveAction in phase.allowed_actions:
            actions.extend(self._legal_move_actions(state, player))

        if EntrenchAction in phase.allowed_actions:
            actions.extend(self._legal_entrench_actions(state, player))

        if DeclareAttackAction in phase.allowed_actions:
            combat_sub_phase = state.metadata.get("combat_sub_phase")
            if combat_sub_phase == SUB_PHASE_DECLARATION:
                actions.extend(self._legal_declare_actions(state, player))
                actions.extend(self._legal_undeclare_actions(state, player))
                if state.metadata.get("declaration_complete", False):
                    actions.append(EndPhaseAction(player=player))
            elif combat_sub_phase == SUB_PHASE_RESOLUTION:
                post_battle = self._find_active_post_battle(state)
                if post_battle:
                    actions.extend(self._legal_post_battle_actions(state, player, post_battle))
                else:
                    actions.extend(self._legal_resolve_actions(state, player))
                    all_done = all(
                        b.post_phase == PostBattlePhase.DONE
                        for b in state.metadata.get("battles", [])
                        if b.resolved
                    )
                    unresolved = [b for b in state.metadata.get("battles", [])
                                  if not b.resolved]
                    if not unresolved and all_done:
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
        if isinstance(action, DeclareStrategicMovementAction):
            return self._apply_declare_strategic_movement(state, action)
        if isinstance(action, DeclareAttackAction):
            return self._apply_declare_attack(state, action)
        if isinstance(action, UndeclareAttackAction):
            return self._apply_undeclare_attack(state, action)
        if isinstance(action, ResolveBattleAction):
            return self._apply_resolve_battle(state, action, rng)
        if isinstance(action, ChooseRetreatSplitAction):
            return self._apply_retreat_split(state, action)
        if isinstance(action, AssignCplLossAction):
            return self._apply_assign_cpl_loss(state, action)
        if isinstance(action, RetreatUnitAction):
            return self._apply_retreat_unit(state, action)
        if isinstance(action, PursuitAction):
            return self._apply_pursuit(state, action)
        if isinstance(action, SkipPursuitAction):
            return self._apply_skip_pursuit(state, action)
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
        new_state = state
        if phase.id in ("move_a", "move_b"):
            for unit in new_state.units_of(phase.player):
                new_state = new_state.with_unit(unit.with_movement_left(unit.movement_max))
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
        combat_sub_phase = state.metadata.get("combat_sub_phase")
        if combat_sub_phase == SUB_PHASE_DECLARATION:
            battles = state.metadata.get("battles", [])
            if battles:
                return False
        if combat_sub_phase == SUB_PHASE_RESOLUTION:
            battles = state.metadata.get("battles", [])
            all_done = all(b.resolved and b.post_phase == PostBattlePhase.DONE for b in battles)
            if not all_done:
                return False
        return True
