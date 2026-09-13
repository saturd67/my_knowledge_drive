import logging

from services.file_downloader_service.downloadable_file.downloadable_file import DownloadableFile

logger = logging.getLogger(__name__)


class UnsupportedFile(DownloadableFile):
    """Every other type - images, executables, archives. Nothing is written."""

    def download(self):
        logger.info(f"Skipping unsupported file: {self.get_output_file_path()} ({self.mime_type})")
        return False
