"""Library: folder tree over the embedded documents.

The documents are nested under the folders their labels spell out, so a Drive
folder reads the same here as on the sync screen. It opens collapsed to the
top-level folders and is browsed by opening them rather than paged through.

The screen and its blocks live together - each is one part of this one screen.

The documents come from the collection itself, through `LibraryService` -
metadata only, so nothing here loads the embedding model. Copy and
open-in-Drive are still not wired up.
"""

import flet as ft

from constant.settings import EMBEDDING_COLLECTION
from services.SettingService import settingService
from services.library_service.library_service import LibraryService
from view.base_view import BaseView
from view.clipboard import copy_to_clipboard
from view.theme import Field, Radius, Space, palette
from view.widgets.blocks.file_icon import FileIcon
from view.widgets.blocks.page_header import PageHeader
from view.widgets.blocks.stat_card import StatCard
from view.widgets.buttons.ghost_button import GhostButton
from view.widgets.buttons.icon_button import IconButton
from view.widgets.containers.pill import Pill
from view.widgets.containers.pointer_area import PointerArea
from view.widgets.containers.section import SectionCard
from view.widgets.feedback.empty_state import EmptyState
from view.widgets.feedback.notice_bar import NoticeBar
from view.widgets.text.label import Label
from view.widgets.text.mono import Mono

#: How far each folder level is pushed in.
INDENT = 22

#: Columns shared by the header and every document row.
ID_WIDTH = 290
TYPE_WIDTH = 80
ACTIONS_WIDTH = 88


class LibraryView(BaseView):

    # The tree carries the only scrollbar on this screen - the heading, the
    # stat cards and the column header stay put while the rows move.
    scrolls = False

    def __init__(self, portal=None):
        super().__init__(portal)
        self.filter_text = ""
        self.folders_open = {}
        #: Every Document in the collection, read once when the screen opens.
        self.documents = []
        #: Why the read failed, when it did.
        self.error = None
        # Held so refresh() can redraw after a filter or a folder toggle.
        self.body_container = ft.Container(expand=True)
        self.load()

    def build(self):
        self.body_container.content = self._layout()
        return self.body_container

    def refresh(self):
        self.body_container.content = self._layout()
        self.body_container.update()

    def load(self):
        """Read the collection. A failure is shown, not raised - a missing
        store or an unreadable one should leave the screen usable."""
        try:
            self.documents = LibraryService().find_all_documents()
            self.error = None
        except Exception as error:
            self.documents = []
            self.error = str(error)

    def reload(self, _=None):
        self.load()
        self.refresh()

    def filtered(self):
        needle = self.filter_text.strip().lower()
        if not needle:
            return self.documents
        return [
            document for document in self.documents
            if needle in document.label.lower() or needle in document.document_id.lower()
        ]

    def is_folder_open(self, path):
        """Folders start closed, so the screen opens on the top-level folders
        alone and you drill in from there. A filter opens everything - a hit is
        no use hidden - and an explicit click otherwise always wins."""
        if self.filter_text.strip():
            return True
        return self.folders_open.get(path, False)

    @staticmethod
    def build_tree(documents):
        """Nest documents under their folders, keyed by path segment."""
        root = {"folders": {}, "files": []}
        for document in documents:
            folder = document.folder
            node = root
            for segment in folder.split("\\") if folder else []:
                node = node["folders"].setdefault(segment, {"folders": {}, "files": []})
            node["files"].append(document)
        return root

    @classmethod
    def folder_count(cls, node):
        """Every folder under this node, not just its direct children."""
        return len(node["folders"]) + sum(
            cls.folder_count(child) for child in node["folders"].values()
        )

    def _layout(self):
        documents = self.filtered()
        tree = self.build_tree(documents)
        collection = settingService.find_active_by_key(EMBEDDING_COLLECTION)

        notice = []
        if self.error is not None:
            notice = [
                NoticeBar(f"Could not read the collection: {self.error}", "danger"),
                ft.Container(height=Space.LG),
            ]

        return ft.Column(
            [
                PageHeader(
                    "Library",
                    f"{len(self.documents)} documents embedded in {collection}.",
                    actions=[GhostButton("Refresh", icon=ft.Icons.REFRESH_ROUNDED,
                                         on_click=self.reload)],
                ),
                ft.Container(height=Space.XL),
                *notice,
                LibraryStats(len(self.documents), len(documents),
                             len(tree["folders"]), self.folder_count(tree)),
                ft.Container(height=Space.LG),
                DocumentsSection(self, tree),
            ],
            spacing=0,
            expand=True,
        )


