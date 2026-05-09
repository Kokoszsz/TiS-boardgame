from __future__ import annotations

import math

import pygame

from hexwar.core.hex import HexCoord, _hex_round
from hexwar.core.map import TerrainLayer, TerrainType


HEX_SIZE = 40

TERRAIN_COLORS: dict[TerrainType, tuple[int, int, int]] = {
    TerrainType.PLAIN: (200, 220, 140),
    TerrainType.FOREST: (60, 130, 60),
    TerrainType.HILL: (180, 160, 100),
    TerrainType.CITY: (160, 160, 160),
    TerrainType.SWAMP: (100, 140, 120),
    TerrainType.MOUNTAIN: (140, 120, 100),
    TerrainType.WATER: (80, 130, 200),
}

TERRAIN_SYMBOLS: dict[TerrainType, str] = {
    TerrainType.PLAIN: "",
    TerrainType.FOREST: "F",
    TerrainType.HILL: "H",
    TerrainType.CITY: "C",
    TerrainType.SWAMP: "S",
    TerrainType.MOUNTAIN: "M",
    TerrainType.WATER: "W",
}

PLAYER_COLORS: dict[str, tuple[int, int, int]] = {
    "player_a": (50, 80, 200),
    "player_b": (200, 50, 50),
}


def hex_to_pixel(coord: HexCoord, size: float = HEX_SIZE) -> tuple[float, float]:
    x = size * (3 / 2 * coord.q)
    y = size * (math.sqrt(3) / 2 * coord.q + math.sqrt(3) * coord.r)
    return x, y


def pixel_to_hex(x: float, y: float, size: float = HEX_SIZE) -> HexCoord:
    q = (2 / 3 * x) / size
    r = (-1 / 3 * x + math.sqrt(3) / 3 * y) / size
    return _hex_round(q, r)


def hex_corners(center: tuple[float, float], size: float = HEX_SIZE) -> list[tuple[float, float]]:
    cx, cy = center
    corners = []
    for i in range(6):
        angle = math.radians(60 * i)
        corners.append((cx + size * math.cos(angle), cy + size * math.sin(angle)))
    return corners


def draw_hex(
    surface: pygame.Surface,
    coord: HexCoord,
    color: tuple[int, int, int],
    offset: tuple[float, float],
    size: float = HEX_SIZE,
    outline: tuple[int, int, int] | None = (80, 80, 80),
    outline_width: int = 1,
) -> None:
    px, py = hex_to_pixel(coord, size)
    center = (px + offset[0], py + offset[1])
    corners = hex_corners(center, size)
    pygame.draw.polygon(surface, color, corners)
    if outline:
        pygame.draw.polygon(surface, outline, corners, outline_width)


def draw_highlight(
    surface: pygame.Surface,
    coord: HexCoord,
    color: tuple[int, int, int, int],
    offset: tuple[float, float],
    size: float = HEX_SIZE,
) -> None:
    px, py = hex_to_pixel(coord, size)
    center = (px + offset[0], py + offset[1])
    corners = hex_corners(center, size)
    highlight_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(highlight_surf, color, corners)
    surface.blit(highlight_surf, (0, 0))


def draw_terrain_labels(
    surface: pygame.Surface,
    coord: HexCoord,
    layers: list[TerrainLayer],
    offset: tuple[float, float],
    size: float = HEX_SIZE,
    font: pygame.font.Font | None = None,
) -> None:
    symbols = [TERRAIN_SYMBOLS.get(layer.type, "?") for layer in layers if TERRAIN_SYMBOLS.get(layer.type)]
    if not symbols:
        return
    label = " ".join(symbols)
    if font is None:
        font = pygame.font.SysFont("consolas", 11)
    px, py = hex_to_pixel(coord, size)
    sx = px + offset[0]
    sy = py + offset[1]
    text = font.render(label, True, (255, 255, 255))
    text_shadow = font.render(label, True, (0, 0, 0))
    surface.blit(text_shadow, (sx - text.get_width() // 2 + 1, sy - size * 0.55 + 1))
    surface.blit(text, (sx - text.get_width() // 2, sy - size * 0.55))


def draw_arrow(
    surface: pygame.Surface,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int] | tuple[int, int, int, int] = (255, 200, 50),
    width: int = 2,
    head_size: int = 8,
) -> None:
    """Draw an arrow from start to end with an arrowhead."""
    pygame.draw.line(surface, color, start, end, width)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    ux, uy = dx / dist, dy / dist
    # Arrowhead
    left = (end[0] - head_size * ux + head_size * 0.5 * uy,
            end[1] - head_size * uy - head_size * 0.5 * ux)
    right = (end[0] - head_size * ux - head_size * 0.5 * uy,
             end[1] - head_size * uy + head_size * 0.5 * ux)
    pygame.draw.polygon(surface, color, [end, left, right])
