"""Settings: the rows of the setting table, edited in place.

The table is the source of truth - every row shown here is a row in `setting`,
read through `settingService`, and Save writes the changed keys of one card in
a single transaction. Nothing falls back to a value in code.

Each card has a values class beside it - `PathsSettings`, `DriveSettings`,
`EmbeddingSettings` - holding that card's rows as named attributes, so the card
reads `paths.input_dir` rather than looking a key up in a dict. The rule inside
one of those classes:

    editable rows are attributes, so they can hold what you typed;
    read-only rows are properties, so they always show the table.

The three objects live on `SettingsView`, which outlives a redraw, so a
half-typed field survives one. Nothing tracks "unsaved edits" separately -
`changes()` diffs the object against the table, and Revert is `load()`.
"""

import flet as ft

from constant.paths import BASE_DIR
from constant.settings import (
    DRIVE_FOLDER_ID,
    DRIVE_SCOPE,
    DRIVE_SERVICE_ACCOUNT_FILE,
    EMBEDDING_COLLECTION,
    EMBEDDING_MODEL,
    EMBEDDING_RESULTS_PER_QUERY,
    PATHS_CHROMA_STORE,
    PATHS_INPUT_DIR,
    PATHS_OUTPUT_DIR,
)
from services.SettingService import settingService
from view.base_view import BaseView
from view.clipboard import copy_to_clipboard
from view.theme import Radius, Space, palette
from view.widgets.blocks.page_header import PageHeader
from view.widgets.blocks.row_label import RowLabel
from view.widgets.buttons.ghost_button import GhostButton
from view.widgets.buttons.icon_button import IconButton
from view.widgets.buttons.primary_button import PrimaryButton
from view.widgets.containers.divider import Divider
from view.widgets.containers.pill import Pill
from view.widgets.containers.section import SectionCard
from view.widgets.feedback.notice_bar import NoticeBar
from view.widgets.inputs.text_input import TextInput
from view.widgets.text.mono import Mono


class PathsSettings:
    """The Paths card's rows: where the pipeline reads and writes."""

    def __init__(self):
        self.load()

    def load(self):
        """(Re)read every editable row from the table - first paint and Revert."""
        self.input_dir = settingService.find_active_by_key(PATHS_INPUT_DIR)
        self.output_dir = settingService.find_active_by_key(PATHS_OUTPUT_DIR)
        self.chroma_store = settingService.find_active_by_key(PATHS_CHROMA_STORE)

    @property
    def base_dir(self):
        """Where the app is installed. Computed, not stored - see settings-table.md."""
        return BASE_DIR

    def changes(self):
        """key -> value for the rows that differ from the table."""
        changes = {}
        if self.input_dir != settingService.find_active_by_key(PATHS_INPUT_DIR):
            changes[PATHS_INPUT_DIR] = self.input_dir
        if self.output_dir != settingService.find_active_by_key(PATHS_OUTPUT_DIR):
            changes[PATHS_OUTPUT_DIR] = self.output_dir
        if self.chroma_store != settingService.find_active_by_key(PATHS_CHROMA_STORE):
            changes[PATHS_CHROMA_STORE] = self.chroma_store
        return changes

    def validate(self):
        """The message to show, or None when the values are usable.

        It does not check that a folder exists - a path can legitimately be
        typed before it is created, and the run reports a missing one properly.
        """
        if not self.input_dir.strip():
            return "Source files cannot be empty."
        if not self.output_dir.strip():
            return "Converted files cannot be empty."
        if not self.chroma_store.strip():
            return "Chroma store cannot be empty."
        return None


class DriveSettings:
    """The Google Drive card's rows: the folder the mirror is pulled from."""

    def __init__(self):
        self.load()

    def load(self):
        self.folder_id = settingService.find_active_by_key(DRIVE_FOLDER_ID)
        self.service_account_file = settingService.find_active_by_key(DRIVE_SERVICE_ACCOUNT_FILE)

    @property
    def scope(self):
        """Read-only: shown so it is visible that the app only ever reads."""
        return settingService.find_active_by_key(DRIVE_SCOPE)

    def changes(self):
        changes = {}
        if self.folder_id != settingService.find_active_by_key(DRIVE_FOLDER_ID):
            changes[DRIVE_FOLDER_ID] = self.folder_id
        if self.service_account_file != settingService.find_active_by_key(DRIVE_SERVICE_ACCOUNT_FILE):
            changes[DRIVE_SERVICE_ACCOUNT_FILE] = self.service_account_file
        return changes

    def validate(self):
        """A missing credentials file is not checked here - it fails when
        `FileDownloaderService` is built, which keeps this screen usable while
        the path is being fixed."""
        if not self.folder_id.strip():
            return "Folder id cannot be empty."
        if not self.service_account_file.strip():
            return "Service account key cannot be empty."
        return None


