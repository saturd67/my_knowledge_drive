"""Flet entry point for the desktop UI.

Opens on the admin portal; the far-left rail switches to the user portal.
The screens are presentation only - see view/user/ and view/admin/ for the
layouts, and services/ for the code that does the real work.
"""

import flet as ft

from services.DatabaseService import DatabaseService
from view import theme
from view.main_view import TITLES, MainView

START_PORTAL = "user"


def main(page: ft.Page):
    page.title = TITLES[START_PORTAL]
    page.padding = 0
    page.spacing = 0
    theme.apply(page)
    theme.apply_window(page)
    page.add(MainView(portal=START_PORTAL))


if __name__ == "__main__":
    # Once per process, before any screen reads a setting. Creates and seeds
    # every table if the database is new; reading before this fails loudly.
    DatabaseService().initialise()
    ft.run(main)
