from services.library_file.library_file import LibraryFile


class PdfFile(LibraryFile):
    """A .pdf - downloaded byte for byte, name unchanged, and never embedded."""

    MIME_TYPES = ("application/pdf",)
    EXTENSIONS = (".pdf",)

    def _parse(self, text):
        """Nothing - no text is read out of a pdf, and the embedder never reads one."""
        return []
