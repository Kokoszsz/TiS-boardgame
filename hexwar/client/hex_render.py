from __future__ import annotations

import math

import pygame

from hexwar.core.hex import HexCoord
from hexwar.core.map import TerrainType


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


def _hex_round(fq: float, fr: float) -> HexCoord:
    fs = -fq - fr
    q = round(fq)
    r = round(fr)
    s = round(fs)
    q_diff = abs(q - fq)
    r_diff = abs(r - fr)
    s_diff = abs(s - fs)
    if q_diff > r_diff and q_diff > s_diff:
        q = -r - s
    elif r_diff > s_diff:
        r = -q - s
    return HexCoord(q, r)
