"""Picks the LibraryFile subclass that handles a given file.

Adding a file type is a new LibraryFile subclass in its own file in
library_file/, plus one branch here.
"""

from pathlib import Path

from services.library_file.docx_file import DocxFile
from services.library_file.google_doc_file import GoogleDocFile
from services.library_file.markdown_file import MarkdownFile
from services.library_file.pdf_file import PdfFile
from services.library_file.plain_text_file import PlainTextFile
from services.library_file.unsupported_file import UnsupportedFile


class LibraryFileFactory:

    #: The types kept byte for byte, which can only be told apart by extension
    #: or mime type. Extension first: Drive often reports an uploaded .md as
    #: text/plain, and the extension is what the converter and the embedder go
    #: by afterwards.
    KEEP_AS_IS_FILE_CLASSES = (MarkdownFile, PlainTextFile, PdfFile)

    @staticmethod
    def get_file(drive_service, file_id, name, mime_type, target_dir):
        extension = Path(name).suffix.lower()

        if mime_type == GoogleDocFile.MIME_TYPE:
            return GoogleDocFile(drive_service, file_id, name, mime_type, target_dir)
        if mime_type == DocxFile.MIME_TYPE or extension == DocxFile.EXTENSION:
            return DocxFile(drive_service, file_id, name, mime_type, target_dir)

        for library_file_class in LibraryFileFactory.KEEP_AS_IS_FILE_CLASSES:
            if extension in library_file_class.EXTENSIONS:
                return library_file_class(drive_service, file_id, name, mime_type, target_dir)
        for library_file_class in LibraryFileFactory.KEEP_AS_IS_FILE_CLASSES:
            if mime_type in library_file_class.MIME_TYPES:
                return library_file_class(drive_service, file_id, name, mime_type, target_dir)

        return UnsupportedFile(drive_service, file_id, name, mime_type, target_dir)

    @staticmethod
    def get_local_file(file_path):
        """The type of a file already on disk, from its name alone.

        For splitting, which reads the converted copy: there is no Drive
        service, file id or mime type to hand over, and none is needed. The
        extension is enough - a Google Doc or a .docx is a .md by then, and
        splits as one. Never call `download` on what this returns.
        """
        file_path = Path(file_path)
        return LibraryFileFactory.get_file(None, None, file_path.name, None, file_path.parent)
