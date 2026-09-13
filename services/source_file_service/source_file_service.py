r"""The file as it was downloaded, before conversion read its images out.

`LibraryResetService._convert` copies the downloaded tree to the converted
folder and only ever rewrites the copy, so the base64 images survive in the
sources and only converted_files loses them. That leaves every embedded
document with an original sitting at the same relative path under the input
folder:

    resources\files\Python\Async.md            <- still has its images
    resources\converted_files\Python\Async.md   <- images read out as text

The document id *is* that relative path - `FileEmbedderService` sets it to the
file's path under the converted folder - so the original is found by joining,
with nothing to look up.

The original is what the reading pane shows. The embedded text stays the
fallback, because a document can outlive its source: a reset clears the input
folder before it refills it, and a sync only re-downloads the files it was
told to.
"""

import logging
from pathlib import Path

from constant.settings import PATHS_INPUT_DIR
from services.SettingService import settingService

logger = logging.getLogger(__name__)


class SourceFileService:

    def __init__(self, input_dir=None):
        #: None means "read the setting on every call". The Settings screen
        #: can move the input folder while the search screen is open, and a
        #: path cached in the constructor would go on reading the old one.
        self._input_dir = input_dir

    @property
    def input_dir(self):
        return Path(self._input_dir or settingService.get_path(PATHS_INPUT_DIR))

    def find_original_file_text(self, document_id):
        """The original file's text, or None when there is no reading it.

        None rather than an exception for every way this can miss - no source
        on disk, a folder that has moved, bytes that are not UTF-8. The screen
        falls back to the embedded text, which is always there, so a missing
        original is a worse reading pane rather than a broken one.
        """
        source_file_path = self.find_path(document_id)
        if source_file_path is None:
            return None

        try:
            return source_file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            logger.warning(f"Could not read source file {source_file_path} - {error}")
            return None

    def find_path(self, document_id):
        """Where `document_id`'s original lives, or None if it is not a file."""
        input_dir = self.input_dir.resolve()

        try:
            source_file_path = (input_dir / document_id).resolve()
        except OSError as error:
            logger.warning(f"Could not resolve source path for {document_id} - {error}")
            return None

        # The id comes out of the collection rather than from a person, but it
        # is still a relative path being joined onto a folder - one check
        # keeps a `..` in a stale id from reading outside the mirror.
        if not source_file_path.is_relative_to(input_dir):
            logger.warning(f"Source path for {document_id} escapes {input_dir}")
            return None

        return source_file_path if source_file_path.is_file() else None