class EmbeddingSettings:
    """The Embedding card's rows: the model, and where the vectors live."""

    def __init__(self):
        self.load()

    def load(self):
        self.results_per_query = settingService.find_active_by_key(EMBEDDING_RESULTS_PER_QUERY)

    @property
    def model(self):
        """Read-only: changing it would make every stored vector meaningless."""
        return settingService.find_active_by_key(EMBEDDING_MODEL)

    @property
    def collection(self):
        """Read-only: the Chroma collection the store writes into."""
        return settingService.find_active_by_key(EMBEDDING_COLLECTION)

    @property
    def store(self):
        """The resolved absolute path, not the relative one Paths stores.

        A property rather than a loaded value because the Paths card can save a
        new `paths.chroma_store` while this card is on screen - this row has to
        follow it.
        """
        return settingService.get_path(PATHS_CHROMA_STORE)

    def changes(self):
        changes = {}
        if self.results_per_query != settingService.find_active_by_key(EMBEDDING_RESULTS_PER_QUERY):
            changes[EMBEDDING_RESULTS_PER_QUERY] = self.results_per_query
        return changes

    def validate(self):
        value = self.results_per_query.strip()
        if not value:
            return "Results per query cannot be empty."
        if not value.isdigit() or int(value) < 1:
            return "Results per query must be a whole number of 1 or more."
        return None


class SettingsView(BaseView):

    def __init__(self, portal=None):
        super().__init__(portal)
        # The three cards' values, held here rather than on the cards - a card
        # is rebuilt on every redraw, and what you typed has to outlive that.
        self.paths = PathsSettings()
        self.drive = DriveSettings()
        self.embedding = EmbeddingSettings()
        #: section card name -> (message, tone). One banner per card, in the card.
        self.notices = {}
        # Held so a save or a revert can redraw the cards in place.
        self.body_container = ft.Container()

    def build(self):
        self.body_container.content = self._layout()
        return self.body_container

    def refresh(self):
        self.body_container.content = self._layout()
        self.body_container.update()

    # --- banners -------------------------------------------------------------

    def response_message(self, section_card_name, message, tone_name="neutral"):
        """One banner per card, shown just above that card's own buttons.

        In the layout rather than over it, so it pushes the buttons down
        instead of covering a field you are about to fix, and it sits next to
        the Save that produced it - two cards can each hold their own message.
        """
        self.notices[section_card_name] = (message, tone_name)
        self.refresh()

    def hide_response_message(self, section_card_name):
        self.notices.pop(section_card_name, None)
        self.refresh()

    def response_message_for(self, section_card_name):
        """The card's banner, or nothing - spliced into the card's column."""
        if section_card_name not in self.notices:
            return []
        message, tone_name = self.notices[section_card_name]
        return [
            NoticeBar(message, tone_name,
                      on_hide=lambda _=None: self.hide_response_message(section_card_name)),
        ]

    # --- layout --------------------------------------------------------------

    def _layout(self):
        return ft.Column(
            [
                PageHeader(
                    "Settings",
                    "Stored in the setting table. Saving writes straight to the database.",
                    actions=[
                        GhostButton("Open config folder", icon=ft.Icons.FOLDER_OPEN_ROUNDED),
                    ],
                ),
                ft.Container(height=Space.XL),
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Column(
                                [
                                    PathsSectionCard(self),
                                    DriveSectionCard(self),
                                ],
                                spacing=Space.LG,
                            ),
                            expand=3,
                        ),
                        ft.Container(
                            content=EmbeddingSectionCard(self),
                            expand=2,
                        ),
                    ],
                    spacing=Space.LG,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=0,
        )


