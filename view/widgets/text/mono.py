import flet as ft

from view.theme import MONO_FONT_FAMILY, palette


class Mono(ft.Text):
    """Fixed-width text - ids, paths and anything copied verbatim."""

    def __init__(self, value, size=12, color=None, **kwargs):
        super().__init__(
            value,
            size=size,
            font_family=MONO_FONT_FAMILY,
            color=color or palette().text_muted,
            **kwargs,
        )
