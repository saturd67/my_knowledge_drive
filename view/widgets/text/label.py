import flet as ft

from view.theme import palette


class Label(ft.Text):
    """Small upper-cased caption above a field or a table column."""

    def __init__(self, value, size=11):
        super().__init__(
            value.upper(),
            size=size,
            weight=ft.FontWeight.W_700,
            color=palette().text_faint,
        )
