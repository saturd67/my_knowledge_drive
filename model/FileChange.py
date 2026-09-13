"""What a scan found for one file, and what an update would do about it.

A FileChange *is* a Document - same id, label, folder, name and kind - with the
scan's verdict added, so the review tree reads `file_change.name` exactly as
the Library screen reads `document.name`.

It is never stored. Every field is re-derived from the three live sources on
each scan - the Drive listing, the converted folder and the collection - so a
change can never be acted on after the state it describes has moved. That is
the rule `plans/file-table.md` states as "a row is never allowed to decide that
a file needs updating"; nothing here is a row.
"""

from model.Document import Document

#: Statuses an update can actually do something about.
ACTIONABLE_STATUSES = ("added", "updated", "removed", "stale_local")


class FileChange(Document):

    def __init__(self, document_id, label, drive_id=None, drive_modified_time=None,
                 embedded_modified_time=None, status="unchanged", source_name=None,
                 source_mime_type=None, folder_path="", is_selected=False):
        # `modified_time` is Drive's, so the inherited `modified` property
        # reads as "when it last changed upstream" - which is the column the
        # review tree wants against a file it is offering to fetch.
        super().__init__(document_id, label, drive_modified_time)
        #: The Drive file id, or None for a document Drive no longer has.
        self.drive_id = drive_id
        #: Drive's `modifiedTime`, verbatim.
        self.drive_modified_time = drive_modified_time
        #: The `modifiedTime` the collection holds, verbatim. None when the
        #: document is not embedded.
        self.embedded_modified_time = embedded_modified_time
        #: added | updated | removed | stale_local | unsupported | unchanged
        self.status = status
        #: The Drive file's name, needed to download it again.
        self.source_name = source_name
        self.source_mime_type = source_mime_type
        #: Folders above it, relative to the input folder, as they are on disk.
        self.folder_path = folder_path
        #: Ticked in the review tree. Only actionable rows are ever ticked.
        self.is_selected = is_selected

    @property
    def is_actionable(self):
        """Whether an update has anything to do for this file."""
        return self.status in ACTIONABLE_STATUSES

    @property
    def is_removal(self):
        return self.status == "removed"

    @property
    def is_fetch(self):
        """Whether applying it means going back to Drive for the file."""
        return self.status in ("added", "updated")
