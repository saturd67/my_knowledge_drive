"""The base class every downloadable file type extends."""

import io
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)


class DownloadableFile(ABC):
    """A single Drive file, and how it should be written to disk.

    One subclass per file type, each in its own file in this directory, all
    built by DownloadableFileFactory.
    """

    def __init__(self, drive_service, file_id, name, mime_type, target_dir):
        self.drive_service = drive_service
        self.file_id = file_id
        self.name = name
        self.mime_type = mime_type
        self.target_dir = Path(target_dir)

    @abstractmethod
    def download(self):
        """Writes the file. Returns False when nothing was written."""

    def get_output_file_path(self):
        """Where this file lands - same name and extension unless overridden."""
        return self.target_dir / self.name
        

    def _get_media(self):
        """Raw bytes of an uploaded file."""
        request = self.drive_service.files().get_media(fileId=self.file_id, supportsAllDrives=True)
        return self._read_stream(request)

    def _export(self, mime_type):
        """Bytes of a Google-native file exported to `mime_type`."""
        request = self.drive_service.files().export_media(fileId=self.file_id, mimeType=mime_type)
        return self._read_stream(request)

    @staticmethod
    def _read_stream(request):
        buffer = io.BytesIO()
        media_io_base_download = MediaIoBaseDownload(buffer, request)
        is_done = False
        while not is_done:
            status, is_done = media_io_base_download.next_chunk()
            if status:
                logger.debug(f"  {int(status.progress() * 100)}%")
        return buffer.getvalue()

    def _write(self, destination_path, content):
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with open(destination_path, "wb") as file:
            file.write(content)
