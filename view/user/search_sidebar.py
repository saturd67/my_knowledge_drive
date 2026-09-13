"""User sidebar: brand header, query field, ranked hits.

Reads the query and the picked hit off the screen it is given, and calls back
into it - the reading pane beside it has to change with the same click.
"""

from typing import TYPE_CHECKING

import flet as ft

from view.theme import Radius, Space, palette, tone
from view.ui_thread import control_update
from view.widgets.blocks.brand import BrandHeader
from view.widgets.blocks.file_icon import FileIcon
from view.widgets.buttons.icon_button import IconButton
from view.widgets.buttons.primary_icon_button import PrimaryIconButton
from view.widgets.containers.pill import Pill
from view.widgets.containers.pointer_area import PointerArea
from view.widgets.feedback.empty_state import EmptyState
from view.widgets.text.label import Label

if TYPE_CHECKING:
    # Annotation-only: the screen imports this module, so a real import here
    # would be a cycle.
    from view.user.screens.search_view import SearchView

#: Wide enough for a hit row.
WIDTH = 330

#: Height of the query line. Fixed, so the box keeps its size when the clear
#: button appears - a bare icon button is taller than the field.
SEARCH_HEIGHT = 40

#: The submit button is inset inside that line, which keeps the field the
#: widest thing in the sidebar.
SEARCH_BUTTON = 32


class SearchSidebar(ft.Container):
    """The column itself: its width, its fill and the rule down its right.

    None of that changes with a search, so the panel inside is what gets
    redrawn.
    """

    def __init__(self, search_view: "SearchView"):
        super().__init__()
        self.search_view = search_view
        # Hand ourselves back, so the view redraws this column directly when
        # the query or the picked hit changes.
        search_view.attach_sidebar(self)
        self.search_panel = SearchPanel(search_view)

    def build(self):
        p = palette()
        self.width = WIDTH
        self.bgcolor = p.sidebar
        self.border = ft.Border.only(right=ft.BorderSide(1, p.border))
        self.content = self.search_panel

    def refresh(self):
        self.search_panel.refresh()