class PathsSectionCard(SectionCard):
    """Where the pipeline reads and writes."""

    SECTION_CARD_NAME = "paths"

    def __init__(self, view: SettingsView):
        p = palette()
        paths = view.paths
        super().__init__(
            "Paths",
            "Where the pipeline reads and writes.",
            content=ft.Column(
                [
                    ft.Row(
                        [
                            RowLabel("Base directory"),
                            ft.Container(
                                content=Mono(paths.base_dir, size=12, color=p.text),
                                expand=True,
                            ),
                            # The value is read when the button is pressed, not
                            # when the row is built, so an edited path copies
                            # as it reads on screen rather than as it is saved.
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy base directory",
                                       lambda e: copy_to_clipboard(
                                           e.control, paths.base_dir, "the base directory")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Source files"),
                            TextInput(paths.input_dir, is_mono=True,
                                      on_change=self.edit_input_dir),
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy source files",
                                       lambda e: copy_to_clipboard(
                                           e.control, paths.input_dir,
                                           "the source files path")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Converted files"),
                            TextInput(paths.output_dir, is_mono=True,
                                      on_change=self.edit_output_dir),
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy converted files",
                                       lambda e: copy_to_clipboard(
                                           e.control, paths.output_dir,
                                           "the converted files path")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Chroma store"),
                            TextInput(paths.chroma_store, is_mono=True,
                                      on_change=self.edit_chroma_store),
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy chroma store",
                                       lambda e: copy_to_clipboard(
                                           e.control, paths.chroma_store,
                                           "the chroma store path")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, size=15,
                                        color=p.text_faint),
                                ft.Text(
                                    "Stored relative to the base directory, so the database "
                                    "survives moving the project folder. An absolute path is "
                                    "used as-is.",
                                    size=11,
                                    color=p.text_muted,
                                    expand=True,
                                ),
                            ],
                            spacing=Space.SM,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        padding=Space.MD,
                        bgcolor=p.surface_alt,
                        border_radius=Radius.SM,
                    ),
                    Divider(bottom=Space.SM),
                    *view.response_message_for(self.SECTION_CARD_NAME),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            GhostButton("Revert", icon=ft.Icons.UNDO_ROUNDED, is_dense=True,
                                        on_click=self.revert),
                            PrimaryButton("Save", icon=ft.Icons.CHECK_ROUNDED, is_dense=True,
                                          on_click=self.save),
                        ],
                        spacing=Space.SM,
                    ),
                ],
                spacing=Space.MD,
            ),
        )
        # After super(), which is what actually builds the card above. The
        # handlers only run on a click, by which time these are set.
        self.view = view
        self.paths = paths

    def edit_input_dir(self, e):
        self.paths.input_dir = e.control.value

    def edit_output_dir(self, e):
        self.paths.output_dir = e.control.value

    def edit_chroma_store(self, e):
        self.paths.chroma_store = e.control.value

    def save(self, _=None):
        changes = self.paths.changes()
        if not changes:
            self.view.response_message(self.SECTION_CARD_NAME, "No changes to paths.", "neutral")
            return

        error = self.paths.validate()
        if error:
            self.view.response_message(self.SECTION_CARD_NAME, error, "danger")
            return

        try:
            settingService.update_all(changes)
        except Exception as error:
            self.view.response_message(self.SECTION_CARD_NAME,
                             f"Could not save paths: {error}", "danger")
            return

        if PATHS_OUTPUT_DIR in changes:
            # The converted text moves, so what is embedded no longer matches
            # what is on disk. Saved anyway - blocking the edit would be worse.
            self.view.response_message(
                self.SECTION_CARD_NAME,
                "Saved paths. The existing collection no longer matches - run a reset.",
                "warning",
            )
        else:
            self.view.response_message(self.SECTION_CARD_NAME, "Saved paths.", "success")

    def revert(self, _=None):
        if not self.paths.changes():
            return
        self.paths.load()
        self.view.response_message(self.SECTION_CARD_NAME, "Reverted paths.", "neutral")


