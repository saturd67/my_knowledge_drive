import flet as ft

from view.theme import Radius, Space, palette
from view.widgets.containers.pointer_area import PointerArea


class PortalRail(ft.Container):
    """Narrow rail on the far left for switching between the two portals.

    Presentation only for now - `on_select` is handed the portal key so the
    shell can swap portals once there is a second one to swap to.
    """

    #: key, tooltip, icon
    PORTALS = [
        ("user", "User portal", ft.Icons.TRAVEL_EXPLORE_ROUNDED),
        ("admin", "Admin portal", ft.Icons.ADMIN_PANEL_SETTINGS_ROUNDED),
    ]

    def __init__(self, active="admin", on_select=None):
        super().__init__()
        self.active = active
        self.on_select = on_select

    def build(self):
        p = palette()

        buttons = [
            self._button(key, tooltip, icon, key == self.active)
            for key, tooltip, icon in self.PORTALS
        ]

        self.content = ft.Column(
            buttons,
            spacing=Space.SM,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.width = 64
        self.padding = ft.Padding.symmetric(horizontal=0, vertical=Space.LG)
        self.bgcolor = p.surface_alt
        self.border = ft.Border.only(right=ft.BorderSide(1, p.border))

    def _button(self, key, tooltip, icon, is_active):
        p = palette()

        # The portal you are already on is not clickable, so it keeps the arrow.
        return PointerArea(
            content = ft.Container(
                content=ft.Icon(icon, size=21, color=p.primary if is_active else p.text_faint),
                width=44,
                height=44,
                alignment=ft.Alignment.CENTER,
                bgcolor=p.primary_soft if is_active else "transparent",
                border_radius=Radius.MD,
                tooltip=tooltip,
            ),
            is_clickable=not is_active,
            on_click=lambda _: self.on_select(key) if self.on_select is not None else None,
            hover_bgcolor=p.surface_high,
        )
