"""User portal: the search sidebar and the reading pane beside it.

Everything right of the rail when the user portal is showing. The two columns
are the two panes of one screen: the sidebar holds that screen, and the screen
holds the reading pane, so both are reached from the sidebar. It hands itself
to the screen as it is built, and the two redraw each other from then on.
"""

import flet as ft

from view.user.screens.search_view import SearchView
from view.user.search_sidebar import SearchSidebar


class UserPortal(ft.Row):

    def __init__(self):
        super().__init__()
        self.search_sidebar = SearchSidebar(SearchView())

    def build(self):
        self.controls = [
            self.search_sidebar,
            self.search_sidebar.search_view.reader_container,
        ]
        self.spacing = 0
        self.expand = True
        self.vertical_alignment = ft.CrossAxisAlignment.STRETCH

    def did_mount(self):
        """Start loading the embedding model the moment the portal is drawn.

        It takes seconds, and it used to load on the first search - so the
        whole wait landed in front of someone who had just asked a question.
        Started here, it runs while the screen is being read and the query
        typed, and by the time Search is pressed it is usually already done.

        On a worker thread: `did_mount` is the event loop, and blocking it
        would freeze the window that was just drawn. Cheap to repeat when the
        rail switches back to this portal - `SearchService` caches what it
        built, so every call after the first returns at once.

        Through the screen rather than straight to the service, so the sidebar
        can show the wait and drop the spinner when it is over.
        """
        self.page.run_thread(self.search_sidebar.search_view.init_search)
