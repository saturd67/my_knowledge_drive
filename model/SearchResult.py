"""One hit from a search: a document, how close it scored, and its text.

A SearchResult *is* a Document - same id, label, folder, name and kind - with
the query-specific parts added, so the screen reads `result.name` exactly as
the Library screen reads `document.name`.

A search ranks chunks, but a hit is a whole file: `SearchService` keeps the
closest chunk of each file, which is where `distance` and `chunk_text` come
from, and puts the file's chunks back together into `file_text`.
"""

from model.Document import Document

#: How much of the text the preview shows before trailing off.
PREVIEW_LENGTH = 220


class SearchResult(Document):

    def __init__(self, document_id, label, modified_time=None, distance=0.0, chunk_text="", file_text=""):
        super().__init__(document_id, label, modified_time)
        #: Cosine distance from the query to the closest chunk of the file.
        #: Smaller is closer.
        self.distance = distance
        #: That closest chunk - the passage that matched, without the path and
        #: headings it was embedded under.
        self.chunk_text = chunk_text
        #: The whole document as it was embedded, put back together from every
        #: one of its chunks. What the pane falls back to when the original is
        #: gone.
        self.file_text = file_text
        #: The original file, before conversion took its images out. Filled in
        #: by the screen from `SourceFileService`, and left None when there is
        #: no source on disk any more.
        self.original_file_text = None
        #: The Drive file this document came from. Filled in by the screen from
        #: `DriveFileService`, and left None for a document embedded before the
        #: drive_file table existed - the collection itself never knew it.
        self.drive_id = None

    @staticmethod
    def from_chroma(chunk_id, metadata, distance=0.0, chunk_text=""):
        """Build one from a row of `collection.query()` - one chunk of the file.

        The document id falls back to the row's own id, the way
        `Document.from_chroma` does, for a document embedded whole.
        """
        metadata = metadata or {}
        document_id = metadata.get("documentId") or chunk_id
        return SearchResult(
            document_id=document_id,
            label=metadata.get("label") or document_id,
            modified_time=metadata.get("modifiedTime"),
            distance=distance,
            chunk_text=chunk_text,
        )

    @property
    def score(self):
        """Rough 0..1 relevance, for display only.

        Cosine distance is not a probability and this is not calibrated - it
        exists so the hits can be compared against each other in one glance.
        """
        return max(0.0, min(1.0, 1.0 - self.distance))

    @property
    def is_original(self):
        """Whether `display_text` is the source file or the embedded copy.

        The pane says which of the two it is showing, because they are not the
        same file: one has the pictures, the other has the text that was read
        out of them.
        """
        return self.original_file_text is not None

    @property
    def display_text(self):
        """What the reading pane draws - the original wherever there is one."""
        return self.original_file_text if self.is_original else self.file_text

    @property
    def preview(self):
        """The passage that matched, on one line.

        The chunk that scored closest, so this is the part of the file the
        query actually landed on rather than however the file happens to open.
        """
        chunk_text = " ".join(self.chunk_text.split())
        if len(chunk_text) <= PREVIEW_LENGTH:
            return chunk_text
        return chunk_text[:PREVIEW_LENGTH].rsplit(" ", 1)[0] + " ..."
