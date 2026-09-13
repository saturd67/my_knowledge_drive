import logging

from services.file_downloader_service.downloadable_file.downloadable_file import DownloadableFile

logger = logging.getLogger(__name__)


class KeepAsIsFile(DownloadableFile):
    """A pdf, markdown or text file - downloaded byte for byte, name unchanged.

    Drive is inconsistent about the mime type it reports for uploaded text
    files (.md often arrives as text/plain or application/octet-stream), so the
    factory matches on the extension as well.
    """

    MIME_TYPES = ("application/pdf", "text/markdown", "text/x-markdown", "text/plain")
    EXTENSIONS = (".pdf", ".md", ".markdown", ".txt")

    def download(self):
        destination_path = self.get_output_file_path()
        logger.info(f"Downloading: {destination_path}")
        self._write(destination_path, self._get_media())
        return True
