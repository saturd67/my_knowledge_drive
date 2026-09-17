import logging

from services.library_file.library_file import LibraryFile

logger = logging.getLogger(__name__)


class UnsupportedFile(LibraryFile):
    """Every other type - images, executables, archives. Nothing is written, and nothing is split."""

    def download(self):
        logger.info(f"Skipping unsupported file: {self.get_output_file_path()} ({self.mime_type})")
        return False

    def _parse(self, text):
        """Nothing - a file that is never downloaded has no text to read."""
        return []
