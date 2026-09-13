import flet as ft

from view.theme import Radius, palette, tone
from view.widgets.buttons._padding import button_padding


class GhostButton(ft.OutlinedButton):
    """Outlined secondary action."""

    def __init__(self, text, on_click=None, icon=None, tone_name="neutral",
                 expand=False, is_dense=False):
        p = palette()
        fg, _ = tone(tone_name)
        super().__init__(
            # `content`, not `text` - flet 0.86 dropped the `text` field and
            # takes the label (a str or a Control) on `content`.
            content=text,
            icon=icon,
            on_click=on_click,
            expand=expand,
            style=ft.ButtonStyle(
                color=p.text if tone_name == "neutral" else fg,
                side=ft.BorderSide(1, p.border),
                padding=button_padding(is_dense),
                shape=ft.RoundedRectangleBorder(radius=Radius.MD),
                text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_600),
                # Per state, so a disabled button keeps the plain arrow rather
                # than inviting a click it will refuse.
                mouse_cursor={
                    ft.ControlState.DEFAULT: ft.MouseCursor.CLICK,
                    ft.ControlState.DISABLED: ft.MouseCursor.BASIC,
                },
            ),
        )
