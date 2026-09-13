r"""The full rebuild, in the order the Reset screen lists it.

One place that knows the whole pipeline, so the screen stays presentation
only: it calls `start_reset()`, and gets told which step is running through a
callback it passes in.

The three workers it drives are the standalone services - the downloader, the
file converter and the embedder. They take their folders as arguments rather
than reading the setting table themselves, so this is where the settings are
read and handed to them.

    resources\files            <- step 1 clears it, step 2 downloads Drive into it
    resources\converted_files  <- step 3 clears it, step 4 fills it
    the chroma store           <- step 5 empties, step 6 refills

Every one of the three is emptied before it is refilled, so a reset is a
rebuild from Drive rather than a merge over what an earlier run left behind -
a file removed upstream disappears here too.

That also means the local mirror is gone the moment step 1 runs: a reset that
fails at step 2 leaves no sources to fall back on, and has to be run again
once Drive is reachable. Conversion still never rewrites the sources - only
the copy in converted_files is cut down to fit the model.
"""

import logging
import shutil
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
from services.DriveFileService import driveFileService
from services.SettingService import settingService
from services.file_downloader_service.file_downloader_service import FileDownloaderService
from services.file_embedder_service.file_embedder_service import FileEmbedderService
from services.file_convert_service.file_convert_service import FileConvertService

logger = logging.getLogger(__name__)


class LibraryResetCancelled(Exception):
    """Raised when the caller's `is_cancelled` says to stop between steps."""


class LibraryResetService:
    """Downloads, converts, and re-embeds the whole library from scratch.

    The steps are the same five the Reset screen shows, in the same order.
    """

    STEPS = (
        "Clear downloaded files",
        "Download from Drive",
        "Clear converted files",
        "Convert every source file",
        "Drop the collection",
        "Re-embed everything",
    )

    def __init__(self, input_dir=None, output_dir=None, chroma_store_dir=None, collection_name=None):
        self.input_dir = Path(input_dir or settingService.get_path(PATHS_INPUT_DIR))
        self.output_dir = Path(output_dir or settingService.get_path(PATHS_OUTPUT_DIR))
        self.chroma_store_dir = chroma_store_dir or settingService.get_path(PATHS_CHROMA_STORE)
        self.collection_name = collection_name or settingService.find_active_by_key(EMBEDDING_COLLECTION)

    def start_reset(self, on_step=None, is_cancelled=None):
        """Runs the six steps in order and returns what each one did.

        `on_step(step_number, step_name)` is called as each step starts, and
        `is_cancelled()` is checked between steps - a run that is cancelled
        raises LibraryResetCancelled, leaving what has already been written
        where it is."""
        results = {}

        self._start_step(1, on_step, is_cancelled)
        self._clear_downloaded_files()

        self._start_step(2, on_step, is_cancelled)
        downloaded_file_count, skipped_file_count, failed_file_count = self._download()
        results["downloaded"] = downloaded_file_count
        results["download_skipped"] = skipped_file_count
        results["download_failed"] = failed_file_count

        self._start_step(3, on_step, is_cancelled)
        self._clear_converted_files()

        self._start_step(4, on_step, is_cancelled)
        results["converted"] = self._convert()

        file_embedder_service = FileEmbedderService(
            self.output_dir,
            self.chroma_store_dir,
            self.collection_name,
            settingService.find_active_by_key(EMBEDDING_MODEL),
        )

        self._start_step(5, on_step, is_cancelled)
        file_embedder_service.reset_collection()

        self._start_step(6, on_step, is_cancelled)
        embedded_file_count, embed_skipped_file_count, embed_failed_file_count = (
            file_embedder_service.start_embedding()
        )
        results["embedded"] = embedded_file_count
        results["embed_skipped"] = embed_skipped_file_count
        results["embed_failed"] = embed_failed_file_count

        logger.info(f"Reset completed - {results}")
        return results

    def _download(self):
        file_downloader_service = FileDownloaderService(
            settingService.find_active_by_key(DRIVE_FOLDER_ID),
            self.input_dir,
            settingService.get_path(DRIVE_SERVICE_ACCOUNT_FILE),
            settingService.find_active_by_key(DRIVE_SCOPE),
        )
        results = file_downloader_service.start_download()

        # Which Drive file each document came from, so the reading pane can
        # link to it. A reset is a rebuild from Drive, so anything this run did
        # not download is no longer in the library either - its mapping is
        # retired rather than left pointing at a document that has gone.
        drive_ids_by_document_id = file_downloader_service.drive_ids_by_document_id
        driveFileService.save_all(drive_ids_by_document_id)
        driveFileService.deactivate_missing(list(drive_ids_by_document_id))

        return results

    def _clear_downloaded_files(self):
        """Empties the source folder, so what an earlier run left is gone.

        Without this, a file deleted or renamed in Drive stays on disk, gets
        converted and embedded again, and the collection keeps a document that
        no longer exists upstream. The download that follows is a fresh copy,
        not a merge over the old one.
        """
        logger.info(f"Clearing: {self.input_dir}")
        shutil.rmtree(self.input_dir, ignore_errors=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)

    def _clear_converted_files(self):
        logger.info(f"Clearing: {self.output_dir}")
        shutil.rmtree(self.output_dir, ignore_errors=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _convert(self):
        """Copies the downloaded tree, then fits each copy to the model's window.

        Returns how many files were converted.

        The copy is what makes the run repeatable - the sources keep their
        base64 images and full text, and only converted_files is cut down.
        Images are not read out as text any more: FileConvertService drops image
        text, so reading it was minutes of work nothing used."""
        logger.info(f"Copying {self.input_dir} to {self.output_dir}")
        shutil.copytree(self.input_dir, self.output_dir, dirs_exist_ok=True)
        return FileConvertService().add_to_folder(self.output_dir)

    @staticmethod
    def _start_step(step_number, on_step, is_cancelled):
        if is_cancelled is not None and is_cancelled():
            raise LibraryResetCancelled()
        step_name = LibraryResetService.STEPS[step_number - 1]
        logger.info(f"Step {step_number} of {len(LibraryResetService.STEPS)}: {step_name}")
        if on_step is not None:
            on_step(step_number, step_name)


def main():
    """Runs the whole rebuild from the terminal, without the UI.

    Everything comes from the setting table, the same as the Reset screen, so
    this is the screen's run with the progress printed instead of drawn.

    Run it from the project root, so the `constant` and `services` imports
    resolve: `python -m services.library_reset_service.library_reset_service`
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    library_reset_service = LibraryResetService()
    print(f"Input folder    : {library_reset_service.input_dir}")
    print(f"Output folder   : {library_reset_service.output_dir}")
    print(f"Chroma store    : {library_reset_service.chroma_store_dir}")
    print(f"Collection      : {library_reset_service.collection_name}")
    print("This rewrites both folders and empties the collection.")
    if input("Type 'reset' to start: ").strip().lower() != "reset":
        print("Nothing done.")
        return

    def on_step(step_number, step_name):
        print(f"\n[{step_number}/{len(LibraryResetService.STEPS)}] {step_name}")

    try:
        results = library_reset_service.start_reset(on_step=on_step)
    except LibraryResetCancelled:
        print("\nCancelled - what was already written is left where it is.")
        return
    except KeyboardInterrupt:
        print("\nStopped - what was already written is left where it is.")
        return

    print("\nDone.")
    for name, count in results.items():
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
