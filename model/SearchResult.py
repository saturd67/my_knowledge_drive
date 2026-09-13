"""One hit from a search: a document, how close it scored, and its text.

A SearchResult *is* a Document - same id, label, folder, name and kind - with
the query-specific parts added, so the screen reads `result.name` exactly as
the Library screen reads `document.name`.
"""

from model.Document import Document

#: How much of the text the preview shows before trailing off.
PREVIEW_LENGTH = 220


class SearchResult(Document):

    def __init__(self, document_id, label, modified_time=None, distance=0.0, file_text=""):
        super().__init__(document_id, label, modified_time)
        #: Cosine distance from the query. Smaller is closer.
        self.distance = distance
        #: The document as it was embedded - the images already read out as
        #: text. What the pane falls back to when the original is gone.
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
    def from_chroma(document_id, metadata, distance=0.0, file_text=""):
        metadata = metadata or {}
        return SearchResult(
            document_id=document_id,
            label=metadata.get("label") or document_id,
            modified_time=metadata.get("modifiedTime"),
            distance=distance,
            file_text=file_text,
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
        """The opening of the document, on one line.

        Deliberately the opening rather than "the passage that matched":
        `FileEmbedderService` embeds one vector per whole file, so no
        particular passage is what scored, and pointing at one would be
        inventing a reason. Chunked embeddings would change that.
        """
        file_text = " ".join(self.file_text.split())
        if len(file_text) <= PREVIEW_LENGTH:
            return file_text
        return file_text[:PREVIEW_LENGTH].rsplit(" ", 1)[0] + " ..."
