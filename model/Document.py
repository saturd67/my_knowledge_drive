"""One document in the Chroma collection.

Deliberately not a BaseModel: this is not a row in the SQLite database, so it
has no `id`, `created_date`, `updated_date` or `is_active`. Its identity is the
Chroma document id, which `FileEmbedderService` sets to the file's path under
the converted folder - extension and all.
"""

from datetime import datetime
from pathlib import PurePath

#: Converted-file extension -> the kind FileIcon draws it as. Everything in
#: the collection is text by the time it is embedded, so this says what the
#: converter wrote, not what the source was: an OCR'd image and a hand-written
#: note both arrive as `.txt` and are indistinguishable here.
KINDS_BY_SUFFIX = {
    ".md": "doc",
    ".markdown": "doc",
    ".txt": "text",
}


class Document:

    def __init__(self, document_id, label, modified_time=None):
        #: Path under the converted folder, with the extension. Unique.
        self.document_id = document_id
        #: The same path without the extension - what is shown on screen.
        self.label = label
        #: ISO-8601 UTC, from the source file's mtime at embedding time.
        self.modified_time = modified_time

    @staticmethod
    def from_chroma(document_id, metadata):
        """Build one from a row of `collection.get()`.

        `label` falls back to the id: a document embedded by an older run may
        not carry the metadata, and a listing that hides it would be worse
        than one that shows the raw path.
        """
        metadata = metadata or {}
        return Document(
            document_id=document_id,
            label=metadata.get("label") or document_id,
            modified_time=metadata.get("modifiedTime"),
        )

    @property
    def folder(self):
        """The folders above it, or "" for a document at the top level."""
        return self.label.rpartition("\\")[0]

    @property
    def name(self):
        """Just the file, without the folders leading to it."""
        return self.label.rpartition("\\")[2]

    @property
    def kind(self):
        return KINDS_BY_SUFFIX.get(PurePath(self.document_id).suffix.lower(), "text")

    @property
    def modified(self):
        """`modified_time` to the minute, for a row that has to stay narrow.

        The raw value back if it will not parse, and "" if there is none - an
        older run may have embedded without it.
        """
        if not self.modified_time:
            return ""
        try:
            return datetime.fromisoformat(self.modified_time).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return self.modified_time
