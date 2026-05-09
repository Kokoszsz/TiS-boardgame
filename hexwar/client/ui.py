from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import pygame


class UIButton:
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        on_click: Callable[[], None],
        is_visible: Callable[[], bool] | None = None,
        is_enabled: Callable[[], bool] | None = None,
        bg_color: tuple = (80, 120, 80),
        border_color: tuple = (150, 200, 150),
        text_color: tuple = (220, 220, 220),
        disabled_bg: tuple = (60, 60, 60),
        disabled_border: tuple = (100, 100, 100),
        disabled_text: tuple = (100, 100, 100),
    ):
        self.rect = rect
        self.label = label
        self.on_click = on_click
        self.is_visible = is_visible or (lambda: True)
        self.is_enabled = is_enabled or (lambda: True)
        self.bg_color = bg_color
        self.border_color = border_color
        self.text_color = text_color
        self.disabled_bg = disabled_bg
        self.disabled_border = disabled_border
        self.disabled_text = disabled_text

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)
