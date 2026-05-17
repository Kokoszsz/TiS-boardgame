from __future__ import annotations

from hexwar.core.actions import StrategicMoveAction
from hexwar.core.events import Event, UnitMoved
from hexwar.core.pathfinding import reachable_hexes
from hexwar.core.state import GameState
from hexwar.core.unit import Player
from hexwar.systems.wb48.movement import MovementMixin


class StrategicMovementMixin(MovementMixin):
    """Strategic Movement phase actions (rule 11.0).

    Eligibility (11.12): unit must be sm_tagged. (Other 11.12 conditions —
    did not move, did not fight, did not build FF — are enforced at tagging
    time during the movement phase.)

    MP budget (11.21): movement_max - 2.
    No ZOC entry (11.22): allow_overrun=False in pathfinding.
    """

    def _legal_strategic_move_actions(
        self, state: GameState, player: Player,
    ) -> list[StrategicMoveAction]:
        actions: list[StrategicMoveAction] = []
        for unit in state.units_of(player):
            if not unit.strategic_movement:
                continue
            mp = max(0, unit.movement_max - 2)
            targets = self._move_targets_for_unit(
                state, player, unit, mp,
                allow_overrun=False, block_zoc_entry=True,
            )
            actions.extend(
                StrategicMoveAction(player=player, unit_id=unit.id, target=t)
                for t in targets
            )
        return actions

    def _apply_strategic_move(
        self, state: GameState, action: StrategicMoveAction,
    ) -> tuple[GameState, list[Event]]:
        """Execute strategic move: move unit, consume MP, clear SM tag.

        Engine guarantees action was in legal set, so we trust the target.
        """
        unit = state.get_unit(action.unit_id)
        if unit is None:
            return state, []
        old_pos = unit.position

        mp = max(0, unit.movement_max - 2)
        player = unit.player
        zoc_map = self.enemy_zoc_map(state, player)

        def cost_fn(f, t):
            c = self._movement_cost_with_zoc(state, f, t, player, zoc_map)
            return None if c == float('inf') else c

        blocked_fn = lambda c: self._is_blocked(state, c)
        reachable = reachable_hexes(
            old_pos, mp, cost_fn, blocked_fn,
            allow_first_step_overrun=False,
        )
        new_mp = reachable.get(action.target, 0)

        new_state = state.with_unit_moved(action.unit_id, action.target)
        moved_unit = new_state.get_unit(action.unit_id)
        # Consume SM tag and remaining MP — SM is one-shot per turn
        moved_unit = moved_unit.with_movement_left(new_mp).with_strategic_movement(False)
        new_state = new_state.with_unit(moved_unit)

        return new_state, [UnitMoved(
            unit_id=action.unit_id, from_hex=old_pos, to_hex=action.target,
        )]
