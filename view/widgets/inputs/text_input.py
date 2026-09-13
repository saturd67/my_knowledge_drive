import flet as ft

from view.theme import MONO_FONT_FAMILY, Radius, Space, palette


class TextInput(ft.TextField):
    """One single-line text box, sized to sit in a labelled row."""

    def __init__(self, value, is_mono=False, on_change=None, expand=True):
        p = palette()
        super().__init__(
            value=value,
            on_change=on_change,
            text_size=12,
            text_style=ft.TextStyle(font_family=MONO_FONT_FAMILY) if is_mono else None,
            color=p.text,
            dense=True,
            expand=expand,
            content_padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
            filled=True,
            fill_color=p.surface_alt,
            border_color=p.border,
            focused_border_color=p.primary,
            border_radius=Radius.SM,
        )
