r"""What changed upstream, and applying only the part of it you picked.

The other half of Library Sync. Where LibraryResetService rebuilds everything
unconditionally, this compares and then touches as little as it can:

    start_scan()   reads three live sources and returns a FileChange per file
    start_update() acts on the ones you ticked

Nothing is persisted between the two. A scan is re-derived every time from
Drive, the converted folder and the collection, so an update can never act on
a verdict that has gone stale while the screen sat open - see
plans/file-table.md, which states the same rule for the cache it designs.

The three sources, and what each one settles:

    the Drive listing      what exists upstream, and when it last changed
    resources\converted_files  what has been converted but perhaps not embedded
    the Chroma collection  what is actually searchable, and as of when

A file's identity through all of it is its path under the converted folder,
extension and all - which is exactly the Chroma document id
`FileEmbedderService` writes. The mapping from a Drive file to that path is
not re-implemented here: `DownloadableFileFactory` already owns it, so the
same object that would download the file is asked where it would land.
"""

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from constant.settings import (
    DRIVE_FOLDER_ID,
    DRIVE_SCOPE,
    DRIVE_SERVICE_ACCOUNT_FILE,
    EMBEDDING_COLLECTION,
    EMBEDDING_MODEL,
    PATHS_CHROMA_STORE,
    PATHS_INPUT_DIR,
    PATHS_OUTPUT_DIR,
)
from model.FileChange import FileChange
from services.DriveFileService import driveFileService
from services.SettingService import settingService
from services.file_downloader_service.downloadable_file.unsupported_file import UnsupportedFile
from services.file_downloader_service.downloadable_file_factory import DownloadableFileFactory
from services.file_downloader_service.file_downloader_service import FileDownloaderService
from services.file_embedder_service.file_embedder_service import FileEmbedderService
from services.file_convert_service.file_convert_service import FileConvertService
from services.library_service.library_service import LibraryService

logger = logging.getLogger(__name__)


class SyncPlannerCancelled(Exception):
    """Raised when the caller's `is_cancelled` says to stop between steps."""