class DriveSectionCard(SectionCard):
    """The Drive folder the mirror is pulled from."""

    SECTION_CARD_NAME = "Drive settings"

    def __init__(self, view: SettingsView):
        p = palette()
        drive = view.drive
        super().__init__(
            "Google Drive",
            "Used by services/file_downloader_service/.",
            trailing=Pill("Read-only scope", "success", ft.Icons.CLOUD_DONE_ROUNDED),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            RowLabel("Folder id"),
                            TextInput(drive.folder_id, is_mono=True,
                                      on_change=self.edit_folder_id),
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy folder id",
                                       lambda e: copy_to_clipboard(
                                           e.control, drive.folder_id, "the folder id")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Service account key"),
                            TextInput(drive.service_account_file, is_mono=True,
                                      on_change=self.edit_service_account_file),
                            # The path to the key, never its contents - this
                            # copies where the credentials live, not them.
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy service account key",
                                       lambda e: copy_to_clipboard(
                                           e.control, drive.service_account_file,
                                           "the service account key path")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Scope"),
                            ft.Container(
                                content=Mono(drive.scope, size=12, color=p.text),
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, size=15,
                                        color=p.text_faint),
                                ft.Text(
                                    "Only file metadata is read - ids, names and modifiedTime. "
                                    "File content still comes from the local mirror.",
                                    size=11,
                                    color=p.text_muted,
                                    expand=True,
                                ),
                            ],
                            spacing=Space.SM,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        padding=Space.MD,
                        bgcolor=p.surface_alt,
                        border_radius=Radius.SM,
                    ),
                    *view.response_message_for(self.SECTION_CARD_NAME),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            GhostButton("Revert", icon=ft.Icons.UNDO_ROUNDED, is_dense=True,
                                        on_click=self.revert),
                            PrimaryButton("Save", icon=ft.Icons.CHECK_ROUNDED, is_dense=True,
                                          on_click=self.save),
                        ],
                        spacing=Space.SM,
                    ),
                ],
                spacing=Space.MD,
            ),
        )
        self.view = view
        self.drive = drive

    def edit_folder_id(self, e):
        self.drive.folder_id = e.control.value

    def edit_service_account_file(self, e):
        self.drive.service_account_file = e.control.value

    def save(self, _=None):
        changes = self.drive.changes()
        if not changes:
            self.view.response_message(self.SECTION_CARD_NAME, "No changes to Drive settings.", "neutral")
            return

        error = self.drive.validate()
        if error:
            self.view.response_message(self.SECTION_CARD_NAME, error, "danger")
            return

        try:
            settingService.update_all(changes)
        except Exception as error:
            self.view.response_message(self.SECTION_CARD_NAME,
                             f"Could not save Drive settings: {error}", "danger")
            return

        # Nothing here orphans the collection - a new folder id only changes
        # what the next sync pulls down.
        self.view.response_message(self.SECTION_CARD_NAME, "Saved Drive settings.", "success")

    def revert(self, _=None):
        if not self.drive.changes():
            return
        self.drive.load()
        self.view.response_message(self.SECTION_CARD_NAME, "Reverted Drive settings.", "neutral")


class EmbeddingSectionCard(SectionCard):
    """The model documents are indexed with, and where the vectors live."""

    SECTION_CARD_NAME = "embedding settings"

    def __init__(self, view: SettingsView):
        p = palette()
        embedding = view.embedding
        super().__init__(
            "Embedding",
            "Used by services/file_embedder_service/ and the search.",
            content=ft.Column(
                [
                    ft.Row(
                        [
                            RowLabel("Model"),
                            ft.Container(
                                content=Mono(embedding.model, size=12, color=p.text),
                                expand=True,
                            ),
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy model name",
                                       lambda e: copy_to_clipboard(
                                           e.control, embedding.model, "the model name")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Collection"),
                            ft.Container(
                                content=Mono(embedding.collection, size=12, color=p.text),
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Store"),
                            ft.Container(
                                content=Mono(embedding.store, size=12, color=p.text),
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Results per query"),
                            TextInput(embedding.results_per_query, is_mono=True,
                                      on_change=self.edit_results_per_query),
                            IconButton(ft.Icons.CONTENT_COPY_ROUNDED, "Copy results per query",
                                       lambda e: copy_to_clipboard(
                                           e.control, embedding.results_per_query,
                                           "the results per query")),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            RowLabel("Telemetry"),
                            ft.Container(
                                content=ft.Text("Disabled", size=13, color=p.text),
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    Divider(bottom=Space.SM),
                    *view.response_message_for(self.SECTION_CARD_NAME),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            GhostButton("Revert", icon=ft.Icons.UNDO_ROUNDED, is_dense=True,
                                        on_click=self.revert),
                            PrimaryButton("Save", icon=ft.Icons.CHECK_ROUNDED, is_dense=True,
                                          on_click=self.save),
                        ],
                        spacing=Space.SM,
                    ),
                ],
                spacing=Space.MD,
            ),
        )
        self.view = view
        self.embedding = embedding

    def edit_results_per_query(self, e):
        self.embedding.results_per_query = e.control.value

    def save(self, _=None):
        changes = self.embedding.changes()
        if not changes:
            self.view.response_message(self.SECTION_CARD_NAME, "No changes to embedding settings.",
                             "neutral")
            return

        error = self.embedding.validate()
        if error:
            self.view.response_message(self.SECTION_CARD_NAME, error, "danger")
            return

        try:
            settingService.update_all(changes)
        except Exception as error:
            self.view.response_message(self.SECTION_CARD_NAME,
                             f"Could not save embedding settings: {error}", "danger")
            return

        # The one row that can change here is how many results a search returns,
        # which nothing on disk depends on - no reset warning.
        self.view.response_message(self.SECTION_CARD_NAME, "Saved embedding settings.", "success")

    def revert(self, _=None):
        if not self.embedding.changes():
            return
        self.embedding.load()
        self.view.response_message(self.SECTION_CARD_NAME, "Reverted embedding settings.", "neutral")
