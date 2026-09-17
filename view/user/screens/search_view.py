"""Search screen: query and ranked hits on the left, file content on the right.

The screen owns the state both sides share and the reading pane itself. The
sidebar is built by `UserPortal` and hands itself back here, so the two talk
directly from then on - picking a hit redraws each of them.

A query goes to `SearchService`, which embeds it with the same model the
documents were embedded with. That model loads on the first search of a
process and takes seconds, so a search runs on a worker thread and the screen
draws a searching state meanwhile. Open in Drive is not wired up.

What the pane reads is the *original* file, from `SourceFileService` - the
copy under the input folder that still has its base64 images in it, rather
than the converted text those images were read out of. So a screenshot in a
Google Doc is a picture here again instead of the OCR of one. The embedded
text is the fallback for a document whose source has gone: see
services/source_file_service/source_file_service.py.
"""

import flet as ft

from model.SearchResult import SearchResult
from services.DriveFileService import driveFileService
from services.library_file.markdown_file import MarkdownFile
from services.search_service.search_service import searchService
from services.source_file_service.source_file_service import SourceFileService
from view.base_view import BaseView
from view.clipboard import copy_to_clipboard
from view.theme import Radius, Space, palette
from view.ui_thread import is_mounted, control_update
from view.user.screens.markdown_block_parser import MarkdownBlockParser
from view.user.search_sidebar import SearchSidebar
from view.widgets.blocks.brand import BrandHeader
from view.widgets.blocks.file_icon import FileIcon
from view.widgets.buttons.icon_button import IconButton
from view.widgets.buttons.primary_button import PrimaryButton
from view.widgets.containers.card import Card
from view.widgets.containers.icon_badge import IconBadge
from view.widgets.containers.pill import Pill
from view.widgets.feedback.empty_state import EmptyState
from view.widgets.text.label import Label
from view.widgets.text.mono import Mono

#: Both panes open on a header - the brand in the sidebar, the file bar in the
#: reading pane - and they share this height so the rule under each of them
#: lands on the same line.
HEADER_HEIGHT = BrandHeader.HEIGHT

#: One file on Drive. `open?id=` rather than `file/d/<id>`, because the library
#: is mixed: `file/d/` is the viewer for uploaded files, while a native Google
#: Doc lives at docs.google.com/document/d/. `open` redirects to whichever is
#: right for the id it is given.
DRIVE_FILE_URL = "https://drive.google.com/open?id={drive_id}"


def drive_url(result):
    """The Drive link for this document, or None when there is not one.

    The file itself or nothing. A document whose download never recorded a
    Drive id - everything embedded before the drive_file table existed - has
    no link, and the button is disabled rather than sending someone to the
    folder instead, which is not the file they asked for.
    """
    if not result.drive_id:
        return None
    return DRIVE_FILE_URL.format(drive_id=result.drive_id)