class SyncPlannerService:
    """Scans for what changed, and applies the changes that were picked."""

    #: The three things a scan looks at, in the order it looks at them.
    SCAN_STEPS = (
        "Walk the local mirror",
        "Fetch Drive listing",
        "Diff against the collection",
    )

    #: The three things an update does.
    UPDATE_STEPS = (
        "Download the picked files",
        "Convert the picked files",
        "Update the collection",
    )

    #: Ticked for you when a scan returns. Removals are deliberately not in
    #: here: fetching a file again costs a minute, deleting one costs the
    #: document, so a deletion is something you ask for rather than untick.
    PRE_SELECTED_STATUSES = ("added", "updated", "stale_local")

    def __init__(self, input_dir=None, output_dir=None, chroma_store_dir=None,
                 collection_name=None, embedding_model=None):
        self.input_dir = Path(input_dir or settingService.get_path(PATHS_INPUT_DIR))
        self.output_dir = Path(output_dir or settingService.get_path(PATHS_OUTPUT_DIR))
        self.chroma_store_dir = chroma_store_dir or settingService.get_path(PATHS_CHROMA_STORE)
        self.collection_name = (
            collection_name or settingService.find_active_by_key(EMBEDDING_COLLECTION)
        )
        self.embedding_model = (
            embedding_model or settingService.find_active_by_key(EMBEDDING_MODEL)
        )

    # --- the scan ------------------------------------------------------------

    def start_scan(self, on_step=None, is_cancelled=None):
        """Reads the three sources and returns a FileChange for every file.

        Writes nothing, anywhere. `on_step(step_number, step_name)` is called
        as each step starts and `is_cancelled()` is checked between them.
        """
        self._start_step(SyncPlannerService.SCAN_STEPS, 1, on_step, is_cancelled)
        converted_times_by_id = self._walk_converted_files()

        self._start_step(SyncPlannerService.SCAN_STEPS, 2, on_step, is_cancelled)
        drive_files = self._list_drive_files()

        self._start_step(SyncPlannerService.SCAN_STEPS, 3, on_step, is_cancelled)
        # Read-only, and deliberately through LibraryService: it builds no
        # embedding function, so a scan never loads the SentenceTransformer
        # model that FileEmbedderService pulls in on construction.
        library_service = LibraryService(self.chroma_store_dir, self.collection_name)
        documents = library_service.find_all_documents()

        file_changes = self._diff(drive_files, converted_times_by_id, documents)
        logger.info(f"Scan found {len(file_changes)} file(s): {self.count_by_status(file_changes)}")
        return file_changes

    def _walk_converted_files(self):
        """Document id -> when its converted file was last written.

        Empty when the folder is not there, which is a first run rather than
        an error - every Drive file then reads as `added`, correctly."""
        converted_times_by_id = {}
        if not self.output_dir.is_dir():
            logger.info(f"No converted folder yet: {self.output_dir}")
            return converted_times_by_id

        for file_path in self.output_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in FileEmbedderService.TEXT_EXTENSIONS:
                continue
            document_id = str(file_path.relative_to(self.output_dir))
            converted_times_by_id[document_id] = datetime.fromtimestamp(
                file_path.stat().st_mtime, timezone.utc
            )

        logger.info(f"Walked {len(converted_times_by_id)} converted file(s) in {self.output_dir}")
        return converted_times_by_id

    def _list_drive_files(self):
        return self._file_downloader_service().list_files()

    def _diff(self, drive_files, converted_times_by_id, documents):
        """One FileChange per Drive file, plus one per orphaned document."""
        documents_by_id = {document.document_id: document for document in documents}
        file_changes = []
        seen_document_ids = set()

        for file_id, name, mime_type, modified_time, folder_path in drive_files:
            output_path = self._output_path_for(file_id, name, mime_type, folder_path)
            document_id = str(output_path)

            if not self._is_embeddable(file_id, name, mime_type, folder_path):
                # Blocked: downloaded or not, it can never reach the
                # collection, so no tick would do anything for it.
                file_changes.append(self._file_change(
                    document_id, file_id, name, mime_type, modified_time, folder_path,
                    status="unsupported",
                ))
                continue

            seen_document_ids.add(document_id)
            document = documents_by_id.get(document_id)
            file_changes.append(self._file_change(
                document_id, file_id, name, mime_type, modified_time, folder_path,
                status=self._status_for(document, modified_time,
                                        converted_times_by_id.get(document_id)),
                embedded_modified_time=document.modified_time if document else None,
            ))

        file_changes += self._removed_changes(documents_by_id, seen_document_ids)
        file_changes.sort(key=lambda file_change: file_change.label.lower())
        return file_changes

    def _status_for(self, document, drive_modified_time, converted_time):
        """The verdict for one file that is on Drive and can be embedded."""
        if document is None:
            return "added"

        # Drive's clock against ours: the collection stores the converted
        # file's mtime, which is when we last wrote it, so a Drive time after
        # it means the document changed upstream since we embedded it.
        if self._is_after(drive_modified_time, document.modified_time):
            return "updated"

        # Converted since we embedded, but the embed never happened - a
        # cancelled run, usually. Nothing to fetch; it just needs embedding.
        if self._is_after(converted_time, document.modified_time):
            return "stale_local"

        return "unchanged"

    def _removed_changes(self, documents_by_id, seen_document_ids):
        """Documents the collection holds that no Drive file accounts for."""
        removed_changes = []
        for document_id, document in documents_by_id.items():
            if document_id in seen_document_ids:
                continue
            output_path = Path(document_id)
            removed_changes.append(FileChange(
                document_id=document_id,
                label=str(output_path.with_suffix("")),
                embedded_modified_time=document.modified_time,
                status="removed",
                folder_path=str(output_path.parent) if output_path.parent != Path() else "",
            ))
        return removed_changes

    # --- the update ----------------------------------------------------------

    def start_update(self, file_changes, on_step=None, is_cancelled=None):
        """Applies the ticked changes and returns what each step did.

        Only rows that are both ticked and actionable are touched; everything
        else in the list is ignored, so the caller can hand back the whole
        scan result.
        """
        picked_changes = [
            file_change for file_change in file_changes
            if file_change.is_selected and file_change.is_actionable
        ]
        fetch_changes = [f for f in picked_changes if f.is_fetch]
        removal_changes = [f for f in picked_changes if f.is_removal]
        results = {"walked": len(file_changes), "selected": len(picked_changes)}

        self._start_step(SyncPlannerService.UPDATE_STEPS, 1, on_step, is_cancelled)
        downloaded_file_count, download_failed_file_count = self._download(fetch_changes)
        results["downloaded"] = downloaded_file_count
        results["download_failed"] = download_failed_file_count

        self._start_step(SyncPlannerService.UPDATE_STEPS, 2, on_step, is_cancelled)
        results["converted"] = self._convert(fetch_changes)

        self._start_step(SyncPlannerService.UPDATE_STEPS, 3, on_step, is_cancelled)
        results.update(self._apply_to_collection(picked_changes, removal_changes))

        logger.info(f"Update completed - {results}")
        return results

    def _download(self, fetch_changes):
        """Fetches each picked file again, one call per file."""
        if not fetch_changes:
            logger.info("Nothing to download")
            return 0, 0

        file_downloader_service = self._file_downloader_service()
        downloaded_file_count = 0
        failed_file_count = 0
        for file_change in fetch_changes:
            try:
                is_downloaded = file_downloader_service.download_file(
                    file_change.drive_id,
                    file_change.source_name,
                    file_change.source_mime_type,
                    file_change.folder_path,
                )
            except Exception as error:
                # One unreachable file must not lose the other forty.
                logger.error(f"Failed to download {file_change.label} - {error}")
                failed_file_count += 1
                continue
            downloaded_file_count += is_downloaded and 1 or 0

        # Only what this update fetched, and no `deactivate_missing`: an update
        # touches the files it was told to and leaves the rest of the library
        # alone, so the mappings it did not write are still true.
        driveFileService.save_all(file_downloader_service.drive_ids_by_document_id)

        return downloaded_file_count, failed_file_count

    def _convert(self, fetch_changes):
        """Copies each fetched file across and fits the copy to the model's window.

        Returns how many files were copied and converted.

        The copy is what keeps the run repeatable, the same as a reset: the
        downloaded source keeps its images and full text, and only the copy
        under the converted folder is cut down."""
        if not fetch_changes:
            logger.info("Nothing to convert")
            return 0

        file_convert_service = FileConvertService()
        converted_file_count = 0

        for file_change in fetch_changes:
            source_path = self.input_dir / file_change.document_id
            if not source_path.is_file():
                logger.warning(f"Downloaded file is missing, skipping: {source_path}")
                continue

            output_path = self.output_dir / file_change.document_id
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Copying {source_path} to {output_path}")
            shutil.copy2(source_path, output_path)
            converted_file_count += 1

            # Every copied file rather than only the markdown - a .txt is
            # embedded too, so it has to fit the window as well.
            file_convert_service.add_to_file(output_path, self.output_dir)

        return converted_file_count

    def _apply_to_collection(self, picked_changes, removal_changes):
        """Embeds what was fetched or was already stale, deletes the rest."""
        embed_changes = [f for f in picked_changes if not f.is_removal]
        if not embed_changes and not removal_changes:
            logger.info("Nothing to write to the collection")
            return {"embedded": 0, "embed_skipped": 0, "embed_failed": 0, "removed": 0}

        file_embedder_service = FileEmbedderService(
            self.output_dir,
            self.chroma_store_dir,
            self.collection_name,
            self.embedding_model,
        )

        embedded_file_count, embed_skipped_file_count, embed_failed_file_count = (
            file_embedder_service.embed_files(
                self.output_dir / file_change.document_id for file_change in embed_changes
            )
        )

        removed_file_count = file_embedder_service.delete_documents(
            file_change.document_id for file_change in removal_changes
        )
        for file_change in removal_changes:
            self._delete_local_files(file_change)

        return {
            "embedded": embedded_file_count,
            "embed_skipped": embed_skipped_file_count,
            "embed_failed": embed_failed_file_count,
            "removed": removed_file_count,
        }

    def _delete_local_files(self, file_change):
        """Removes what is left of a deleted document on disk.

        Both folders, because leaving the converted file behind would make the
        next scan report it as `stale_local` and offer to embed it straight
        back in. The source is matched by stem: it was `Notes.docx` before the
        converter made it `Notes.md`."""
        output_path = self.output_dir / file_change.document_id
        output_path.unlink(missing_ok=True)

        source_dir = self.input_dir / file_change.folder_path
        if not source_dir.is_dir():
            return
        for source_path in source_dir.glob(f"{output_path.stem}.*"):
            if source_path.is_file():
                logger.info(f"Deleting: {source_path}")
                source_path.unlink(missing_ok=True)

    # --- the shape of a change -----------------------------------------------

    def _file_change(self, document_id, file_id, name, mime_type, modified_time,
                     folder_path, status, embedded_modified_time=None):
        return FileChange(
            document_id=document_id,
            label=str(Path(document_id).with_suffix("")),
            drive_id=file_id,
            drive_modified_time=modified_time,
            embedded_modified_time=embedded_modified_time,
            status=status,
            source_name=name,
            source_mime_type=mime_type,
            folder_path=str(folder_path) if str(folder_path) != "." else "",
            is_selected=status in SyncPlannerService.PRE_SELECTED_STATUSES,
        )

    def _output_path_for(self, file_id, name, mime_type, folder_path):
        """Where this Drive file would land, relative to either folder.

        Asked of the factory rather than worked out here, so the extension a
        Google Doc or a .docx ends up with has one definition."""
        downloadable_file = DownloadableFileFactory.get_file(
            None, file_id, name, mime_type, Path(folder_path)
        )
        return downloadable_file.get_output_file_path()

    def _is_embeddable(self, file_id, name, mime_type, folder_path):
        """Whether this file can reach the collection at all.

        Two ways it cannot: the downloader skips the type outright, or it
        downloads it into something the embedder does not read - a .pdf is
        kept byte for byte and then never embedded."""
        downloadable_file = DownloadableFileFactory.get_file(
            None, file_id, name, mime_type, Path(folder_path)
        )
        if isinstance(downloadable_file, UnsupportedFile):
            return False
        suffix = downloadable_file.get_output_file_path().suffix.lower()
        return suffix in FileEmbedderService.TEXT_EXTENSIONS

    def _file_downloader_service(self):
        return FileDownloaderService(
            settingService.find_active_by_key(DRIVE_FOLDER_ID),
            self.input_dir,
            settingService.get_path(DRIVE_SERVICE_ACCOUNT_FILE),
            settingService.find_active_by_key(DRIVE_SCOPE),
        )

    @staticmethod
    def count_by_status(file_changes):
        """How many files landed in each status - for a log line or a pill."""
        counts = {}
        for file_change in file_changes:
            counts[file_change.status] = counts.get(file_change.status, 0) + 1
        return counts

    @staticmethod
    def _is_after(moment, other_moment):
        """Whether `moment` is later than `other_moment`, either as a string.

        False whenever either will not parse, which is the safe answer: an
        unreadable timestamp should leave a file alone rather than have it
        re-fetched on every scan for ever."""
        moment = SyncPlannerService._to_datetime(moment)
        other_moment = SyncPlannerService._to_datetime(other_moment)
        if moment is None or other_moment is None:
            return False
        return moment > other_moment

    @staticmethod
    def _to_datetime(value):
        """An ISO-8601 timestamp as an aware datetime, or None.

        Drive writes `...Z` and the embedder writes `...+00:00`; both mean
        UTC and both have to compare against each other. A value with no zone
        at all is read as UTC rather than dropped."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            logger.debug(f"Unreadable timestamp: {value!r}")
            return None
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)

    @staticmethod
    def _start_step(steps, step_number, on_step, is_cancelled):
        if is_cancelled is not None and is_cancelled():
            raise SyncPlannerCancelled()
        step_name = steps[step_number - 1]
        logger.info(f"Step {step_number} of {len(steps)}: {step_name}")
        if on_step is not None:
            on_step(step_number, step_name)
