from __future__ import annotations

import pygame

from hexwar.core.actions import (
    AssignCplLossAction, ChooseRetreatSplitAction,
    DeclareAttackAction, EndPhaseAction,
    EntrenchAction, MoveAction, PursuitAction, ResolveBattleAction,
    RetreatUnitAction, SkipPursuitAction, UndeclareAttackAction,
)
from hexwar.core.battle import PostBattlePhase
from hexwar.core.engine import Engine
from hexwar.core.events import BattleResolved
from hexwar.core.hex import HexCoord
from hexwar.core.map import HexMap, TerrainLayer, TerrainType
from hexwar.core.rng import GameRNG
from hexwar.core.state import GameState, build_initial_state
from hexwar.core.unit import Unit
from hexwar.client.hex_render import (
    HEX_SIZE,
    PLAYER_COLORS,
    TERRAIN_COLORS,
    draw_arrow,
    draw_hex,
    draw_highlight,
    draw_terrain_labels,
    hex_to_pixel,
    pixel_to_hex,
)
from hexwar.systems.wb48.system import (
    PLAYER_A, PLAYER_B, SUB_PHASE_DECLARATION, SUB_PHASE_RESOLUTION, WB48System,
)
from hexwar.client.ui import UIButton

SCREEN_W = 1024
SCREEN_H = 700
BG_COLOR = (30, 30, 30)
UI_BG = (50, 50, 50)
UI_HEIGHT = 80
TEXT_COLOR = (220, 220, 220)
HIGHLIGHT_MOVE = (100, 200, 100, 80)
HIGHLIGHT_SELECT = (255, 255, 100, 120)
HIGHLIGHT_ZOC = (255, 50, 50, 60)
HIGHLIGHT_OBLIGATED = (255, 160, 0, 90)
HIGHLIGHT_SELECTED_ATTACKER = (255, 200, 50, 100)
BATTLE_ARROW_COLOR = (255, 200, 50)
BATTLE_ARROW_SELECTED = (255, 255, 150)
BATTLE_RESOLVED_COLOR = (100, 200, 100)
BATTLE_UNRESOLVED_COLOR = (255, 200, 50)

PANEL_BG = (40, 40, 50, 230)
PANEL_ITEM_BG = (60, 60, 70)
PANEL_ITEM_HOVER = (80, 100, 130)
PANEL_BORDER = (120, 120, 140)
EXHAUSTED_TINT = (80, 80, 80)

BTN_Y = SCREEN_H - UI_HEIGHT + 20
BTN_H = 40
BTN_W = 130