class SearchView(BaseView):
    """Both panes of the user portal, and the state they share."""

    #: Set by `SearchSidebar` as it is built - see `attach_sidebar`. The
    #: sidebar is constructed by the portal, but the two talk directly after
    #: that. Declared rather than assigned: an annotation with no value is
    #: what tells the editor the type without pretending a `None` is one.
    search_sidebar: SearchSidebar

    def __init__(self):
        super().__init__()
        self.search_query = ""
        self.selected_index = 0
        #: idle | searching | done | failed
        self.status = "idle"
        #: The hits of the last finished search.
        self.search_results = []
        #: Why the last search failed, when it did.
        self.error = None
        #: Whether the embedding model is still loading. True from the start:
        #: `UserPortal.did_mount` kicks the load off as soon as the portal is
        #: drawn, which is before anything here gets a chance to set it, so
        #: the first paint has to already say so.
        self.is_initialising = True
        #: Reads the picked hit's original file - what the pane draws, when
        #: the source is still on disk.
        self.source_file_service = SourceFileService()

        # The reading pane runs to the window edges - no padding frame.
        self.reader_container = ft.Container(expand=True)
        self._fill_reader()

    def attach_sidebar(self, search_sidebar: SearchSidebar):
        """Take the sidebar that reads this view, so `refresh` can redraw it."""
        self.search_sidebar = search_sidebar

    def build(self):
        """The shell places the two panes itself, so there is nothing to
        return as one control. Kept to satisfy `BaseView`."""
        return self.reader_container

    @property
    def is_searched(self):
        return self.status != "idle"

    @property
    def is_searching(self):
        return self.status == "searching"

    def get_search_results(self) -> list[SearchResult]:
        """The hits, closest first - the order chroma already returns them in."""
        return self.search_results

    def get_search_result(self) -> SearchResult | None:
        """The hit the reading pane is showing, or None when there are none."""
        if not self.search_results:
            return None
        return self.search_results[min(self.selected_index, len(self.search_results) - 1)]

    def search(self, search_query):
        """Runs on a worker thread: the first search of a process loads the
        embedding model, which would freeze the window for seconds."""
        search_query = (search_query or "").strip()
        if not search_query:
            self.clear()
            return

        self.search_query = search_query
        self.selected_index = 0
        self.status = "searching"
        self.search_results = []
        self.error = None
        self.refresh()

        if not is_mounted(self.reader_container):
            # Nothing is driving a UI to keep responsive, so run it here. This
            # is the path a test takes; the app always has a page.
            self.run_search()
            return
        self.reader_container.page.run_thread(self.run_search)

    def init_search(self):
        """Load the embedding model, with the sidebar saying so meanwhile.

        Blocking - `UserPortal.did_mount` puts it on a worker thread. The flag
        is cleared whatever happens: a model that will not load is still not
        loading any more, and leaving the spinner up would promise a wait that
        has already ended. The failure itself surfaces on the first search.
        """
        try:
            searchService.init_collection()
        finally:
            self.is_initialising = False
            self.refresh()

    def run_search(self):
        try:
            self.search_results = searchService.search(self.search_query)
            self.status = "done"
        except Exception as error:
            self.search_results = []
            self.error = str(error)
            self.status = "failed"
        # A finished search means the model is loaded, however it got there -
        # this is what clears the flag if `init_search` never ran.
        self.is_initialising = False
        self.refresh()

    def clear(self):
        self.search_query = ""
        self.selected_index = 0
        self.status = "idle"
        self.search_results = []
        self.error = None
        self.refresh()

    def select(self, index):
        self.selected_index = index
        self.refresh()

    def refresh(self):
        """Both panes move together - picking a hit changes each of them."""
        self.search_sidebar.refresh()
        self._fill_reader()
        control_update(self.reader_container)

    def _fill_reader(self):
        result = self.get_search_result()
        if result is not None:
            # Filled in here rather than by the widget, which reads it back off
            # the result: a widget's `build()` runs inside flet's
            # reconciliation pass, on the event loop, so a file read there
            # would block every redraw. Here, the path that follows a search is
            # already on the worker thread.
            result.original_file_text = self.source_file_service.find_original_file_text(result.document_id)
            result.drive_id = driveFileService.find_drive_id(result.document_id)
            self.reader_container.content = SearchFilePreviewContainer(result)
        elif self.status == "searching":
            self.reader_container.content = SearchingContainer(self.search_query)
        elif self.status == "failed":
            self.reader_container.content = SearchFailedContainer(self.error)
        elif self.status == "done":
            self.reader_container.content = NoResultsContainer(self.search_query)
        else:
            self.reader_container.content = SearchIntroductionContainer()


