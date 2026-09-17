"""Rewrites each converted file as the chunks it is embedded from.

The walk, the reading and the writing live here. How a file's text becomes
chunks belongs to its type - a MarkdownFile for a .md, a PlainTextFile for a
.txt - picked from the file's extension by LibraryFileFactory, the same factory
the downloader uses. See services/library_file/library_file.py for the shape of
a chunk.

The chunks are written into the converted file one after another, with
`FileEmbedderService.CHUNK_SEPARATOR` on a line between each pair, and the
embedder cuts the file back apart there.

Written into the converted copy, never the download: the sources under the
input folder stay exactly as Drive gave them, which is what the reading pane
shows and what makes a re-run repeatable. Both conversion paths copy the
source over the top before calling this, so a second run rebuilds from a full
file rather than an already-split one.

Only the extensions the embedder reads are rewritten - a .pdf sitting in the
folder is never embedded, so changing it would have no reader.
"""

import logging
from pathlib import Path

from constant.settings import EMBEDDING_MODEL
from services.SettingService import settingService
from services.file_embedder_service.file_embedder_service import FileEmbedderService
from services.file_convert_service.token_counter import TokenCounter
from services.library_file.library_file import LibraryFile
from services.library_file.library_file_factory import LibraryFileFactory

logger = logging.getLogger(__name__)


class FileConvertService:

    #: Between two chunks in the converted file. The separator line has a
    #: blank line after it, so each chunk still opens on its own path.
    CHUNK_JOINER = f"\n{FileEmbedderService.CHUNK_SEPARATOR}\n\n"

    def __init__(self, token_counter=None):
        self._token_counter = token_counter

    @property
    def token_counter(self):
        """Built on first use, so reading the settings table waits until a file needs it."""
        if self._token_counter is None:
            self._token_counter = TokenCounter(settingService.find_active_by_key(EMBEDDING_MODEL))
        return self._token_counter

    def add_to_folder(self, converted_dir):
        """Rewrites every embeddable file under `converted_dir`.

        Returns how many files were rewritten.
        """
        converted_dir = Path(converted_dir)
        logger.info(f"Splitting files into chunks of {LibraryFile.MAX_TOKENS} tokens in {converted_dir}")
        split_file_count = 0
        for file_path in sorted(converted_dir.rglob("*")):
            if file_path.is_file() and self.add_to_file(file_path, converted_dir):
                split_file_count += 1
        logger.info(f"Done. Split {split_file_count} file(s) into chunks")
        return split_file_count

    def add_to_file(self, converted_file_path, converted_dir):
        """Rewrites one converted file as the chunks it is embedded from.

        False when there was nothing to do, rather than an exception for a file
        that cannot be read: one bad file must not lose the rest of a run, and a
        file left as it was is still embedded, just as one chunk of raw text.
        """
        converted_file_path = Path(converted_file_path)
        if converted_file_path.suffix.lower() not in FileEmbedderService.TEXT_EXTENSIONS:
            return False

        try:
            document_id = str(converted_file_path.relative_to(Path(converted_dir)))
        except ValueError:
            logger.warning(f"Not rewriting {converted_file_path} - outside {converted_dir}")
            return False

        try:
            text = converted_file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            logger.warning(f"Could not read {converted_file_path} - {error}")
            return False

        # Belt and braces: the callers copy the source over the top first, so
        # this should never fire - but splitting a split file would be silent.
        if text.startswith(document_id):
            logger.debug(f"Already split: {converted_file_path}")
            return False

        library_file = LibraryFileFactory.get_local_file(converted_file_path)
        chunks = library_file.split(document_id, text, self.token_counter)
        try:
            converted_file_path.write_text(FileConvertService.CHUNK_JOINER.join(chunks), encoding="utf-8")
        except OSError as error:
            logger.warning(f"Could not write {converted_file_path} - {error}")
            return False

        logger.debug(f"Split {converted_file_path} as {type(library_file).__name__} into {len(chunks)} chunk(s)")
        return True
