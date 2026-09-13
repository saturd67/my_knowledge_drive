"""Admin sidebar: brand header, navigation, connection footer.

Reads the selected screen off the portal it is given, and calls back into it -
the reader beside it has to change with the same click.
"""

from typing import TYPE_CHECKING

import flet as ft

from view.admin.screens.library_sync.library_sync_view import LibrarySyncView
from view.admin.screens.library_view import LibraryView
from view.admin.screens.settings_view import SettingsView
from view.theme import Radius, Space, palette
from view.widgets.blocks.brand import BrandHeader
from view.widgets.blocks.nav_item import NavItem
from view.widgets.containers.pointer_area import PointerArea

if TYPE_CHECKING:
    # Annotation-only: the portal imports this module, so a real import here
    # would be a cycle.
    from view.admin.admin_portal import AdminPortal

#: text, icon, selected icon, the BaseView subclass the reader shows. One row
#: rather than two lists, so a nav item and its screen cannot drift apart.
NAV_ITEMS = [
    ("Library", ft.Icons.TABLE_ROWS_OUTLINED, ft.Icons.TABLE_ROWS_ROUNDED, LibraryView),
    ("Library Sync", ft.Icons.SYNC_OUTLINED, ft.Icons.SYNC_ROUNDED, LibrarySyncView),
    ("Settings", ft.Icons.TUNE_OUTLINED, ft.Icons.TUNE_ROUNDED, SettingsView),
]

WIDTH = 248


class AdminSidebar(ft.Container):
    """The column itself: its width, its fill and the rule down its right.

    None of that changes when a screen is picked, so the panel inside is what
    gets redrawn.
    """

    def __init__(self, admin_portal: "AdminPortal"):
        super().__init__()
        # No handing ourselves back: the portal builds this sidebar and keeps
        # the reference, so it can already redraw us.
        self.admin_portal = admin_portal
        self.admin_panel = AdminPanel(admin_portal)

    def build(self):
        p = palette()
        self.width = WIDTH
        self.bgcolor = p.sidebar
        self.border = ft.Border.only(right=ft.BorderSide(1, p.border))
        self.content = self.admin_panel

    def refresh(self):
        self.admin_panel.refresh()


class AdminPanel(ft.Column):
    """What the sidebar holds: the brand, the nav rows and the store footer."""

    def __init__(self, admin_portal: "AdminPortal"):
        super().__init__()
        self.admin_portal = admin_portal

    def build(self):
        self.controls = self._blocks()
        self.spacing = 0
        self.expand = True

    def refresh(self):
        self.controls = self._blocks()
        self.update()

    def _blocks(self):
        p = palette()
        return [
            BrandHeader("Admin Portal"),
            AdminNavList(self.admin_portal),
            # Pushes the footer to the bottom whatever the nav runs to.
            ft.Container(expand=True),
            ft.Container(height=1, bgcolor=p.border_soft),
            StoreFooter(),
        ]


class AdminNavList(ft.Container):
    """One row per screen, with the selected one carrying the pill."""

    def __init__(self, admin_portal: "AdminPortal"):
        super().__init__()
        self.admin_portal = admin_portal

    def build(self):
        p = palette()
        admin_portal = self.admin_portal

        self.content = ft.Column(
            [
                PointerArea(
                    NavItem(text, icon, selected_icon, is_selected=index == admin_portal.index),
                    on_click=lambda _, i=index: admin_portal.navigate(i),
                    # The selected row already has its pill - only the others
                    # light up.
                    hover_bgcolor=None if index == admin_portal.index else p.surface_high,
                )
                for index, (text, icon, selected_icon, _view_class) in enumerate(NAV_ITEMS)
            ],
            spacing=Space.XS,
        )
        self.padding = ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.LG)


class StoreFooter(ft.Container):
    """Whether the store is reachable, and the model it was built with."""

    def build(self):
        p = palette()
        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(width=7, height=7, bgcolor=p.success,
                                     border_radius=Radius.PILL),
                        ft.Text("Store connected", size=11, color=p.text_muted),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("all-MiniLM-L6-v2 - local", size=10, color=p.text_faint),
            ],
            spacing=Space.XS,
        )
        self.padding = Space.LG
