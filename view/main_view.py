import flet as ft

from view.admin.admin_portal import AdminPortal
from view.user.user_portal import UserPortal
from view.widgets.blocks.portal_rail import PortalRail

TITLES = {
    "user": "MyKnowledgeDrive - User Portal",
    "admin": "MyKnowledgeDrive - Admin Portal",
}


class MainView(ft.Row):
    """The window: the rail, and whichever portal it is pointing at.

    The rail switches portals in place. What a portal puts beside it - a nav
    sidebar and a screen, or a search sidebar and a reading pane - is the
    portal's own business.
    """

    def __init__(self, portal="admin"):
        super().__init__()
        self.portal = portal

    def build(self):
        self.expand = True
        self.spacing = 0
        self.vertical_alignment = ft.CrossAxisAlignment.STRETCH
        self.controls = self._columns()

    def select_portal(self, portal):
        """Swap the whole window over to the other portal."""
        self.portal = portal
        self.controls = self._columns()
        if self.page is not None:
            self.page.title = TITLES[portal]
        self.update()

    def _columns(self):
        portal_rail = PortalRail(active=self.portal, on_select=self.select_portal)
        if self.portal == "user":
            return [portal_rail, UserPortal()]
        return [portal_rail, AdminPortal()]