class SearchPanel(ft.Column):
    """What the sidebar holds: the brand, the query line and the hits."""

    def __init__(self, search_view: "SearchView"):
        super().__init__()
        self.search_view = search_view

    def build(self):
        self.controls = self._blocks()
        self.spacing = 0
        self.expand = True

    def refresh(self):
        self.controls = self._blocks()
        control_update(self)

    def _blocks(self):
        p = palette()
        return [
            # The rule under the brand is a border rather than a row of its
            # own: inside the box it lands on the same line as the one under
            # the file bar, which is drawn the same way and given the same
            # height.
            BrandHeader("User Portal"),
            self._search_block(),
            ft.Container(height=1, bgcolor=p.border_soft),
            self._results_header(),
            ft.Container(
                content=self._results_list(),
                padding=ft.Padding.only(left=Space.SM, right=Space.SM, bottom=Space.SM),
                expand=True,
            ),
        ]

    def _search_block(self):
        p = palette()
        search_view = self.search_view

        # The height sits on the box below, not on the field: a forced height
        # here renders the input decoration at the top of its box.
        text_field = ft.TextField(
            value=search_view.search_query,
            hint_text="Ask for a note or a command ...",
            hint_style=ft.TextStyle(size=13, color=p.text_faint),
            text_size=13,
            autofocus=True,
            dense=True,
            expand=True,
            content_padding=ft.Padding.symmetric(horizontal=0, vertical=Space.SM),
            border_color="transparent",
            focused_border_color="transparent",
            on_submit=lambda e: search_view.search(e.control.value),
        )

        line = [text_field]
        if search_view.search_query:
            line.append(
                IconButton(ft.Icons.CLOSE_ROUNDED, "Clear", lambda _: search_view.clear())
            )

        return ft.Container(
            content=ft.Row(
                [
                    # `expand` so the field takes whatever the button leaves.
                    ft.Container(
                        content=ft.Row(line, spacing=Space.XS,
                                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor=p.surface,
                        border=ft.Border.all(1, p.border),
                        border_radius=Radius.MD,
                        padding=ft.Padding.only(left=Space.MD, right=0),
                        height=SEARCH_HEIGHT,
                        expand=True,
                    ),
                    PrimaryIconButton(
                        ft.Icons.SEARCH_ROUNDED,
                        "Search",
                        lambda _: search_view.search(text_field.value),
                        size=SEARCH_BUTTON,
                    ),
                ],
                spacing=Space.XS,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=Space.SM, vertical=Space.SM),
        )

    def _results_header(self):
        search_view = self.search_view
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(content=Label("Results"), expand=True),
                    self._results_pill(),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=Space.MD, right=Space.MD, top=Space.MD,
                                    bottom=Space.SM),
        )

    def _results_pill(self):
        """The count, or what the search is doing instead of having one."""
        search_view = self.search_view
        if search_view.is_searching:
            return Pill("searching", "primary")
        if search_view.status == "failed":
            return Pill("failed", "danger")
        if search_view.is_searched:
            return Pill(str(len(search_view.get_search_results())), "success")
        if search_view.is_initialising:
            return Pill("loading", "warning")
        return ft.Container()

    def _loading_block(self):
        """The model loading, before anything has been searched for.

        A spinner rather than an `EmptyState`: that one badges an icon, and a
        wait this long needs something that visibly moves. It says what is
        happening, because a portal that looks ready but answers slowly is
        worse than one that admits it is still getting up.
        """
        p = palette()
        return ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(width=26, height=26, stroke_width=3),
                    ft.Container(height=Space.MD),
                    ft.Text("Getting search ready", size=13, weight=ft.FontWeight.W_600,
                            color=p.text),
                    ft.Text("Loading the embedding model. It happens once, and you can "
                            "type your question while it finishes.",
                            size=11, color=p.text_muted, text_align=ft.TextAlign.CENTER),
                ],
                spacing=2,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            height=200,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=0),
        )

    def _results_list(self):
        p = palette()
        search_view = self.search_view

        if not search_view.is_searched:
            # The wait wins over "no search yet": both mean an empty list, but
            # only one of them is something happening.
            if search_view.is_initialising:
                return self._loading_block()
            return EmptyState(
                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                "No search yet",
                "Matching files will be listed here, closest first.",
                height=200,
            )

        if search_view.is_searching:
            return EmptyState(
                ft.Icons.HOURGLASS_TOP_ROUNDED,
                "Searching ...",
                "The first search of a session loads the embedding model.",
                height=200,
            )

        if not search_view.get_search_results():
            return EmptyState(
                ft.Icons.SEARCH_OFF_ROUNDED,
                "No matches",
                "Nothing in the collection came back for that.",
                height=200,
            )

        return ft.Column(
            [
                PointerArea(
                    SearchHit(index, result, is_selected=index == search_view.selected_index),
                    on_click=lambda _, i=index: search_view.select(i),
                    hover_bgcolor=None if index == search_view.selected_index else p.surface_high,
                )
                for index, result in enumerate(search_view.get_search_results())
            ],
            spacing=Space.XS,
            scroll=ft.ScrollMode.AUTO,
        )


class SearchHit(ft.Container):
    """One ranked file: position, name, folder and how close it scored.

    Styling only - the click and the hover belong to the `PointerArea` this is
    wrapped in.
    """

    def __init__(self, index, result, is_selected):
        super().__init__()
        self.index = index
        self.result = result
        self.is_selected = is_selected

    @staticmethod
    def score_tone(score):
        if score >= 0.65:
            return tone("success")[0]
        if score >= 0.4:
            return tone("primary")[0]
        return tone("warning")[0]

    def build(self):
        p = palette()
        score = self.result.score
        score_color = self.score_tone(score)

        self.content = ft.Row(
            [
                ft.Container(
                    content=ft.Text(str(self.index + 1), size=11, weight=ft.FontWeight.W_700,
                                    color=p.primary if self.is_selected else p.text_faint),
                    width=12,
                ),
                FileIcon(self.result.kind, size=32),
                ft.Column(
                    [
                        ft.Text(self.result.name, size=12, weight=ft.FontWeight.W_600, color=p.text,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(self.result.folder or "(root)", size=10, color=p.text_faint,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Container(height=3),
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.ProgressBar(
                                        value=score,
                                        bgcolor=p.surface_high,
                                        color=score_color,
                                        bar_height=4,
                                    ),
                                    expand=True,
                                ),
                                ft.Text(f"{int(score * 100)}%", size=10,
                                        weight=ft.FontWeight.W_700, color=score_color),
                            ],
                            spacing=Space.SM,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=0,
                    expand=True,
                ),
            ],
            spacing=Space.SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.padding = ft.Padding.symmetric(horizontal=Space.SM, vertical=Space.SM)
        self.bgcolor = p.primary_soft if self.is_selected else "transparent"
        self.border_radius = Radius.MD