class SearchIntroductionContainer(ft.Container):
    """What the reading pane shows before anything has been asked."""

    def build(self):
        p = palette()
        self.content = ft.Column(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.TRAVEL_EXPLORE_ROUNDED, size=34, color=p.primary),
                    width=72,
                    height=72,
                    bgcolor=p.primary_soft,
                    border_radius=Radius.XL,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(height=Space.XL),
                ft.Text("Search your knowledge drive", size=27,
                        weight=ft.FontWeight.W_700, color=p.text),
                ft.Text(
                    "Ask on the left and the closest notes, screenshots and cheat sheets "
                    "are listed there - the one you pick is read here.",
                    size=14,
                    color=p.text_muted,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=0,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.alignment = ft.Alignment.CENTER
        self.expand = True


class CentredMessageContainer(ft.Container):
    """A reading pane with one message in the middle of it.

    The three states that are not a file all look like this - only the badge
    and the words change.
    """

    def __init__(self, badge, heading, message):
        super().__init__()
        self.badge = badge
        self.heading = heading
        self.message = message

    def build(self):
        p = palette()
        self.content = ft.Column(
            [
                self.badge,
                ft.Container(height=Space.XL),
                ft.Text(self.heading, size=20, weight=ft.FontWeight.W_700, color=p.text),
                ft.Text(self.message, size=13, color=p.text_muted,
                        text_align=ft.TextAlign.CENTER),
            ],
            spacing=0,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.alignment = ft.Alignment.CENTER
        self.expand = True
        self.padding = Space.XXL


class SearchingContainer(CentredMessageContainer):
    """Shown while the worker thread is searching.

    The first search of a process loads the embedding model, which is why the
    wait is worth a message rather than being over before it is drawn.
    """

    def __init__(self, query):
        super().__init__(
            ft.ProgressRing(width=34, height=34, stroke_width=3),
            "Searching ...",
            f"Looking for the closest documents to “{query}”. The first search "
            "loads the embedding model, so it takes a moment.",
        )


class NoResultsContainer(CentredMessageContainer):
    """A search that ran and found nothing."""

    def __init__(self, query):
        super().__init__(
            IconBadge(ft.Icons.SEARCH_OFF_ROUNDED, "neutral", size=72, icon_size=34),
            "Nothing close enough",
            f"No document came back for “{query}”. If the library is empty, run a "
            "reset from the admin portal first.",
        )


class SearchFailedContainer(CentredMessageContainer):
    """The search raised - a missing store, or a model that will not load."""

    def __init__(self, error):
        super().__init__(
            IconBadge(ft.Icons.ERROR_ROUNDED, "danger", size=72, icon_size=34),
            "Search failed",
            error or "Something went wrong.",
        )


class SearchFilePreviewContainer(ft.Column):
    """The file bar tops the pane; the file itself fills what is left.

    Both run to the window edge, so the rule under the bar is the only line
    between them - an outline round either would double the sidebar border on
    the left and be clipped on the right.
    """

    def __init__(self, result: SearchResult):
        super().__init__()
        self.result = result

    def build(self):
        self.controls = [
            FileHeader(self.result),
            FileBody(self.result)
        ]
        self.spacing = 0
        self.expand = True


class FileHeader(Card):
    """One bar over the text: what the file is and the Drive actions.

    How close the file scored is left to its row in the sidebar, which is
    where the hits are compared against each other.
    """

    def __init__(self, result: SearchResult):
        p = palette()

        # `url` is a field on every flet button, so following it is native -
        # the OS opens the default browser, with no handler and no page to
        # reach for. Set after construction, the way the other buttons in this
        # app take their state.
        drive_link = drive_url(result)
        open_in_drive_button = PrimaryButton("Open in Google Drive",
                                             icon=ft.Icons.OPEN_IN_NEW_ROUNDED, is_dense=True)
        open_in_drive_button.url = drive_link
        open_in_drive_button.disabled = drive_link is None
        # A disabled button says why rather than just refusing: the mapping
        # arrives with a run, so there is something to do about it.
        open_in_drive_button.tooltip = (
            "Open this file in Google Drive" if drive_link is not None
            else "Not linked to Drive yet - run a sync or a reset to map this file"
        )

        super().__init__(
            ft.Row(
                [
                    FileIcon(result.kind, size=30),
                    ft.Text(result.name, size=14, weight=ft.FontWeight.W_700, color=p.text,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    # The folder soaks up the slack, so the actions stay put and
                    # a deep path is the first thing to be cut.
                    ft.Text(result.folder or "(root)", size=11, color=p.text_muted, expand=True,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Container(width=1, height=22, bgcolor=p.border_soft),
                    ft.Container(
                        content=Mono(result.document_id, size=10, color=p.text, max_lines=1,
                                     overflow=ft.TextOverflow.ELLIPSIS,
                                     tooltip=result.document_id),
                        width=104,
                    ),
                    ft.Text(result.modified, size=10, color=p.text_faint,
                            tooltip=f"{result.kind} - modified {result.modified}"),
                    # Was "Copy Drive link", which this cannot do: a Drive URL
                    # needs the Drive file id and the collection stores the
                    # converted path as its id. The path is what the row
                    # already shows, so that is what it copies.
                    IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy document id",
                               lambda e, r=result: copy_to_clipboard(
                                   e.control, r.document_id, "the document id")),
                    open_in_drive_button,
                ],
                spacing=Space.SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            radius=0,
            border=ft.Border.only(bottom=ft.BorderSide(1, p.border)),
            height=HEADER_HEIGHT,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=0),
        )


class FileBody(Card):
    """The file itself - the original where there is one, and its pictures.

    The original is the copy under the input folder, which still has its
    base64 images in it. The converted text is the fallback for a document
    whose source has gone, and reads the way this pane always did: the images
    already replaced by the text OCR found in them.

    Reading the file into blocks is `MarkdownBlockParser`'s job; `_block` below
    draws what it hands back.
    """

    def __init__(self, result: SearchResult):
        is_original = result.is_original
        blocks = MarkdownBlockParser().parse(result.display_text)

        # A converted file opens with its own title, which the header above
        # already shows, so that first heading is dropped.
        body = [
            self._block(kind, payload)
            for index, (kind, payload) in enumerate(blocks)
            if not (index == 0 and kind == "h1")
        ]
        if not blocks:
            body.append(
                EmptyState(
                    ft.Icons.DESCRIPTION_OUTLINED,
                    "Nothing to read" if is_original else "No converted text",
                    "The original file is empty." if is_original
                    else "This file has not been converted yet, so there is nothing to read.",
                    height=240,
                )
            )

        super().__init__(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(content=Label("File content"), expand=True),
                            # Which of the two is on screen, because they are
                            # not the same file: one has the pictures, the
                            # other has the text that was read out of them.
                            Pill(
                                "Original file" if is_original else "Converted text",
                                "primary" if is_original else "neutral",
                                icon=(ft.Icons.IMAGE_ROUNDED if is_original
                                      else ft.Icons.ARTICLE_ROUNDED),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=Space.MD),
                    ft.Container(
                        content=ft.Column(body, spacing=0, scroll=ft.ScrollMode.AUTO),
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            radius=0,
            border=None,
            padding=Space.MD,
            expand=True,
        )

    def _block(self, kind, payload):
        p = palette()
        text = payload

        if kind == "image":
            return ft.Container(
                # flet 0.86 dropped `src_base64`; `src` takes the raw bytes.
                # SCALE_DOWN rather than CONTAIN, and no width or height: a
                # screenshot wider than the pane is shrunk to fit it, and a
                # small inline icon is left at its own size instead of being
                # blown up to fill a box.
                content=ft.Image(
                    src=payload,
                    fit=ft.BoxFit.SCALE_DOWN,
                    border_radius=Radius.SM,
                    error_content=ft.Text(MarkdownFile.UNREADABLE_IMAGE_TEXT,
                                          size=12, color=p.text_faint),
                ),
                alignment=ft.Alignment.CENTER_LEFT,
                padding=ft.Padding.only(top=Space.XS, bottom=Space.MD),
            )

        if kind in ("h1", "h2"):
            return ft.Container(
                content=ft.Text(text, size=16 if kind == "h1" else 14,
                                weight=ft.FontWeight.W_700, color=p.text),
                padding=ft.Padding.only(top=Space.MD, bottom=Space.XS),
            )

        if kind == "code":
            return ft.Container(
                content=Mono(text, size=12, color=p.text, selectable=True),
                bgcolor=p.surface_alt,
                border=ft.Border.all(1, p.border_soft),
                border_radius=Radius.SM,
                padding=Space.MD,
                margin=ft.Margin.only(top=Space.XS, bottom=Space.SM),
            )

        if kind == "bullet":
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(width=5, height=5, bgcolor=p.text_faint,
                                     border_radius=Radius.PILL,
                                     margin=ft.Margin.only(top=6)),
                        ft.Text(text, size=13, color=p.text_muted, selectable=True, expand=True),
                    ],
                    spacing=Space.MD,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=ft.Padding.only(left=Space.SM, bottom=Space.XS),
            )

        return ft.Container(
            content=ft.Text(text, size=13, color=p.text, selectable=True),
            padding=ft.Padding.only(bottom=Space.SM),
        )