class PygameClient:
    def __init__(self, engine: Engine):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("HexWar Engine")
        self.clock = pygame.time.Clock()
        self.engine = engine
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_big = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 12)

        self.camera_offset = (SCREEN_W / 2 - 100, (SCREEN_H - UI_HEIGHT) / 2 - 50)
        self.selected_unit_id: str | None = None
        self.legal_moves: set[HexCoord] = set()
        self.enemy_zoc: set[HexCoord] = set()
        self.event_log: list[str] = []
        self.dragging = False
        self.drag_start = (0, 0)
        self.cam_start = (0.0, 0.0)

        self.unit_picker_open = False
        self.unit_picker_units: list[Unit] = []
        self.unit_picker_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.unit_picker_item_rects: list[pygame.Rect] = []
        self.unit_picker_hex: HexCoord | None = None
        self.can_entrench = False

        # Combat declaration UI state
        self.selected_attackers: list[str] = []
        self.selected_battle_id: int | None = None

        # Post-battle UI state
        self.retreat_split_open = False
        self.retreat_split_options: list[ChooseRetreatSplitAction] = []
        self.retreat_split_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.retreat_split_rects: list[pygame.Rect] = []
        self.post_battle_selected_unit: str | None = None

        self.buttons: list[UIButton] = []
        self._build_buttons()

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self._handle_left_click(event.pos)
                    elif event.button == 3:
                        self.dragging = True
                        self.drag_start = event.pos
                        self.cam_start = self.camera_offset
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 3:
                        self.dragging = False
                elif event.type == pygame.MOUSEMOTION:
                    if self.dragging:
                        dx = event.pos[0] - self.drag_start[0]
                        dy = event.pos[1] - self.drag_start[1]
                        self.camera_offset = (self.cam_start[0] + dx, self.cam_start[1] + dy)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.unit_picker_open:
                            self._close_picker()
                        else:
                            self._deselect()
                    elif event.key == pygame.K_e:
                        self._end_phase()
                    elif event.key == pygame.K_f:
                        self._do_entrench()
                    elif event.key == pygame.K_u:
                        self._undo()
                    elif event.key == pygame.K_d:
                        self._undeclare_selected()
                    elif event.key == pygame.K_s:
                        self._do_skip_pursuit()
                    elif event.key == pygame.K_q:
                        running = False

            self._draw()
            self.clock.tick(30)

        pygame.quit()

    def _handle_left_click(self, pos: tuple[int, int]) -> None:
        if self.unit_picker_open:
            self._handle_picker_click(pos)
            return
        if self.retreat_split_open:
            self._handle_retreat_split_click(pos)
            return

        if pos[1] > SCREEN_H - UI_HEIGHT:
            self._handle_ui_click(pos)
            return

        clicked = pixel_to_hex(
            pos[0] - self.camera_offset[0],
            pos[1] - self.camera_offset[1],
            HEX_SIZE,
        )

        if clicked not in self.engine.state.hex_map.all_coords():
            self._deselect()
            return

        phase = self.engine.current_phase
        sub_phase = self.engine.state.metadata.get("combat_sub_phase")

        if phase.phase_type == "movement":
            self._handle_movement_click(clicked, pos)
        elif phase.phase_type == "combat":
            if sub_phase == SUB_PHASE_DECLARATION:
                self._handle_declaration_click(clicked)
            elif sub_phase == SUB_PHASE_RESOLUTION:
                self._handle_resolution_click(clicked)
            else:
                self._deselect()
        else:
            self._deselect()

    def _handle_movement_click(self, clicked: HexCoord, pos: tuple[int, int]) -> None:
        """Handle clicks during movement phases: move selected unit or select a unit."""
        if self.selected_unit_id and clicked in self.legal_moves:
            self._do_move(clicked)
            return

        units_here = self.engine.state.units_at(clicked)
        friendly = [u for u in units_here if u.player == self.engine.state.active_player]
        if len(friendly) > 1:
            self._open_unit_picker(friendly, pos)
        elif friendly:
            self._select_unit(friendly[0].id)
        else:
            self._deselect()

    def _build_buttons(self) -> None:
        self.buttons = [
            UIButton(
                rect=pygame.Rect(SCREEN_W - 150, BTN_Y, BTN_W, BTN_H),
                label="End Phase",
                on_click=self._end_phase,
                is_enabled=self._can_end_phase,
            ),
            UIButton(
                rect=pygame.Rect(SCREEN_W - 300, BTN_Y, BTN_W, BTN_H),
                label="Entrench (F)",
                on_click=self._do_entrench,
                is_visible=lambda: self.can_entrench,
                bg_color=(80, 80, 120),
                border_color=(150, 150, 200),
            ),
        ]

    def _can_end_phase(self) -> bool:
        state = self.engine.state
        if self._in_declaration_mode():
            return state.metadata.get("declaration_complete", False)
        if self._in_resolution_mode():
            battles = state.metadata.get("battles", [])
            return all(b.resolved and b.post_phase == PostBattlePhase.DONE for b in battles)
        return True

    def _handle_ui_click(self, pos: tuple[int, int]) -> None:
        for btn in self.buttons:
            if btn.is_visible() and btn.is_enabled() and btn.contains(pos):
                btn.on_click()
                return

    def _draw_button(self, btn: UIButton) -> None:
        enabled = btn.is_enabled()
        bg = btn.bg_color if enabled else btn.disabled_bg
        border = btn.border_color if enabled else btn.disabled_border
        text_col = btn.text_color if enabled else btn.disabled_text
        pygame.draw.rect(self.screen, bg, btn.rect)
        pygame.draw.rect(self.screen, border, btn.rect, 2)
        text = self.font_big.render(btn.label, True, text_col)
        self.screen.blit(text, (btn.rect.x + 8, btn.rect.y + 10))

    def _open_unit_picker(self, units: list[Unit], click_pos: tuple[int, int], hex_coord: HexCoord | None = None) -> None:
        self.unit_picker_open = True
        self.unit_picker_units = units
        self.unit_picker_hex = hex_coord
        item_h = 30
        panel_w = 200
        panel_h = len(units) * item_h + 10
        px = min(click_pos[0], SCREEN_W - panel_w - 10)
        py = min(click_pos[1], SCREEN_H - UI_HEIGHT - panel_h - 10)
        self.unit_picker_rect = pygame.Rect(px, py, panel_w, panel_h)
        self.unit_picker_item_rects = []
        for i in range(len(units)):
            r = pygame.Rect(px + 5, py + 5 + i * item_h, panel_w - 10, item_h - 2)
            self.unit_picker_item_rects.append(r)

    def _handle_picker_click(self, pos: tuple[int, int]) -> None:
        for i, rect in enumerate(self.unit_picker_item_rects):
            if rect.collidepoint(pos):
                unit_id = self.unit_picker_units[i].id
                unit_name = self.unit_picker_units[i].name
                battle = self._get_active_post_battle()
                if battle and battle.post_phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL, PostBattlePhase.MANDATORY_CPL):
                    self._close_picker()
                    player = self.engine.state.active_player
                    action = AssignCplLossAction(player=player, battle_id=battle.id, unit_id=unit_id)
                    events = self.engine.submit_action(action)
                    self.event_log.append(f"Unit {unit_name} destroyed (CPL)")
                    for e in events:
                        self.event_log.append(str(e))
                    self.post_battle_selected_unit = None
                elif battle and battle.post_phase == PostBattlePhase.PURSUIT:
                    self._close_picker()
                    self.post_battle_selected_unit = unit_id
                elif self._in_declaration_mode():
                    committed = self.engine.state.metadata.get("committed_attackers", set())
                    if unit_id in committed:
                        return
                    self._close_picker()
                    self._toggle_attacker_selection(unit_id, False)
                else:
                    self._close_picker()
                    self._select_unit(unit_id)
                return
        self._close_picker()

    def _close_picker(self) -> None:
        self.unit_picker_open = False
        self.unit_picker_units = []
        self.unit_picker_item_rects = []

    def _select_unit(self, unit_id: str) -> None:
        self.selected_unit_id = unit_id
        self._compute_legal_targets()

    def _deselect(self) -> None:
        self.selected_unit_id = None
        self.legal_moves.clear()
        self.enemy_zoc.clear()
        self._close_picker()
        self.selected_attackers.clear()
        self.selected_battle_id = None

    # ------------------------------------------------------------------
    # Combat declaration mode
    # ------------------------------------------------------------------

    def _in_declaration_mode(self) -> bool:
        return self.engine.state.metadata.get("combat_sub_phase") == SUB_PHASE_DECLARATION

    def _in_resolution_mode(self) -> bool:
        return self.engine.state.metadata.get("combat_sub_phase") == SUB_PHASE_RESOLUTION

    def _handle_declaration_click(self, clicked: HexCoord) -> None:
        """Handle clicks during combat declaration sub-phase."""
        player = self.engine.state.active_player
        shift = pygame.key.get_mods() & pygame.KMOD_SHIFT

        units_here = self.engine.state.units_at(clicked)
        enemies = [u for u in units_here if u.player != player]
        battles = self.engine.state.metadata.get("battles", [])

        # If we have attackers selected and clicked on enemy hex — declare/merge attack
        if enemies and self.selected_attackers:
            self._do_declare_attack(clicked)
            return

        # If a battle is selected and clicked on a new enemy hex — extend defender hexes (fan-out)
        if enemies and self.selected_battle_id is not None:
            self._extend_battle_defenders(clicked)
            return

        # Check if clicked on a declared battle's defender hex (to select that battle)
        for battle in battles:
            if clicked in battle.defender_hexes:
                self.selected_battle_id = battle.id
                self.selected_attackers.clear()
                return

        # Check if clicked on a friendly unit — toggle multi-select
        friendly = [u for u in units_here if u.player == player]
        committed = self.engine.state.metadata.get("committed_attackers", set())

        if friendly:
            uncommitted = [u for u in friendly if u.id not in committed]

            # Multiple friendly on hex with at least one uncommitted → picker
            # (picker shows committed grayed with [ATK])
            if len(friendly) > 1 and uncommitted and not shift:
                px, py = hex_to_pixel(clicked, HEX_SIZE)
                screen_pos = (int(px + self.camera_offset[0]), int(py + self.camera_offset[1]))
                self._open_unit_picker(friendly, screen_pos, hex_coord=clicked)
                self.selected_battle_id = None
                return

            # All committed here → show battle they belong to
            committed_here = [u for u in friendly if u.id in committed]
            if committed_here and not shift:
                for battle in battles:
                    if committed_here[0].id in battle.attacker_ids:
                        self.selected_battle_id = battle.id
                        self.selected_attackers.clear()
                        return

            if uncommitted:
                self._toggle_attacker_selection(uncommitted[0].id, shift)
                self.selected_battle_id = None
                return

        # Clicked empty — deselect
        self.selected_attackers.clear()
        self.selected_battle_id = None

    def _toggle_attacker_selection(self, uid: str, shift: bool) -> None:
        if shift:
            if uid in self.selected_attackers:
                self.selected_attackers.remove(uid)
            else:
                self.selected_attackers.append(uid)
        else:
            if uid in self.selected_attackers:
                self.selected_attackers.remove(uid)
            elif not self.selected_attackers:
                self.selected_attackers = [uid]
            else:
                self.selected_attackers = [uid]

    def _redeclare_with_rollback(
        self,
        old_battle: dict | None,
        attacker_ids: tuple[str, ...],
        defender_hexes: tuple[HexCoord, ...],
        error_msg: str,
    ) -> bool:
        """Undeclare old_battle (if any), declare new action, restore on failure."""
        player = self.engine.state.active_player
        if old_battle is not None:
            self.engine.submit_action(
                UndeclareAttackAction(player=player, battle_id=old_battle.id)
            )
        action = DeclareAttackAction(
            player=player, attacker_ids=attacker_ids, defender_hexes=defender_hexes,
        )
        if any(a == action for a in self.engine.get_legal_actions()):
            events = self.engine.submit_action(action)
            for e in events:
                self.event_log.append(str(e))
            return True
        if old_battle is not None:
            self.engine.submit_action(DeclareAttackAction(
                player=player,
                attacker_ids=tuple(old_battle.attacker_ids),
                defender_hexes=tuple(old_battle.defender_hexes),
            ))
        self.event_log.append(error_msg)
        return False

    def _do_declare_attack(self, target_hex: HexCoord) -> None:
        attacker_unit = self.engine.state.get_unit(self.selected_attackers[0]) if self.selected_attackers else None
        attacker_hex = attacker_unit.position if attacker_unit else None

        battles = self.engine.state.metadata.get("battles", [])
        existing = next(
            (b for b in battles if target_hex in b.defender_hexes), None
        )
        if existing:
            merged = tuple(sorted(set(existing.attacker_ids) | set(self.selected_attackers)))
            defender_hexes = tuple(existing.defender_hexes)
        else:
            merged = tuple(sorted(self.selected_attackers))
            defender_hexes = (target_hex,)
        if self._redeclare_with_rollback(existing, merged, defender_hexes, "[INVALID] Cannot declare that attack"):
            self.selected_attackers.clear()
            self._reopen_picker_if_needed(attacker_hex)

    def _reopen_picker_if_needed(self, attacker_hex: HexCoord | None) -> None:
        if attacker_hex is None:
            return
        player = self.engine.state.active_player
        friendly = [u for u in self.engine.state.units_at(attacker_hex) if u.player == player]
        if len(friendly) < 2:
            return
        px, py = hex_to_pixel(attacker_hex, HEX_SIZE)
        screen_pos = (int(px + self.camera_offset[0]), int(py + self.camera_offset[1]))
        self._open_unit_picker(friendly, screen_pos, hex_coord=attacker_hex)

    def _extend_battle_defenders(self, target_hex: HexCoord) -> None:
        """Add a new defender hex to the currently selected battle (fan-out)."""
        battles = self.engine.state.metadata.get("battles", [])
        battle = next((b for b in battles if b.id == self.selected_battle_id), None)
        if battle is None:
            return
        if target_hex in battle.defender_hexes:
            return
        new_defender_hexes = tuple(sorted(set(battle.defender_hexes) | {target_hex}))
        if self._redeclare_with_rollback(
            battle, tuple(battle.attacker_ids), new_defender_hexes,
            "[INVALID] Cannot extend battle to that hex",
        ):
            self.selected_battle_id = None

    def _undeclare_selected(self) -> None:
        """Undeclare the currently selected battle (press D)."""
        if not self._in_declaration_mode():
            return
        if self.selected_battle_id is None:
            return
        action = UndeclareAttackAction(
            player=self.engine.state.active_player,
            battle_id=self.selected_battle_id,
        )
        events = self.engine.submit_action(action)
        for e in events:
            self.event_log.append(str(e))
        self.selected_battle_id = None

    # ------------------------------------------------------------------
    # Combat resolution mode
    # ------------------------------------------------------------------

    def _handle_resolution_click(self, clicked: HexCoord) -> None:
        """Handle clicks during combat resolution sub-phase."""
        state = self.engine.state
        battles = state.metadata.get("battles", [])

        active_post = self._get_active_post_battle()
        if active_post:
            self._handle_post_battle_click(clicked, active_post)
            return

        for battle in battles:
            if battle.resolved:
                continue
            if clicked in battle.defender_hexes:
                self._do_resolve_battle(battle.id)
                return
            for uid in battle.attacker_ids:
                unit = state.get_unit(uid)
                if unit and unit.position == clicked:
                    self._do_resolve_battle(battle.id)
                    return

    def _get_active_post_battle(self):
        """Find battle in active post-battle phase."""
        for battle in self.engine.state.metadata.get("battles", []):
            if battle.resolved and battle.post_phase != PostBattlePhase.DONE:
                return battle
        return None

    def _handle_post_battle_click(self, clicked: HexCoord, battle) -> None:
        """Route clicks based on current post-battle phase."""
        state = self.engine.state
        player = state.active_player
        phase = battle.post_phase

        if phase in (PostBattlePhase.ATTACKER_SPLIT, PostBattlePhase.DEFENDER_SPLIT):
            return

        if phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL, PostBattlePhase.MANDATORY_CPL):
            units_here = state.units_at(clicked)
            legal = self.engine.get_legal_actions()
            eligible = [
                u for u in units_here
                if any(a == AssignCplLossAction(player=player, battle_id=battle.id, unit_id=u.id) for a in legal)
            ]
            if len(eligible) > 1:
                px, py = hex_to_pixel(clicked, HEX_SIZE)
                screen_pos = (int(px + self.camera_offset[0]), int(py + self.camera_offset[1]))
                self._open_unit_picker(eligible, screen_pos, hex_coord=clicked)
                return
            if eligible:
                action = AssignCplLossAction(player=player, battle_id=battle.id, unit_id=eligible[0].id)
                events = self.engine.submit_action(action)
                self.event_log.append(f"Unit {eligible[0].name} destroyed (CPL)")
                for e in events:
                    self.event_log.append(str(e))
                self.post_battle_selected_unit = None
                return

        if phase in (PostBattlePhase.ATTACKER_RETREAT, PostBattlePhase.DEFENDER_RETREAT):
            if self.post_battle_selected_unit:
                action = RetreatUnitAction(
                    player=player, battle_id=battle.id,
                    unit_id=self.post_battle_selected_unit, target=clicked,
                )
                legal = self.engine.get_legal_actions()
                if any(a == action for a in legal):
                    events = self.engine.submit_action(action)
                    unit = state.get_unit(self.post_battle_selected_unit)
                    self.event_log.append(f"{unit.name} retreats to {clicked}")
                    for e in events:
                        self.event_log.append(str(e))
                    self.post_battle_selected_unit = None
                    return
            # Select a unit that needs to retreat
            units_here = state.units_at(clicked)
            for unit in units_here:
                if unit.id in battle.units_needing_retreat:
                    self.post_battle_selected_unit = unit.id
                    return
            self.post_battle_selected_unit = None

        if phase == PostBattlePhase.PURSUIT:
            if self.post_battle_selected_unit:
                action = PursuitAction(
                    player=player, battle_id=battle.id,
                    unit_id=self.post_battle_selected_unit, target=clicked,
                )
                legal = self.engine.get_legal_actions()
                if any(a == action for a in legal):
                    events = self.engine.submit_action(action)
                    self.event_log.append(f"Pursuit to {clicked}")
                    for e in events:
                        self.event_log.append(str(e))
                    self.post_battle_selected_unit = None
                    return
            # Select pursuing unit (may belong to either player)
            pursuer_ids = battle.attacker_ids if battle.pursuing_side == "attacker" else battle.defender_ids
            eligible = [
                u for u in state.units_at(clicked)
                if u.id in pursuer_ids and u.id not in battle.units_pursued
            ]
            if len(eligible) > 1:
                px, py = hex_to_pixel(clicked, HEX_SIZE)
                screen_pos = (int(px + self.camera_offset[0]), int(py + self.camera_offset[1]))
                self._open_unit_picker(eligible, screen_pos)
                return
            if eligible:
                self.post_battle_selected_unit = eligible[0].id
                return
            self.post_battle_selected_unit = None

    def _open_retreat_split(self) -> None:
        """Open retreat split option panel."""
        legal = self.engine.get_legal_actions()
        self.retreat_split_options = [
            a for a in legal if isinstance(a, ChooseRetreatSplitAction)
        ]
        if not self.retreat_split_options:
            return
        self.retreat_split_open = True
        # Build rects for panel
        panel_w = 260
        item_h = 30
        panel_h = len(self.retreat_split_options) * item_h + 20
        panel_x = SCREEN_W // 2 - panel_w // 2
        panel_y = (SCREEN_H - UI_HEIGHT) // 2 - panel_h // 2
        self.retreat_split_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        self.retreat_split_rects = []
        for i in range(len(self.retreat_split_options)):
            r = pygame.Rect(panel_x + 10, panel_y + 10 + i * item_h, panel_w - 20, item_h - 4)
            self.retreat_split_rects.append(r)

    def _handle_retreat_split_click(self, pos: tuple[int, int]) -> None:
        """Handle click on retreat split panel."""
        for i, rect in enumerate(self.retreat_split_rects):
            if rect.collidepoint(pos):
                action = self.retreat_split_options[i]
                events = self.engine.submit_action(action)
                self.event_log.append(
                    f"Split: retreat {action.retreat_hexes} hex, lose {action.unit_losses} unit(s)"
                )
                for e in events:
                    self.event_log.append(str(e))
                self.retreat_split_open = False
                self.retreat_split_options = []
                return
        # Click outside panel — close
        if not self.retreat_split_rect.collidepoint(pos):
            self.retreat_split_open = False

    def _do_skip_pursuit(self) -> None:
        """Skip pursuit for active battle."""
        battle = self._get_active_post_battle()
        if not battle or battle.post_phase != PostBattlePhase.PURSUIT:
            return
        action = SkipPursuitAction(player=self.engine.state.active_player, battle_id=battle.id)
        legal = self.engine.get_legal_actions()
        if any(a == action for a in legal):
            events = self.engine.submit_action(action)
            self.event_log.append("Pursuit skipped")
            for e in events:
                self.event_log.append(str(e))
            self.post_battle_selected_unit = None

    def _post_battle_controls_text(self, battle) -> str:
        phase = battle.post_phase
        phase_names = {
            PostBattlePhase.ATTACKER_SPLIT: "ATTACKER SPLIT",
            PostBattlePhase.DEFENDER_SPLIT: "DEFENDER SPLIT",
            PostBattlePhase.ATTACKER_CPL: "ATTACKER CPL",
            PostBattlePhase.DEFENDER_CPL: "DEFENDER CPL",
            PostBattlePhase.MANDATORY_CPL: "MANDATORY CPL",
            PostBattlePhase.ATTACKER_RETREAT: "ATTACKER RETREAT",
            PostBattlePhase.DEFENDER_RETREAT: "DEFENDER RETREAT",
            PostBattlePhase.PURSUIT: "PURSUIT",
        }
        name = phase_names.get(phase, str(phase))
        if phase in (PostBattlePhase.ATTACKER_SPLIT, PostBattlePhase.DEFENDER_SPLIT):
            return f"Battle #{battle.id}  |  {name}  |  Choose retreat/loss split"
        if phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL, PostBattlePhase.MANDATORY_CPL):
            return f"Battle #{battle.id}  |  {name}  |  Click unit to destroy  |  {battle.remaining_cpl_to_assign} remaining"
        if phase in (PostBattlePhase.ATTACKER_RETREAT, PostBattlePhase.DEFENDER_RETREAT):
            remaining = len([uid for uid in battle.units_needing_retreat if self.engine.state.get_unit(uid)])
            return f"Battle #{battle.id}  |  {name}  |  Click unit then target hex  |  {remaining} unit(s), {battle.remaining_retreat_steps} step(s)"
        if phase == PostBattlePhase.PURSUIT:
            pursuer_ids = battle.attacker_ids if battle.pursuing_side == "attacker" else battle.defender_ids
            remaining = sum(1 for uid in pursuer_ids if uid not in battle.units_pursued and self.engine.state.get_unit(uid))
            return f"Battle #{battle.id}  |  {name}  |  Click unit then target  |  {remaining} unit(s) left  |  S: skip all"
        return f"Battle #{battle.id}  |  {name}"

    def _do_resolve_battle(self, battle_id: int) -> None:
        """Submit ResolveBattleAction for the given battle."""
        action = ResolveBattleAction(
            player=self.engine.state.active_player,
            battle_id=battle_id,
        )
        legal = self.engine.get_legal_actions()
        if any(a == action for a in legal):
            events = self.engine.submit_action(action)
            for e in events:
                if isinstance(e, BattleResolved):
                    self.event_log.append(
                        f"Battle #{e.battle_id}: {e.attack_strength}v{e.defense_strength} "
                        f"dice={e.dice_roll[0]}+{e.dice_roll[1]}={e.dice_total} → {e.result}"
                    )
                else:
                    self.event_log.append(str(e))
        else:
            self.event_log.append("[INVALID] Cannot resolve that battle")

    def _compute_legal_targets(self) -> None:
        self.legal_moves.clear()
        self.enemy_zoc.clear()
        self.can_entrench = False
        if not self.selected_unit_id:
            return

        unit = self.engine.state.get_unit(self.selected_unit_id)
        if unit:
            zoc_map = self.engine.system.enemy_zoc_map(
                self.engine.state, unit.player
            )
            self.enemy_zoc = set(zoc_map.keys())

        legal = self.engine.get_legal_actions()
        for action in legal:
            if isinstance(action, MoveAction) and action.unit_id == self.selected_unit_id:
                self.legal_moves.add(action.target)
            elif isinstance(action, EntrenchAction) and action.unit_id == self.selected_unit_id:
                self.can_entrench = True

    def _do_move(self, target: HexCoord) -> None:
        action = MoveAction(
            player=self.engine.state.active_player,
            unit_id=self.selected_unit_id,
            target=target,
        )
        events = self.engine.submit_action(action)
        for e in events:
            self.event_log.append(str(e))
        self._select_unit(self.selected_unit_id)

    def _do_entrench(self) -> None:
        if not self.can_entrench or not self.selected_unit_id:
            return
        action = EntrenchAction(
            player=self.engine.state.active_player,
            unit_id=self.selected_unit_id,
        )
        events = self.engine.submit_action(action)
        for e in events:
            self.event_log.append(str(e))
        self._select_unit(self.selected_unit_id)

    def _end_phase(self) -> None:
        if not self._can_end_phase():
            if self._in_declaration_mode():
                self.event_log.append("[BLOCKED] Must declare all obligated attacks first")
            elif self._in_resolution_mode():
                battles = self.engine.state.metadata.get("battles", [])
                unresolved = sum(1 for b in battles if not b.resolved)
                in_post = sum(1 for b in battles if b.resolved and b.post_phase != PostBattlePhase.DONE)
                if unresolved:
                    self.event_log.append(f"[BLOCKED] {unresolved} battle(s) still unresolved")
                elif in_post:
                    self.event_log.append(f"[BLOCKED] {in_post} battle(s) in post-battle phase")
            return
        action = EndPhaseAction(player=self.engine.state.active_player)
        events = self.engine.submit_action(action)
        for e in events:
            self.event_log.append(str(e))
        self._deselect()

    def _undo(self) -> None:
        result = self.engine.undo()
        if result:
            self.event_log.append("[UNDO]")
            self._deselect()

    def _draw(self) -> None:
        self.screen.fill(BG_COLOR)
        self._draw_map()
        self._draw_highlights()
        self._draw_units()
        if self._in_declaration_mode():
            self._draw_declaration_overlay()
        if self._in_resolution_mode():
            self._draw_resolution_overlay()
            self._draw_post_battle_highlights()
        self._draw_ui()
        if self.unit_picker_open:
            self._draw_unit_picker()
        if self.retreat_split_open:
            self._draw_retreat_split_panel()
        # Auto-open split panel when entering split phase
        battle = self._get_active_post_battle()
        if battle and battle.post_phase in (PostBattlePhase.ATTACKER_SPLIT, PostBattlePhase.DEFENDER_SPLIT):
            if not self.retreat_split_open:
                self._open_retreat_split()
        elif self.retreat_split_open:
            self.retreat_split_open = False
        pygame.display.flip()

    def _draw_unit_picker(self) -> None:
        panel_surf = pygame.Surface(
            (self.unit_picker_rect.width, self.unit_picker_rect.height), pygame.SRCALPHA
        )
        panel_surf.fill(PANEL_BG)
        self.screen.blit(panel_surf, self.unit_picker_rect.topleft)
        pygame.draw.rect(self.screen, PANEL_BORDER, self.unit_picker_rect, 1)

        mouse_pos = pygame.mouse.get_pos()
        remaining_mp = self.engine.state.metadata.get("remaining_mp", {})
        committed = self.engine.state.metadata.get("committed_attackers", set()) if self._in_declaration_mode() else set()

        for i, (unit, rect) in enumerate(zip(self.unit_picker_units, self.unit_picker_item_rects)):
            is_committed = unit.id in committed
            hovered = rect.collidepoint(mouse_pos) and not is_committed
            bg = (80, 80, 80) if is_committed else (PANEL_ITEM_HOVER if hovered else PANEL_ITEM_BG)
            pygame.draw.rect(self.screen, bg, rect)

            color = PLAYER_COLORS.get(unit.player, (200, 200, 200))
            pygame.draw.circle(self.screen, color, (rect.x + 14, rect.centery), 8)

            mp_left = remaining_mp.get(unit.id, unit.stats.get("movement", 1))
            suffix = "  [ATK]" if is_committed else ""
            info = f"{unit.name}  MP:{mp_left}{suffix}"
            text_color = (120, 120, 120) if is_committed else TEXT_COLOR
            text = self.font_small.render(info, True, text_color)
            self.screen.blit(text, (rect.x + 28, rect.centery - text.get_height() // 2))

    def _draw_retreat_split_panel(self) -> None:
        """Draw retreat/loss split choice panel."""
        if not self.retreat_split_options:
            return
        panel_surf = pygame.Surface(
            (self.retreat_split_rect.width, self.retreat_split_rect.height), pygame.SRCALPHA
        )
        panel_surf.fill(PANEL_BG)
        self.screen.blit(panel_surf, self.retreat_split_rect.topleft)
        pygame.draw.rect(self.screen, PANEL_BORDER, self.retreat_split_rect, 1)

        mouse_pos = pygame.mouse.get_pos()
        side = self.retreat_split_options[0].side if self.retreat_split_options else ""
        title = self.font.render(f"Choose {side} split:", True, TEXT_COLOR)
        self.screen.blit(title, (self.retreat_split_rect.x + 10, self.retreat_split_rect.y - 18))

        for i, (opt, rect) in enumerate(zip(self.retreat_split_options, self.retreat_split_rects)):
            hovered = rect.collidepoint(mouse_pos)
            bg = PANEL_ITEM_HOVER if hovered else PANEL_ITEM_BG
            pygame.draw.rect(self.screen, bg, rect)
            label = f"Retreat {opt.retreat_hexes} hex  |  Lose {opt.unit_losses} unit(s)"
            text = self.font_small.render(label, True, TEXT_COLOR)
            self.screen.blit(text, (rect.x + 10, rect.centery - text.get_height() // 2))

    def _draw_post_battle_highlights(self) -> None:
        """Draw highlights for post-battle interactions."""
        battle = self._get_active_post_battle()
        if not battle:
            return
        state = self.engine.state
        phase = battle.post_phase

        if phase in (PostBattlePhase.ATTACKER_CPL, PostBattlePhase.DEFENDER_CPL, PostBattlePhase.MANDATORY_CPL):
            # Highlight units eligible for CPL loss in red
            if phase == PostBattlePhase.ATTACKER_CPL:
                unit_ids = battle.attacker_ids
            elif phase == PostBattlePhase.DEFENDER_CPL:
                unit_ids = battle.defender_ids
            else:
                if battle.attacker_mandatory_cpl > 0:
                    unit_ids = battle.attacker_ids
                else:
                    unit_ids = battle.defender_ids
            for uid in unit_ids:
                unit = state.get_unit(uid)
                if unit:
                    draw_highlight(self.screen, unit.position, (255, 50, 50, 100), self.camera_offset)

        elif phase in (PostBattlePhase.ATTACKER_RETREAT, PostBattlePhase.DEFENDER_RETREAT):
            # Highlight units needing retreat in orange
            for uid in battle.units_needing_retreat:
                unit = state.get_unit(uid)
                if unit:
                    color = (255, 200, 50, 100) if uid != self.post_battle_selected_unit else (255, 255, 100, 140)
                    draw_highlight(self.screen, unit.position, color, self.camera_offset)
            # If unit selected, highlight valid retreat targets in green
            if self.post_battle_selected_unit:
                legal = self.engine.get_legal_actions()
                for a in legal:
                    if isinstance(a, RetreatUnitAction) and a.unit_id == self.post_battle_selected_unit:
                        draw_highlight(self.screen, a.target, (100, 200, 100, 80), self.camera_offset)

        elif phase == PostBattlePhase.PURSUIT:
            selected = self.post_battle_selected_unit
            pursuer_ids = battle.attacker_ids if battle.pursuing_side == "attacker" else battle.defender_ids
            for uid in pursuer_ids:
                if uid in battle.units_pursued:
                    continue
                unit = state.get_unit(uid)
                if unit:
                    color = (150, 200, 255, 140) if uid == selected else (100, 150, 255, 100)
                    draw_highlight(self.screen, unit.position, color, self.camera_offset)
            # Highlight pursuit targets in green
            active_uid = selected
            if active_uid:
                legal = self.engine.get_legal_actions()
                for a in legal:
                    if isinstance(a, PursuitAction) and a.unit_id == active_uid:
                        draw_highlight(self.screen, a.target, (100, 200, 100, 80), self.camera_offset)

    def _draw_map(self) -> None:
        state = self.engine.state
        label_font = pygame.font.SysFont("consolas", 11)
        for coord, layers in state.hex_map.terrain.items():
            color = TERRAIN_COLORS.get(TerrainType.PLAIN)
            if layers:
                color = TERRAIN_COLORS.get(layers[0].type, color)
            draw_hex(self.screen, coord, color, self.camera_offset)
            if layers and (len(layers) > 1 or layers[0].type != TerrainType.PLAIN):
                draw_terrain_labels(self.screen, coord, layers, self.camera_offset, font=label_font)

    def _draw_highlights(self) -> None:
        entrenched = self.engine.state.metadata.get("entrenched", {})
        for coord, owner in entrenched.items():
            if coord in self.engine.state.hex_map.all_coords():
                color = (80, 180, 80, 60) if owner == self.engine.state.active_player else (180, 80, 80, 60)
                draw_highlight(self.screen, coord, color, self.camera_offset)

        for coord in self.enemy_zoc:
            if coord in self.engine.state.hex_map.all_coords():
                draw_highlight(self.screen, coord, HIGHLIGHT_ZOC, self.camera_offset)

        if self.selected_unit_id:
            unit = self.engine.state.get_unit(self.selected_unit_id)
            if unit:
                draw_highlight(self.screen, unit.position, HIGHLIGHT_SELECT, self.camera_offset)

        for coord in self.legal_moves:
            draw_highlight(self.screen, coord, HIGHLIGHT_MOVE, self.camera_offset)

        # Declaration mode: highlight obligated units and selected attackers
        if self._in_declaration_mode():
            state = self.engine.state
            obligated_attackers = state.metadata.get("obligated_attackers", set())
            committed_attackers = state.metadata.get("committed_attackers", set())
            obligated_enemies = state.metadata.get("obligated_enemies", set())
            committed_defenders = state.metadata.get("committed_defenders", set())

            # Orange highlight on units that still need to attack
            for uid in obligated_attackers - committed_attackers:
                unit = state.get_unit(uid)
                if unit:
                    draw_highlight(self.screen, unit.position, HIGHLIGHT_OBLIGATED, self.camera_offset)

            # Orange highlight on enemies that still need to be attacked
            for uid in obligated_enemies - committed_defenders:
                unit = state.get_unit(uid)
                if unit:
                    draw_highlight(self.screen, unit.position, HIGHLIGHT_OBLIGATED, self.camera_offset)

            # Yellow highlight on currently selected attackers
            for uid in self.selected_attackers:
                unit = state.get_unit(uid)
                if unit:
                    draw_highlight(self.screen, unit.position, HIGHLIGHT_SELECTED_ATTACKER, self.camera_offset)

    def _is_unit_exhausted(self, unit: Unit) -> bool:
        remaining_mp = self.engine.state.metadata.get("remaining_mp", {})
        return remaining_mp.get(unit.id, -1) == 0

    def _draw_units(self) -> None:
        state = self.engine.state
        units_by_hex: dict[HexCoord, list[Unit]] = {}
        for unit in state.units.values():
            units_by_hex.setdefault(unit.position, []).append(unit)

        for coord, units in units_by_hex.items():
            px, py = hex_to_pixel(coord, HEX_SIZE)
            base_sx = px + self.camera_offset[0]
            base_sy = py + self.camera_offset[1]

            if len(units) > 1:
                stack_text = self.font_small.render(f"x{len(units)}", True, (255, 255, 100))
                self.screen.blit(stack_text, (int(base_sx) + 10, int(base_sy) - 22))

            for i, unit in enumerate(units):
                offset_x = i * 4
                offset_y = -i * 4
                sx = base_sx + offset_x
                sy = base_sy + offset_y

                exhausted = self._is_unit_exhausted(unit)
                color = PLAYER_COLORS.get(unit.player, (200, 200, 200))
                if exhausted:
                    color = tuple((c + g) // 2 for c, g in zip(color, EXHAUSTED_TINT))

                pygame.draw.circle(self.screen, color, (int(sx), int(sy)), 14)
                outline_color = (120, 120, 120) if exhausted else (255, 255, 255)
                pygame.draw.circle(self.screen, outline_color, (int(sx), int(sy)), 14, 1)

                label = unit.type_id[0].upper()
                text = self.font.render(label, True, (255, 255, 255))
                self.screen.blit(text, (int(sx) - text.get_width() // 2, int(sy) - text.get_height() // 2))

                str_val = str(unit.stats.get("strength", "?"))
                str_text = self.font.render(str_val, True, (255, 255, 200))
                self.screen.blit(str_text, (int(sx) - str_text.get_width() // 2, int(sy) + 14))

                if exhausted:
                    pygame.draw.line(self.screen, (200, 60, 60),
                                     (int(sx) - 10, int(sy) - 10), (int(sx) + 10, int(sy) + 10), 2)
                    pygame.draw.line(self.screen, (200, 60, 60),
                                     (int(sx) + 10, int(sy) - 10), (int(sx) - 10, int(sy) + 10), 2)

            entrenched = state.metadata.get("entrenched", {})
            if coord in entrenched:
                pygame.draw.circle(self.screen, (220, 200, 50),
                                   (int(base_sx), int(base_sy) + 20), 5)
                pygame.draw.circle(self.screen, (255, 240, 100),
                                   (int(base_sx), int(base_sy) + 20), 5, 1)

    def _draw_battle_arrows(
        self, state: GameState, battle, arrow_color: tuple,
    ) -> tuple[float, float, str] | None:
        """Draw arrows for a battle, return (def_cx, def_cy, ratio_text) or None."""
        attacker_ids = battle.attacker_ids
        defender_hexes = battle.defender_hexes
        defender_ids = battle.defender_ids

        if not defender_hexes:
            return None

        def_px_sum, def_py_sum = 0.0, 0.0
        for dh in defender_hexes:
            dpx, dpy = hex_to_pixel(dh, HEX_SIZE)
            def_px_sum += dpx + self.camera_offset[0]
            def_py_sum += dpy + self.camera_offset[1]
        def_cx = def_px_sum / len(defender_hexes)
        def_cy = def_py_sum / len(defender_hexes)

        for uid in attacker_ids:
            unit = state.get_unit(uid)
            if not unit:
                continue
            apx, apy = hex_to_pixel(unit.position, HEX_SIZE)
            ax = apx + self.camera_offset[0]
            ay = apy + self.camera_offset[1]
            draw_arrow(self.screen, (ax, ay), (def_cx, def_cy), color=arrow_color, width=2)

        atk_str = sum(
            state.get_unit(uid).stats.get("strength", 1)
            for uid in attacker_ids if state.get_unit(uid)
        )
        def_str = sum(
            state.get_unit(uid).stats.get("strength", 1)
            for uid in defender_ids if state.get_unit(uid)
        )
        ratio_text = f"{atk_str}:{def_str}" if def_str > 0 else "auto"
        return def_cx, def_cy, ratio_text

    def _draw_battle_label(
        self, text: str, center: tuple[float, float], color: tuple, font=None,
    ) -> None:
        font = font or self.font
        label = font.render(text, True, color)
        label_x = int(center[0]) + 16
        label_y = int(center[1]) - 20
        bg_rect = pygame.Rect(label_x - 2, label_y - 1, label.get_width() + 4, label.get_height() + 2)
        pygame.draw.rect(self.screen, (30, 30, 30), bg_rect)
        self.screen.blit(label, (label_x, label_y))

    def _draw_declaration_overlay(self) -> None:
        state = self.engine.state
        for battle in state.metadata.get("battles", []):
            is_selected = (battle.id == self.selected_battle_id)
            arrow_color = BATTLE_ARROW_SELECTED if is_selected else BATTLE_ARROW_COLOR

            result = self._draw_battle_arrows(state, battle, arrow_color)
            if result is None:
                continue
            def_cx, def_cy, ratio_text = result
            self._draw_battle_label(ratio_text, (def_cx, def_cy), arrow_color)

            if is_selected:
                for dh in battle.defender_hexes:
                    draw_highlight(self.screen, dh, (255, 255, 100, 60), self.camera_offset)

    def _draw_resolution_overlay(self) -> None:
        state = self.engine.state
        for battle in state.metadata.get("battles", []):
            resolved = battle.resolved
            arrow_color = BATTLE_RESOLVED_COLOR if resolved else BATTLE_UNRESOLVED_COLOR

            result = self._draw_battle_arrows(state, battle, arrow_color)
            if result is None:
                continue
            def_cx, def_cy, ratio_text = result

            if resolved:
                dice = battle.dice_roll or (0, 0)
                res = battle.result or "?"
                label_text = f"#{battle.id} {ratio_text} [{dice[0]}+{dice[1]}={sum(dice)}] {res}"
            else:
                label_text = f"#{battle.id} {ratio_text} [click to resolve]"
            self._draw_battle_label(label_text, (def_cx, def_cy), arrow_color, self.font_small)

            if not resolved:
                for dh in battle.defender_hexes:
                    draw_highlight(self.screen, dh, (255, 200, 50, 60), self.camera_offset)

    def _draw_ui(self) -> None:
        ui_rect = pygame.Rect(0, SCREEN_H - UI_HEIGHT, SCREEN_W, UI_HEIGHT)
        pygame.draw.rect(self.screen, UI_BG, ui_rect)

        state = self.engine.state
        phase = self.engine.current_phase

        info = f"Turn {state.turn}  |  {phase.name}  |  Active: {state.active_player}"
        info_surf = self.font_big.render(info, True, TEXT_COLOR)
        self.screen.blit(info_surf, (15, SCREEN_H - UI_HEIGHT + 10))

        if self._in_declaration_mode():
            n_battles = len(state.metadata.get("battles", []))
            complete = state.metadata.get("declaration_complete", False)
            status = "READY" if complete else "INCOMPLETE"
            if self.selected_battle_id is not None:
                controls = (
                    f"Battle #{self.selected_battle_id} selected  |  D: cancel attack  "
                    f"|  ESC: deselect  |  Battles: {n_battles}  [{status}]"
                )
            else:
                controls = (
                    f"Shift+Click: multi-select attackers  |  Click enemy: declare  "
                    f"|  Click battle: select  |  D: cancel  |  E: end  |  Battles: {n_battles}  [{status}]"
                )
        elif self._in_resolution_mode():
            battles = state.metadata.get("battles", [])
            active_pb = self._get_active_post_battle()
            if active_pb:
                controls = self._post_battle_controls_text(active_pb)
            else:
                unresolved = sum(1 for b in battles if not b.resolved)
                controls = (
                    f"RESOLUTION  |  Click battle to resolve  |  "
                    f"{unresolved}/{len(battles)} remaining  |  E: end phase"
                )
        else:
            controls = "Click: select/move/attack  |  F: entrench  |  E: end phase  |  U: undo  |  RMB: pan  |  Q: quit"
        ctrl_surf = self.font.render(controls, True, (150, 150, 150))
        self.screen.blit(ctrl_surf, (15, SCREEN_H - UI_HEIGHT + 35))

        if self.event_log:
            last = self.event_log[-1][:80]
            log_surf = self.font.render(last, True, (180, 180, 100))
            self.screen.blit(log_surf, (15, SCREEN_H - UI_HEIGHT + 55))

        for btn in self.buttons:
            if btn.is_visible():
                self._draw_button(btn)


def build_test_scenario() -> Engine:
    hex_map = HexMap()
    for q in range(8):
        for r in range(8):
            hex_map.set_terrain(HexCoord(q, r), [TerrainLayer(TerrainType.PLAIN)])

    hex_map.set_terrain(HexCoord(3, 3), [TerrainLayer(TerrainType.FOREST)])
    hex_map.set_terrain(HexCoord(4, 3), [TerrainLayer(TerrainType.FOREST)])
    hex_map.set_terrain(HexCoord(3, 4), [TerrainLayer(TerrainType.HILL)])
    hex_map.set_terrain(HexCoord(5, 2), [TerrainLayer(TerrainType.CITY)])
    hex_map.set_terrain(HexCoord(2, 5), [TerrainLayer(TerrainType.SWAMP)])
    hex_map.set_terrain(HexCoord(4, 4), [TerrainLayer(TerrainType.FOREST), TerrainLayer(TerrainType.HILL)])
    hex_map.set_terrain(HexCoord(6, 1), [TerrainLayer(TerrainType.CITY), TerrainLayer(TerrainType.HILL)])
    hex_map.set_terrain(HexCoord(1, 6), [TerrainLayer(TerrainType.MOUNTAIN)])

    units = [
        Unit(id="inf_a1", name="1st Infantry A", type_id="infantry",
             player=PLAYER_A, position=HexCoord(1, 2), stats={"strength": 3, "movement": 2}),
        Unit(id="inf_a2", name="2nd Infantry A", type_id="infantry",
             player=PLAYER_A, position=HexCoord(1, 3), stats={"strength": 4, "movement": 2}),
        Unit(id="tank_a1", name="Tank Platoon A", type_id="tank",
             player=PLAYER_A, position=HexCoord(0, 4), stats={"strength": 5, "movement": 3}),
        Unit(id="inf_b1", name="1st Infantry B", type_id="infantry",
             player=PLAYER_B, position=HexCoord(5, 3), stats={"strength": 3, "movement": 2}),
        Unit(id="inf_b2", name="2nd Infantry B", type_id="infantry",
             player=PLAYER_B, position=HexCoord(6, 2), stats={"strength": 4, "movement": 2}),
        Unit(id="tank_b1", name="Tank Platoon B", type_id="tank",
             player=PLAYER_B, position=HexCoord(6, 4), stats={"strength": 5, "movement": 3}),
    ]

    system = WB48System()
    rng = GameRNG(seed=42)

    state = build_initial_state(
        scenario_id="test_visual",
        scenario_name="Visual Test",
        system_id="test",
        hex_map=hex_map,
        units=units,
        active_player=PLAYER_A,
    )

    return Engine(state, system, rng)


def main():
    engine = build_test_scenario()
    client = PygameClient(engine)
    client.run()


if __name__ == "__main__":
    main()
