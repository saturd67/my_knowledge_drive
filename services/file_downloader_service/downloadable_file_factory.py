"""Picks the DownloadableFile subclass that handles a given Drive file.

Adding a file type is a new DownloadableFile subclass in its own file in
downloadable_file/, plus one branch here.
"""

from pathlib import Path

from services.file_downloader_service.downloadable_file.docx_file import DocxFile
from services.file_downloader_service.downloadable_file.google_doc_file import GoogleDocFile
from services.file_downloader_service.downloadable_file.keep_as_is_file import KeepAsIsFile
from services.file_downloader_service.downloadable_file.unsupported_file import UnsupportedFile


class DownloadableFileFactory:

    @staticmethod
    def get_file(drive_service, file_id, name, mime_type, target_dir):
        extension = Path(name).suffix.lower()

        if mime_type == GoogleDocFile.MIME_TYPE:
            downloadable_file_class = GoogleDocFile
        elif mime_type == DocxFile.MIME_TYPE or extension == DocxFile.EXTENSION:
            downloadable_file_class = DocxFile
        elif mime_type in KeepAsIsFile.MIME_TYPES or extension in KeepAsIsFile.EXTENSIONS:
            downloadable_file_class = KeepAsIsFile
        else:
            downloadable_file_class = UnsupportedFile

        return downloadable_file_class(drive_service, file_id, name, mime_type, target_dir)
