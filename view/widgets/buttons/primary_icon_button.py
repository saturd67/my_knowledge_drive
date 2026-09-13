import flet as ft

from view.theme import Radius, palette, tone


class PrimaryIconButton(ft.IconButton):
    """`PrimaryButton` with no room for a label - a filled tile round one glyph.

    Sized rather than padded, so it lines up with whatever field it sits
    beside instead of setting the height of the row itself.
    """

    def __init__(self, icon, tooltip=None, on_click=None, tone_name="primary", size=40):
        fg, _ = tone(tone_name)
        p = palette()
        super().__init__(
            icon=icon,
            icon_size=18,
            tooltip=tooltip,
            on_click=on_click,
            icon_color=p.on_primary if tone_name == "primary" else p.bg,
            width=size,
            height=size,
            style=ft.ButtonStyle(
                bgcolor=fg,
                padding=0,
                shape=ft.RoundedRectangleBorder(radius=Radius.MD),
                mouse_cursor={
                    ft.ControlState.DEFAULT: ft.MouseCursor.CLICK,
                    ft.ControlState.DISABLED: ft.MouseCursor.BASIC,
                },
            ),
        )
