from __future__ import annotations

import math
import sys

import pygame

from hexwar.core.actions import AttackAction, EndPhaseAction, MoveAction
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


class PygameClient:
    def __init__(self, engine: Engine):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("HexWar Engine")
        self.clock = pygame.time.Clock()
        self.engine = engine
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_big = pygame.font.SysFont("consolas", 18, bold=True)

        self.camera_offset = (SCREEN_W / 2 - 100, (SCREEN_H - UI_HEIGHT) / 2 - 50)
        self.selected_unit_id: str | None = None
        self.legal_moves: set[HexCoord] = set()
        self.legal_attacks: dict[HexCoord, str] = {}
        self.enemy_zoc: set[HexCoord] = set()
        self.event_log: list[str] = []
        self.dragging = False
        self.drag_start = (0, 0)
        self.cam_start = (0.0, 0.0)

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
                        self._deselect()
                    elif event.key == pygame.K_e:
                        self._end_phase()
                    elif event.key == pygame.K_u:
                        self._undo()
                    elif event.key == pygame.K_q:
                        running = False

            self._draw()
            self.clock.tick(30)

        pygame.quit()

    def _handle_left_click(self, pos: tuple[int, int]) -> None:
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

        if self.selected_unit_id and clicked in self.legal_moves:
            self._do_move(clicked)
            return

        if self.selected_unit_id and clicked in self.legal_attacks:
            self._do_attack(clicked)
            return

        units_here = self.engine.state.units_at(clicked)
        friendly = [u for u in units_here if u.player == self.engine.state.active_player]
        if friendly:
            self._select_unit(friendly[0].id)
        else:
            self._deselect()

    def _handle_ui_click(self, pos: tuple[int, int]) -> None:
        btn_x = SCREEN_W - 150
        btn_y = SCREEN_H - UI_HEIGHT + 20
        if btn_x <= pos[0] <= btn_x + 130 and btn_y <= pos[1] <= btn_y + 40:
            self._end_phase()

    def _select_unit(self, unit_id: str) -> None:
        self.selected_unit_id = unit_id
        self._compute_legal_targets()

    def _deselect(self) -> None:
        self.selected_unit_id = None
        self.legal_moves.clear()
        self.legal_attacks.clear()
        self.enemy_zoc.clear()

    def _compute_legal_targets(self) -> None:
        self.legal_moves.clear()
        self.legal_attacks.clear()
        self.enemy_zoc.clear()
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

    def _end_phase(self) -> None:
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
        self._draw_ui()
        pygame.display.flip()

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

    def _draw_units(self) -> None:
        state = self.engine.state
        for unit in state.units.values():
            px, py = hex_to_pixel(unit.position, HEX_SIZE)
            sx = px + self.camera_offset[0]
            sy = py + self.camera_offset[1]

            color = PLAYER_COLORS.get(unit.player, (200, 200, 200))
            pygame.draw.circle(self.screen, color, (int(sx), int(sy)), 14)
            pygame.draw.circle(self.screen, (255, 255, 255), (int(sx), int(sy)), 14, 1)

            label = unit.type_id[0].upper()
            text = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(text, (int(sx) - text.get_width() // 2, int(sy) - text.get_height() // 2))

            str_val = str(unit.stats.get("strength", "?"))
            str_text = self.font.render(str_val, True, (255, 255, 200))
            self.screen.blit(str_text, (int(sx) - str_text.get_width() // 2, int(sy) + 14))

    def _draw_ui(self) -> None:
        ui_rect = pygame.Rect(0, SCREEN_H - UI_HEIGHT, SCREEN_W, UI_HEIGHT)
        pygame.draw.rect(self.screen, UI_BG, ui_rect)

        state = self.engine.state
        phase = self.engine.current_phase

        info = f"Turn {state.turn}  |  {phase.name}  |  Active: {state.active_player}"
        info_surf = self.font_big.render(info, True, TEXT_COLOR)
        self.screen.blit(info_surf, (15, SCREEN_H - UI_HEIGHT + 10))

        controls = "Click: select/move/attack  |  E: end phase  |  U: undo  |  RMB: pan  |  Q: quit"
        ctrl_surf = self.font.render(controls, True, (150, 150, 150))
        self.screen.blit(ctrl_surf, (15, SCREEN_H - UI_HEIGHT + 35))

        if self.event_log:
            last = self.event_log[-1][:80]
            log_surf = self.font.render(last, True, (180, 180, 100))
            self.screen.blit(log_surf, (15, SCREEN_H - UI_HEIGHT + 55))

        btn_x = SCREEN_W - 150
        btn_y = SCREEN_H - UI_HEIGHT + 20
        btn_rect = pygame.Rect(btn_x, btn_y, 130, 40)
        pygame.draw.rect(self.screen, (80, 120, 80), btn_rect)
        pygame.draw.rect(self.screen, (150, 200, 150), btn_rect, 2)
        btn_text = self.font_big.render("End Phase", True, TEXT_COLOR)
        self.screen.blit(btn_text, (btn_x + 15, btn_y + 10))


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
