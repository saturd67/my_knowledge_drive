import flet as ft

from view.theme import Radius, palette, tone
from view.widgets.buttons._padding import button_padding


class PrimaryButton(ft.FilledButton):
    """Solid call to action.

    The colours are given per control state rather than as one value. A bare
    colour is read as the default for *every* state, so a disabled button
    would keep its full-strength fill and look exactly like a live one - the
    click is refused, and nothing on screen says why.
    """

    def __init__(self, text, on_click=None, icon=None, tone_name="primary",
                 expand=False, is_dense=False):
        fg, _ = tone(tone_name)
        p = palette()
        super().__init__(
            content=text,
            icon=icon,
            on_click=on_click,
            expand=expand,
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DEFAULT: fg,
                    ft.ControlState.DISABLED: p.surface_high,
                },
                color={
                    ft.ControlState.DEFAULT: p.on_primary if tone_name == "primary" else p.bg,
                    ft.ControlState.DISABLED: p.text_faint,
                },
                padding=button_padding(is_dense),
                shape=ft.RoundedRectangleBorder(radius=Radius.MD),
                text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_600),
                # Per state, like the colours above: a disabled button keeps
                # the plain arrow rather than inviting a click it will refuse.
                mouse_cursor={
                    ft.ControlState.DEFAULT: ft.MouseCursor.CLICK,
                    ft.ControlState.DISABLED: ft.MouseCursor.BASIC,
                },
            ),
        )