class LibraryStats(ft.Row):
    """The three tiles above the listing."""

    def __init__(self, total, matching, top_level_folders, all_folders):
        super().__init__()
        self.total = total
        self.matching = matching
        self.top_level_folders = top_level_folders
        self.all_folders = all_folders

    def build(self):
        self.controls = [
            StatCard(ft.Icons.STORAGE_ROUNDED, "Total documents", str(self.total),
                     None, "primary"),
            StatCard(ft.Icons.FILTER_ALT_ROUNDED, "Matching filter", str(self.matching),
                     None, "info"),
            StatCard(ft.Icons.FOLDER_ROUNDED, "Top-level folders", str(self.top_level_folders),
                     f"{self.all_folders} in total", "warning"),
        ]
        self.spacing = Space.LG


class DocumentsSection(SectionCard):
    """The folder tree, its column header and the filter toolbar.

    Takes the screen rather than a pile of callbacks: it reads the filter and
    the open folders off it, and calls back into it to redraw.
    """

    def __init__(self, view, tree):
        self.view = view
        p = palette()

        def on_filter(e):
            view.filter_text = e.control.value
            view.refresh()

        def set_folders(is_open):
            def handler(_):
                view.folders_open = {path: is_open for path in self.folder_ids()}
                view.refresh()
            return handler

        toolbar = ft.Row(
            [
                ft.TextField(
                    value=view.filter_text,
                    hint_text="Filter by path or id",
                    hint_style=ft.TextStyle(size=Field.TEXT_SIZE, color=p.text_faint),
                    prefix_icon=ft.Icons.SEARCH_ROUNDED,
                    text_size=Field.TEXT_SIZE,
                    width=Field.WIDTH,
                    height=Field.HEIGHT,
                    dense=True,
                    content_padding=Field.padding(),
                    filled=True,
                    fill_color=p.surface_alt,
                    border_color=p.border,
                    focused_border_color=p.primary,
                    border_radius=Radius.MD,
                    on_change=on_filter,
                    on_submit=on_filter,
                ),
                IconButton(ft.Icons.UNFOLD_MORE_ROUNDED, "Expand all folders", set_folders(True)),
                IconButton(ft.Icons.UNFOLD_LESS_ROUNDED, "Collapse all folders",
                           set_folders(False)),
            ],
            spacing=Space.SM,
        )

        super().__init__(
            "Embedded documents",
            "Nested by folder, with the Chroma document id beside each file.",
            trailing=toolbar,
            content=self._listing(tree),
            fill=True,
            expand=True,
        )

    def _listing(self, tree):
        p = palette()

        if not tree["folders"] and not tree["files"]:
            # An empty collection and an over-narrow filter look identical in
            # the tree, but there is nothing to try differently in the first.
            if not self.view.documents:
                return EmptyState(
                    ft.Icons.INBOX_ROUNDED,
                    "Nothing is embedded yet",
                    "Run a reset from Library Sync to fill the collection.",
                )
            return EmptyState(
                ft.Icons.SEARCH_OFF_ROUNDED,
                "No documents match that filter",
                "Try a shorter path fragment, or clear the filter to list everything.",
            )

        # Only the rows scroll: the column header and the rule above them are
        # outside the scrolling column, so they stay pinned to the card.
        return ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(content=Label("Name"), expand=True),
                            ft.Container(content=Label("Document id"), width=ID_WIDTH),
                            ft.Container(content=Label("Type"), width=TYPE_WIDTH),
                            ft.Container(width=ACTIONS_WIDTH),
                        ],
                        spacing=Space.MD,
                    ),
                    padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
                ),
                ft.Container(height=1, bgcolor=p.border_soft),
                ft.Column(self._rows(tree), spacing=0, scroll=ft.ScrollMode.AUTO, expand=True),
            ],
            spacing=0,
            expand=True,
        )

    def folder_ids(self):
        """Every folder path in the library, including the prefixes that chain
        collapsing hides - setting one of those is harmless."""
        ids = set()
        for document in self.view.documents:
            segments = document.folder.split("\\") if document.folder else []
            for index in range(1, len(segments) + 1):
                ids.add("\\".join(segments[:index]))
        return ids

    @staticmethod
    def collapse(name, node):
        """Squash a folder holding one subfolder and no files into one row.

        Keeps deep paths like Python\\Python Notes\\Async on a single line
        instead of spending three levels of indent on them.
        """
        while not node["files"] and len(node["folders"]) == 1:
            child_name, child = next(iter(node["folders"].items()))
            name = f"{name}\\{child_name}"
            node = child
        return name, node

    @classmethod
    def doc_count(cls, node):
        """Every document under this node, not just its direct files."""
        return len(node["files"]) + sum(
            cls.doc_count(child) for child in node["folders"].values()
        )

    def _rows(self, node, depth=0, parent_path=""):
        rows = []
        for name in sorted(node["folders"], key=str.lower):
            label, child = self.collapse(name, node["folders"][name])
            path = f"{parent_path}\\{label}" if parent_path else label
            is_open = self.view.is_folder_open(path)
            rows.append(self._folder_row(path, label, self.doc_count(child), depth, is_open))
            if is_open:
                rows += self._rows(child, depth + 1, path)
        for document in sorted(node["files"], key=lambda d: d.label.lower()):
            rows.append(self._doc_row(document, depth))
        return rows

    @staticmethod
    def _row_padding(depth):
        return ft.Padding.only(left=Space.MD + depth * INDENT, right=Space.MD,
                               top=Space.SM, bottom=Space.SM)

    @staticmethod
    def _on_hover(e):
        p = palette()
        e.control.bgcolor = p.surface_alt if (e.data is True or e.data == "true") else "transparent"
        e.control.update()

    def _folder_row(self, path, label, count, depth, is_open):
        p = palette()
        view = self.view

        def toggle_open(_):
            view.folders_open[path] = not is_open
            view.refresh()

        return PointerArea(
            content = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.EXPAND_MORE_ROUNDED if is_open else ft.Icons.CHEVRON_RIGHT_ROUNDED,
                        size=16,
                        color=p.text_muted,
                    ),
                    ft.Icon(
                        ft.Icons.FOLDER_OPEN_ROUNDED if is_open else ft.Icons.FOLDER_ROUNDED,
                        size=16,
                        color=p.text_faint,
                    ),
                    ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=p.text_muted,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    Pill(str(count)),
                    ft.Container(expand=True),
                ],
                spacing=Space.SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=self._row_padding(depth),
            border_radius=Radius.SM,
            bgcolor="transparent",
        ), 
        on_click=toggle_open,
        hover_bgcolor=p.surface_alt
    )

    def _doc_row(self, document, depth):
        p = palette()
        kind = document.kind
        _icon, kind_tone = FileIcon.KINDS.get(kind, FileIcon.KINDS["text"])

        return ft.Container(
            content=ft.Row(
                [
                    FileIcon(kind, size=26),
                    ft.Text(document.name, size=13, weight=ft.FontWeight.W_600, color=p.text,
                            overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                    ft.Container(
                        content=Mono(document.document_id, size=11,
                                     overflow=ft.TextOverflow.ELLIPSIS),
                        width=ID_WIDTH,
                    ),
                    ft.Container(content=Pill(kind, kind_tone), width=TYPE_WIDTH),
                    ft.Row(
                        [
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy document id",
                                       lambda e, d=document: copy_to_clipboard(
                                           e.control, d.document_id, "the document id")),
                            # Not wired, and cannot be from here: a Drive URL
                            # needs the Drive file id, and the collection
                            # stores the converted path as its id instead.
                            # It comes back with the `file` table, which is
                            # where drive_id would be kept.
                            IconButton(ft.Icons.OPEN_IN_NEW_ROUNDED,
                                       "Open in Google Drive - needs the file table"),
                        ],
                        spacing=0,
                        width=ACTIONS_WIDTH,
                    ),
                ],
                spacing=Space.MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=self._row_padding(depth),
            border_radius=Radius.SM,
            on_hover=self._on_hover,
        )
