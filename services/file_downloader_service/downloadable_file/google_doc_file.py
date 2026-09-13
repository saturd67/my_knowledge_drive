import logging

from services.file_downloader_service.downloadable_file.downloadable_file import DownloadableFile
from pathlib import Path

logger = logging.getLogger(__name__)


class GoogleDocFile(DownloadableFile):
    """A Google-native document. Drive exports it as markdown for us."""

    MIME_TYPE = "application/vnd.google-apps.document"
    MARKDOWN_MIME_TYPE = "text/markdown"

    def get_output_file_path(self):
        return self.target_dir / (Path(self.name).stem + ".md")

    def download(self):
        destination_path = self.get_output_file_path()
        logger.info(f"Exporting Google Doc as markdown: {destination_path}")
        self._write(destination_path, self._export(GoogleDocFile.MARKDOWN_MIME_TYPE))
        return True
