"""Downloads a Google Drive folder to disk.

Self-contained - it reads no setting itself. The folder, the output directory
and the credentials are arguments, so the caller decides where a run reads and
writes: LibraryResetService passes what the setting table holds, and the tests
pass a temporary folder.

This module only walks the folder tree. What happens to a file once it is found
belongs to the DownloadableFile subclass that DownloadableFileFactory picks, one
per file, each in its own file:

    folder                          -> walks into it, keeping the folder structure
    Google Doc (native)             -> GoogleDocFile   - exported from Drive as markdown (.md)
    .docx                           -> DocxFile        - converted to markdown (.md)
    .pdf / .md / .txt               -> KeepAsIsFile    - downloaded byte for byte
    anything else                   -> UnsupportedFile - skipped
"""

import logging
import re
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from services.file_downloader_service.downloadable_file_factory import DownloadableFileFactory

logger = logging.getLogger(__name__)


class FileDownloaderService:
    """Walks a Drive folder and hands every file it finds to the factory."""

    FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

    PAGE_SIZE = 1000
    INVALID_NAME_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

    def __init__(self, folder_id, output_dir, service_account_file, scope):
        self.folder_id = folder_id
        self.output_dir = Path(output_dir)
        #: What this run downloaded, as document id -> Drive file id. The
        #: download is the one moment both are known, and nothing downstream
        #: ever sees the Drive id again - the collection keeps the converted
        #: path as its id. Gathered here and left for the caller to persist,
        #: so this service still reads and writes nothing but Drive and disk.
        self.drive_ids_by_document_id = {}
        credentials = Credentials.from_service_account_file(service_account_file, scopes=[scope])
        self.drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    def start_download(self):
        """Downloads the whole tree. Returns (downloaded, skipped, failed) counts."""
        logger.info(f"Downloading folder {self.folder_id} into {self.output_dir}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        downloaded_file_count, skipped_file_count, failed_file_count = self._download_files_in_folder(
            self.folder_id, self.output_dir
        )
        logger.info(
            f"Done. Downloaded: {downloaded_file_count}, "
            f"skipped: {skipped_file_count}, failed: {failed_file_count}"
        )
        return downloaded_file_count, skipped_file_count, failed_file_count

    def list_files(self):
        """Walks the tree and reports what is there, downloading nothing.

        Each entry is (file_id, name, mime_type, modified_time, folder_path),
        where `folder_path` is the folders above it relative to the output
        folder - the same place `start_download` would have written it, which
        is what makes the listing comparable to what is already on disk.

        The names are sanitised here, so a caller building a path from one
        gets the path the downloader would have used, not Drive's raw name."""
        logger.info(f"Listing folder {self.folder_id}")
        drive_files = self._list_files_in_folder(self.folder_id, Path())
        logger.info(f"Found {len(drive_files)} file(s) on Drive")
        return drive_files

    def download_file(self, file_id, name, mime_type, folder_path):
        """Downloads one file into `folder_path` under the output folder.

        The single-file counterpart of `start_download`, for an update that
        was asked for a handful of files rather than the whole tree. Same
        factory, so a file fetched here lands exactly where a full run would
        have put it. Returns False when the type is one we skip."""
        target_dir = self.output_dir / folder_path
        target_dir.mkdir(parents=True, exist_ok=True)
        downloadable_file = DownloadableFileFactory.get_file(
            self.drive_service, file_id, self._sanitize_name(name), mime_type, target_dir
        )
        is_downloaded = downloadable_file.download()
        if is_downloaded:
            self._record_drive_id(downloadable_file, file_id)
        return is_downloaded

    def _list_files_in_folder(self, folder_id, folder_path):
        drive_files = []
        for file in self._list_folder_children(folder_id):
            name = self._sanitize_name(file["name"])
            if file["mimeType"] == FileDownloaderService.FOLDER_MIME_TYPE:
                drive_files += self._list_files_in_folder(file["id"], folder_path / name)
                continue
            drive_files.append(
                (file["id"], name, file["mimeType"], file.get("modifiedTime"), folder_path)
            )
        return drive_files

    def _download_files_in_folder(self, folder_id, target_dir):
        downloaded_file_count = 0
        skipped_file_count = 0
        failed_file_count = 0

        for file in self._list_folder_children(folder_id):
            name = self._sanitize_name(file["name"])
            mime_type = file["mimeType"]

            if mime_type == FileDownloaderService.FOLDER_MIME_TYPE:
                sub_dir = target_dir / name
                logger.info(f"Entering folder: {sub_dir}")
                sub_dir.mkdir(parents=True, exist_ok=True)
                sub_downloaded_file_count, sub_skipped_file_count, sub_failed_file_count = (
                    self._download_files_in_folder(file["id"], sub_dir)
                )
                downloaded_file_count += sub_downloaded_file_count
                skipped_file_count += sub_skipped_file_count
                failed_file_count += sub_failed_file_count
                continue

            downloadable_file = DownloadableFileFactory.get_file(
                self.drive_service, file["id"], name, mime_type, target_dir
            )
            try:
                is_downloaded = downloadable_file.download()
            except (HttpError, OSError, ValueError) as error:
                logger.error(f"Failed: {downloadable_file.get_output_file_path()} - {error}")
                failed_file_count += 1
                continue

            if is_downloaded:
                self._record_drive_id(downloadable_file, file["id"])
                downloaded_file_count += 1
            else:
                skipped_file_count += 1

        return downloaded_file_count, skipped_file_count, failed_file_count

    def _record_drive_id(self, downloadable_file, file_id):
        """Note which Drive file produced the path that was just written.

        Keyed by the path relative to this run's output folder, because that
        is what becomes the Chroma document id: the reset copies this tree to
        the converted folder before embedding it, and `FileEmbedderService`
        keys on the path relative to *that*. The copy preserves the structure,
        so the same relative path names the same document in both.
        """
        output_file_path = downloadable_file.get_output_file_path()
        try:
            document_id = str(output_file_path.relative_to(self.output_dir))
        except ValueError:
            # A file written outside the run's own folder is not a document
            # the collection will ever hold, so there is nothing to map.
            logger.warning(f"Not mapping {output_file_path} - outside {self.output_dir}")
            return
        self.drive_ids_by_document_id[document_id] = file_id

    def _list_folder_children(self, folder_id):
        """Every non-trashed child of the folder, one page at a time."""
        files = []
        page_token = None
        while True:
            response = self.drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                pageSize=FileDownloaderService.PAGE_SIZE,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            files += response.get("files", [])
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    @staticmethod
    def _sanitize_name(name):
        """Drive names may hold characters Windows will not accept in a path."""
        return FileDownloaderService.INVALID_NAME_CHARACTERS.sub("_", name).strip().rstrip(".") or "untitled"
