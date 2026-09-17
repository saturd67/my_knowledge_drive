import logging

from services.library_file.markdown_file import MarkdownFile
from pathlib import Path

logger = logging.getLogger(__name__)


class GoogleDocFile(MarkdownFile):
    """A Google-native document. Drive exports it as markdown for us, and it splits as markdown."""

    MIME_TYPE = "application/vnd.google-apps.document"
    MARKDOWN_MIME_TYPE = "text/markdown"

    def get_output_file_path(self):
        return self.target_dir / (Path(self.name).stem + ".md")

    def download(self):
        destination_path = self.get_output_file_path()
        logger.info(f"Exporting Google Doc as markdown: {destination_path}")
        self._write(destination_path, self._export(GoogleDocFile.MARKDOWN_MIME_TYPE))
        return True
