from __future__ import annotations

import math
import sys

import pygame

from hexwar.core.actions import (
    AttackAction, DeclareAttackAction, EndPhaseAction,
    EntrenchAction, MoveAction, ResolveBattleAction, UndeclareAttackAction,
)
from hexwar.core.engine import Engine
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
from hexwar.systems.test_system import PLAYER_A, PLAYER_B, TestSystem

SCREEN_W = 1024
SCREEN_H = 700
BG_COLOR = (30, 30, 30)
UI_BG = (50, 50, 50)
UI_HEIGHT = 80
TEXT_COLOR = (220, 220, 220)
HIGHLIGHT_MOVE = (100, 200, 100, 80)
HIGHLIGHT_SELECT = (255, 255, 100, 120)
HIGHLIGHT_ATTACK = (255, 80, 80, 100)
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
        self.legal_attacks: dict[HexCoord, str] = {}
        self.enemy_zoc: set[HexCoord] = set()
        self.event_log: list[str] = []
        self.dragging = False
        self.drag_start = (0, 0)
        self.cam_start = (0.0, 0.0)

        self.unit_picker_open = False
        self.unit_picker_units: list[Unit] = []
        self.unit_picker_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.unit_picker_item_rects: list[pygame.Rect] = []
        self.can_entrench = False

        # Combat declaration UI state
        self.selected_attackers: list[str] = []  # multi-select for declaration
        self.selected_battle_id: int | None = None  # for undeclare

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
                    elif event.key == pygame.K_q:
                        running = False

            self._draw()
            self.clock.tick(30)

        pygame.quit()

    def _handle_left_click(self, pos: tuple[int, int]) -> None:
        if self.unit_picker_open:
            self._handle_picker_click(pos)
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

        # --- Combat declaration mode ---
        if self._in_declaration_mode():
            self._handle_declaration_click(clicked)
            return

        # --- Combat resolution mode ---
        if self._in_resolution_mode():
            self._handle_resolution_click(clicked)
            return

        if self.selected_unit_id and clicked in self.legal_moves:
            self._do_move(clicked)
            return

        if self.selected_unit_id and clicked in self.legal_attacks:
            self._do_attack(clicked)
            return

        units_here = self.engine.state.units_at(clicked)
        friendly = [u for u in units_here if u.player == self.engine.state.active_player]
        if len(friendly) > 1:
            self._open_unit_picker(friendly, pos)
        elif friendly:
            self._select_unit(friendly[0].id)
        else:
            self._deselect()

    def _handle_ui_click(self, pos: tuple[int, int]) -> None:
        btn_x = SCREEN_W - 150
        btn_y = SCREEN_H - UI_HEIGHT + 20
        if btn_x <= pos[0] <= btn_x + 130 and btn_y <= pos[1] <= btn_y + 40:
            self._end_phase()
        ent_x = SCREEN_W - 300
        ent_y = SCREEN_H - UI_HEIGHT + 20
        if ent_x <= pos[0] <= ent_x + 130 and ent_y <= pos[1] <= ent_y + 40:
            self._do_entrench()

    def _open_unit_picker(self, units: list[Unit], click_pos: tuple[int, int]) -> None:
        self.unit_picker_open = True
        self.unit_picker_units = units
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
        self.legal_attacks.clear()
        self.enemy_zoc.clear()
        self._close_picker()
        self.selected_attackers.clear()
        self.selected_battle_id = None

    # ------------------------------------------------------------------
    # Combat declaration mode
    # ------------------------------------------------------------------

    def _in_declaration_mode(self) -> bool:
        return self.engine.state.metadata.get("combat_sub_phase") == "declaration"

    def _in_resolution_mode(self) -> bool:
        return self.engine.state.metadata.get("combat_sub_phase") == "resolution"

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
            if clicked in battle.get("defender_hexes", ()):
                self.selected_battle_id = battle["id"]
                self.selected_attackers.clear()
                return

        # Check if clicked on a friendly unit — toggle multi-select
        friendly = [u for u in units_here if u.player == player]
        committed = self.engine.state.metadata.get("committed_attackers", set())

        if friendly:
            # Check if any friendly unit here is a committed attacker — select that battle
            committed_here = [u for u in friendly if u.id in committed]
            if committed_here and not shift:
                for battle in battles:
                    if committed_here[0].id in battle.get("attacker_ids", ()):
                        self.selected_battle_id = battle["id"]
                        self.selected_attackers.clear()
                        return

            # Only consider uncommitted units for new declarations
            available = [u for u in friendly if u.id not in committed]
            if available:
                uid = available[0].id
                if shift:
                    # Toggle in multi-select
                    if uid in self.selected_attackers:
                        self.selected_attackers.remove(uid)
                    else:
                        self.selected_attackers.append(uid)
                else:
                    if not self.selected_attackers:
                        self.selected_attackers = [uid]
                    else:
                        if uid in self.selected_attackers:
                            self.selected_attackers.remove(uid)
                        else:
                            self.selected_attackers = [uid]
                self.selected_battle_id = None
                return

        # Clicked empty — deselect
        self.selected_attackers.clear()
        self.selected_battle_id = None

    def _do_declare_attack(self, target_hex: HexCoord) -> None:
        """Submit DeclareAttackAction with selected attackers → target hex.

        If the target hex already has a declared battle, merge: undeclare
        the existing battle then re-declare with combined attackers.
        """
        player = self.engine.state.active_player
        new_attackers = list(self.selected_attackers)

        # Check if target hex is already part of an existing battle
        battles = self.engine.state.metadata.get("battles", [])
        existing_battle = None
        for battle in battles:
            if target_hex in battle.get("defender_hexes", ()):
                existing_battle = battle
                break

        if existing_battle:
            # Merge: combine existing attackers with newly selected ones
            old_attackers = list(existing_battle["attacker_ids"])
            merged = list(set(old_attackers + new_attackers))
            # Undeclare the old battle first
            undeclare = UndeclareAttackAction(player=player, battle_id=existing_battle["id"])
            self.engine.submit_action(undeclare)
            # Now declare with merged attackers
            action = DeclareAttackAction(
                player=player,
                attacker_ids=tuple(sorted(merged)),
                defender_hexes=tuple(existing_battle["defender_hexes"]),
            )
        else:
            action = DeclareAttackAction(
                player=player,
                attacker_ids=tuple(sorted(new_attackers)),
                defender_hexes=(target_hex,),
            )

        # Check if action is legal
        legal = self.engine.get_legal_actions()
        if any(a == action for a in legal):
            events = self.engine.submit_action(action)
            for e in events:
                self.event_log.append(str(e))
            self.selected_attackers.clear()
        else:
            # If merge failed, try to re-declare the original battle
            if existing_battle:
                restore = DeclareAttackAction(
                    player=player,
                    attacker_ids=tuple(existing_battle["attacker_ids"]),
                    defender_hexes=tuple(existing_battle["defender_hexes"]),
                )
                self.engine.submit_action(restore)
            self.event_log.append("[INVALID] Cannot declare that attack")

    def _extend_battle_defenders(self, target_hex: HexCoord) -> None:
        """Add a new defender hex to the currently selected battle (fan-out)."""
        player = self.engine.state.active_player
        battles = self.engine.state.metadata.get("battles", [])
        battle = None
        for b in battles:
            if b["id"] == self.selected_battle_id:
                battle = b
                break
        if battle is None:
            return

        # Don't add if already in the battle
        if target_hex in battle.get("defender_hexes", ()):
            return

        # Undeclare old, re-declare with extended defender hexes
        old_attacker_ids = tuple(battle["attacker_ids"])
        old_defender_hexes = tuple(battle["defender_hexes"])
        new_defender_hexes = tuple(sorted(set(old_defender_hexes) | {target_hex}))

        undeclare = UndeclareAttackAction(player=player, battle_id=self.selected_battle_id)
        self.engine.submit_action(undeclare)

        action = DeclareAttackAction(
            player=player,
            attacker_ids=old_attacker_ids,
            defender_hexes=new_defender_hexes,
        )
        legal = self.engine.get_legal_actions()
        if any(a == action for a in legal):
            events = self.engine.submit_action(action)
            for e in events:
                self.event_log.append(str(e))
            self.selected_battle_id = None
        else:
            # Restore original battle
            restore = DeclareAttackAction(
                player=player,
                attacker_ids=old_attacker_ids,
                defender_hexes=old_defender_hexes,
            )
            self.engine.submit_action(restore)
            self.event_log.append("[INVALID] Cannot extend battle to that hex")

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
        """Handle clicks during combat resolution sub-phase.
        Click on a battle's defender hex to resolve it."""
        state = self.engine.state
        battles = state.metadata.get("battles", [])

        for battle in battles:
            if battle.get("resolved"):
                continue
            if clicked in battle.get("defender_hexes", ()):
                self._do_resolve_battle(battle["id"])
                return
            # Also allow clicking attacker hexes
            for uid in battle.get("attacker_ids", ()):
                unit = state.get_unit(uid)
                if unit and unit.position == clicked:
                    self._do_resolve_battle(battle["id"])
                    return

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
                from hexwar.core.events import BattleResolved
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
        self.legal_attacks.clear()
        self.enemy_zoc.clear()
        self.can_entrench = False
        if not self.selected_unit_id:
            return

        unit = self.engine.state.get_unit(self.selected_unit_id)
        if unit:
            zoc_map = self.engine.system._enemy_zoc_map(
                self.engine.state, unit.player
            )
            self.enemy_zoc = set(zoc_map.keys())

        legal = self.engine.get_legal_actions()
        for action in legal:
            if isinstance(action, MoveAction) and action.unit_id == self.selected_unit_id:
                self.legal_moves.add(action.target)
            elif isinstance(action, AttackAction) and action.attacker_id == self.selected_unit_id:
                defender = self.engine.state.get_unit(action.defender_id)
                if defender:
                    self.legal_attacks[defender.position] = action.defender_id
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

    def _do_attack(self, target_hex: HexCoord) -> None:
        defender_id = self.legal_attacks[target_hex]
        action = AttackAction(
            player=self.engine.state.active_player,
            attacker_id=self.selected_unit_id,
            defender_id=defender_id,
        )
        events = self.engine.submit_action(action)
        for e in events:
            self.event_log.append(str(e))
        if self.selected_unit_id in self.engine.state.units:
            self._select_unit(self.selected_unit_id)
        else:
            self._deselect()

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
        # Block if in declaration mode and obligations not met
        if self._in_declaration_mode():
            if not self.engine.state.metadata.get("declaration_complete", False):
                self.event_log.append("[BLOCKED] Must declare all obligated attacks first")
                return
        # Block if in resolution mode and battles remain
        if self._in_resolution_mode():
            unresolved = [b for b in self.engine.state.metadata.get("battles", [])
                          if not b.get("resolved")]
            if unresolved:
                self.event_log.append(f"[BLOCKED] {len(unresolved)} battle(s) still unresolved")
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
        self._draw_ui()
        if self.unit_picker_open:
            self._draw_unit_picker()
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

        for i, (unit, rect) in enumerate(zip(self.unit_picker_units, self.unit_picker_item_rects)):
            hovered = rect.collidepoint(mouse_pos)
            bg = PANEL_ITEM_HOVER if hovered else PANEL_ITEM_BG
            pygame.draw.rect(self.screen, bg, rect)

            color = PLAYER_COLORS.get(unit.player, (200, 200, 200))
            pygame.draw.circle(self.screen, color, (rect.x + 14, rect.centery), 8)

            mp_left = remaining_mp.get(unit.id, unit.stats.get("movement", 1))
            info = f"{unit.name}  MP:{mp_left}"
            text = self.font_small.render(info, True, TEXT_COLOR)
            self.screen.blit(text, (rect.x + 28, rect.centery - text.get_height() // 2))

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

        for coord in self.legal_attacks:
            draw_highlight(self.screen, coord, HIGHLIGHT_ATTACK, self.camera_offset)

        # Declaration mode: highlight obligated units and selected attackers
        if self._in_declaration_mode():
            state = self.engine.state
            player = state.active_player
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

    def _draw_declaration_overlay(self) -> None:
        """Draw arrows and ratio labels for declared battles."""
        state = self.engine.state
        battles = state.metadata.get("battles", [])

        for battle in battles:
            attacker_ids = battle.get("attacker_ids", ())
            defender_hexes = battle.get("defender_hexes", ())
            defender_ids = battle.get("defender_ids", ())
            battle_id = battle.get("id")

            is_selected = (battle_id == self.selected_battle_id)
            arrow_color = BATTLE_ARROW_SELECTED if is_selected else BATTLE_ARROW_COLOR

            # Compute defender center pixel
            if not defender_hexes:
                continue
            def_px_sum, def_py_sum = 0.0, 0.0
            for dh in defender_hexes:
                dpx, dpy = hex_to_pixel(dh, HEX_SIZE)
                def_px_sum += dpx + self.camera_offset[0]
                def_py_sum += dpy + self.camera_offset[1]
            def_cx = def_px_sum / len(defender_hexes)
            def_cy = def_py_sum / len(defender_hexes)

            # Draw arrow from each attacker to defender center
            for uid in attacker_ids:
                unit = state.get_unit(uid)
                if not unit:
                    continue
                apx, apy = hex_to_pixel(unit.position, HEX_SIZE)
                ax = apx + self.camera_offset[0]
                ay = apy + self.camera_offset[1]
                draw_arrow(self.screen, (ax, ay), (def_cx, def_cy), color=arrow_color, width=2)

            # Draw ratio label at midpoint
            atk_str = sum(
                state.get_unit(uid).stats.get("strength", 1)
                for uid in attacker_ids if state.get_unit(uid)
            )
            def_str = sum(
                state.get_unit(uid).stats.get("strength", 1)
                for uid in defender_ids if state.get_unit(uid)
            )
            ratio_text = f"{atk_str}:{def_str}" if def_str > 0 else "auto"
            label = self.font.render(ratio_text, True, arrow_color)

            # Position label near defender
            label_x = int(def_cx) + 16
            label_y = int(def_cy) - 20
            bg_rect = pygame.Rect(label_x - 2, label_y - 1, label.get_width() + 4, label.get_height() + 2)
            pygame.draw.rect(self.screen, (30, 30, 30), bg_rect)
            self.screen.blit(label, (label_x, label_y))

            # If selected, draw border indicator
            if is_selected:
                for dh in defender_hexes:
                    draw_highlight(self.screen, dh, (255, 255, 100, 60), self.camera_offset)

    def _draw_resolution_overlay(self) -> None:
        """Draw battles during resolution sub-phase with resolved/unresolved indicators."""
        state = self.engine.state
        battles = state.metadata.get("battles", [])

        for battle in battles:
            attacker_ids = battle.get("attacker_ids", ())
            defender_hexes = battle.get("defender_hexes", ())
            defender_ids = battle.get("defender_ids", ())
            resolved = battle.get("resolved", False)
            battle_id = battle.get("id")

            arrow_color = BATTLE_RESOLVED_COLOR if resolved else BATTLE_UNRESOLVED_COLOR

            if not defender_hexes:
                continue
            def_px_sum, def_py_sum = 0.0, 0.0
            for dh in defender_hexes:
                dpx, dpy = hex_to_pixel(dh, HEX_SIZE)
                def_px_sum += dpx + self.camera_offset[0]
                def_py_sum += dpy + self.camera_offset[1]
            def_cx = def_px_sum / len(defender_hexes)
            def_cy = def_py_sum / len(defender_hexes)

            # Draw arrows
            for uid in attacker_ids:
                unit = state.get_unit(uid)
                if not unit:
                    continue
                apx, apy = hex_to_pixel(unit.position, HEX_SIZE)
                ax = apx + self.camera_offset[0]
                ay = apy + self.camera_offset[1]
                draw_arrow(self.screen, (ax, ay), (def_cx, def_cy), color=arrow_color, width=2)

            # Label: ratio + result if resolved
            atk_str = sum(
                state.get_unit(uid).stats.get("strength", 1)
                for uid in attacker_ids if state.get_unit(uid)
            )
            def_str = sum(
                state.get_unit(uid).stats.get("strength", 1)
                for uid in defender_ids if state.get_unit(uid)
            )
            ratio_text = f"{atk_str}:{def_str}" if def_str > 0 else "auto"
            if resolved:
                dice = battle.get("dice_roll", (0, 0))
                result = battle.get("result", "?")
                label_text = f"#{battle_id} {ratio_text} [{dice[0]}+{dice[1]}={sum(dice)}] {result}"
            else:
                label_text = f"#{battle_id} {ratio_text} [click to resolve]"
            label = self.font_small.render(label_text, True, arrow_color)

            label_x = int(def_cx) + 16
            label_y = int(def_cy) - 20
            bg_rect = pygame.Rect(label_x - 2, label_y - 1, label.get_width() + 4, label.get_height() + 2)
            pygame.draw.rect(self.screen, (30, 30, 30), bg_rect)
            self.screen.blit(label, (label_x, label_y))

            # Highlight unresolved defender hexes
            if not resolved:
                for dh in defender_hexes:
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
            unresolved = sum(1 for b in battles if not b.get("resolved"))
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

        # End Phase button — grayed when obligations unmet in declaration mode
        btn_x = SCREEN_W - 150
        btn_y = SCREEN_H - UI_HEIGHT + 20
        btn_rect = pygame.Rect(btn_x, btn_y, 130, 40)
        can_end = True
        if self._in_declaration_mode() and not state.metadata.get("declaration_complete", False):
            can_end = False
        if self._in_resolution_mode():
            unresolved = [b for b in state.metadata.get("battles", []) if not b.get("resolved")]
            if unresolved:
                can_end = False
        if can_end:
            pygame.draw.rect(self.screen, (80, 120, 80), btn_rect)
            pygame.draw.rect(self.screen, (150, 200, 150), btn_rect, 2)
            btn_text = self.font_big.render("End Phase", True, TEXT_COLOR)
        else:
            pygame.draw.rect(self.screen, (60, 60, 60), btn_rect)
            pygame.draw.rect(self.screen, (100, 100, 100), btn_rect, 2)
            btn_text = self.font_big.render("End Phase", True, (100, 100, 100))
        self.screen.blit(btn_text, (btn_x + 15, btn_y + 10))

        if self.can_entrench:
            ent_x = SCREEN_W - 300
            ent_y = SCREEN_H - UI_HEIGHT + 20
            ent_rect = pygame.Rect(ent_x, ent_y, 130, 40)
            pygame.draw.rect(self.screen, (80, 80, 120), ent_rect)
            pygame.draw.rect(self.screen, (150, 150, 200), ent_rect, 2)
            ent_text = self.font_big.render("Entrench(F)", True, TEXT_COLOR)
            self.screen.blit(ent_text, (ent_x + 8, ent_y + 10))


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

    system = TestSystem()
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
