import io
import logging

from services.file_downloader_service.downloadable_file.downloadable_file import DownloadableFile
from pathlib import Path

logger = logging.getLogger(__name__)


class DocxFile(DownloadableFile):
    """An uploaded .docx. Drive cannot export it, so it is converted here.

    Drive only exports Google-native files; converting a .docx through the API
    would mean copy-converting it into a Google Doc first, which is a write the
    read-only service account cannot make. mammoth keeps the scope read-only.
    """

    MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    EXTENSION = ".docx"

    def get_output_file_path(self):
        return self.target_dir / (Path(self.name).stem + ".md")

    def download(self):
        destination_path = self.get_output_file_path()
        logger.info(f"Converting docx to markdown: {destination_path}")
        self._write(destination_path, self._to_markdown(self._get_media()))
        return True

    @staticmethod
    def _to_markdown(docx_bytes):
        # Imported here so the other file types still work on a machine that
        # does not have mammoth installed.
        import mammoth

        result = mammoth.convert_to_markdown(io.BytesIO(docx_bytes))
        for message in result.messages:
            logger.debug(f"  mammoth: {message}")
        return result.value.encode("utf-8")
