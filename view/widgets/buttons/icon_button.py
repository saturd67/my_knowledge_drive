import flet as ft

from view.theme import Radius, tone


class IconButton(ft.IconButton):
    """Bare icon action, usually parked at the end of a row."""

    def __init__(self, icon, tooltip=None, on_click=None, tone_name="neutral"):
        fg, _ = tone(tone_name)
        super().__init__(
            icon=icon,
            icon_size=18,
            tooltip=tooltip,
            on_click=on_click,
            icon_color=fg,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=Radius.SM),
                mouse_cursor={
                    ft.ControlState.DEFAULT: ft.MouseCursor.CLICK,
                    ft.ControlState.DISABLED: ft.MouseCursor.BASIC,
                },
            ),
        )
