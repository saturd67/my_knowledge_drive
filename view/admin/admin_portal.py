"""Admin portal: the nav sidebar and the screen beside it.

Everything right of the rail when the admin portal is showing. It owns which
screen is showing and the reader that shows it, and builds the sidebar that
reads both - picking a nav row redraws each column.
"""

import flet as ft

from view.admin.admin_sidebar import NAV_ITEMS, AdminSidebar
from view.admin.screens.library_sync.library_reset_runner import LibraryResetRunner
from view.admin.screens.library_sync.library_sync_runner import LibrarySyncRunner
from view.theme import Space, palette


class AdminPortal(ft.Row):

    def __init__(self):
        super().__init__()
        self.index = 0
        # Held here, not on the Library Sync screen: a run takes minutes and
        # the screen is rebuilt the moment you navigate anywhere else. The
        # sync runner also carries the scan result, so a plan you have not
        # applied yet survives a trip to another screen.
        self.reset_runner = LibraryResetRunner()
        self.sync_runner = LibrarySyncRunner()

        # Held so refresh() can swap just the screen, leaving the chrome alone.
        self.body_container = ft.Container(expand=True)
        # A screen that scrolls a list of its own fills the viewport and keeps
        # its scrollbar inside that list, so the page-level scroll is turned
        # off for it - two nested scrolls leave the inner one unbounded.
        self.scroll_column = ft.Column([self.body_container], expand=True)
        self.reader_container = ft.Container(
            content=self.scroll_column,
            padding=Space.XXL,
            bgcolor=palette().bg,
            expand=True,
        )

        self.admin_sidebar = AdminSidebar(self)
        self._fill_reader()

    def build(self):
        self.controls = [
            self.admin_sidebar,
            self.reader_container,
        ]
        self.spacing = 0
        self.expand = True
        self.vertical_alignment = ft.CrossAxisAlignment.STRETCH

    def navigate(self, index):
        self.index = index
        self.refresh()

    def refresh(self):
        """Both columns move together - picking a row changes each of them."""
        self.admin_sidebar.refresh()
        self._fill_reader()
        self.scroll_column.update()

    def _fill_reader(self):
        """A screen is built fresh each time - the instance lives for one build."""
        # Before the new screen attaches its own: a run in progress keeps
        # going with nowhere to draw, rather than drawing into the old tree.
        self.reset_runner.detach()
        self.sync_runner.detach()

        view_class = NAV_ITEMS[self.index][3]
        self.scroll_column.scroll = ft.ScrollMode.AUTO if view_class.scrolls else None
        self.body_container.content = view_class(self).build()
