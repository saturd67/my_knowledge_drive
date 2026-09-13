"""Embeds the converted files into the chroma store.

Third step of the chain, after the downloader and the image converter, and
self-contained in the same way - it reads no setting itself. The folder, the
store, the collection and the model are arguments, so the caller decides where
a run reads and writes.

One file becomes one document, keyed by its path relative to the source folder.
The same path without the extension is stored as the `label` metadata, which is
what the Library and the search results show. Documents are upserted, so running
it again after a re-download refreshes what changed instead of adding it twice.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)


class FileEmbedderService:
    """Embeds a folder of text files into a chroma collection."""

    TEXT_EXTENSIONS = (".md", ".markdown", ".txt")
    BATCH_SIZE = 100

    def __init__(self, source_dir, chroma_store_dir, collection_name, embedding_model):
        self.source_dir = Path(source_dir)
        self.collection_name = collection_name
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_store_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.sentence_transformer = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.sentence_transformer,
        )

    def start_embedding(self):
        """Embeds every text file under the source folder.

        Returns (embedded_file_count, skipped_file_count, failed_file_count)."""
        logger.info(f"Embedding {self.source_dir} into '{self.collection_name}'")
        files, skipped_file_count, failed_file_count = self._read_files_in_folder(self.source_dir)

        files, duplicate_file_count = self._drop_duplicate_ids(files)
        skipped_file_count += duplicate_file_count

        embedded_file_count = self._upsert_in_batches(files)

        logger.info(
            f"Done. Embedded: {embedded_file_count}, skipped: {skipped_file_count}, "
            f"failed: {failed_file_count}, collection holds: {self.collection.count()}"
        )
        return embedded_file_count, skipped_file_count, failed_file_count

    def embed_files(self, file_paths):
        """Upserts just these files, for an update that touched a few of them.

        Same read, same ids and same metadata as a full run - only the set of
        files differs, so a document embedded here is indistinguishable from
        one a reset wrote. Paths that are missing, empty or not text are
        skipped rather than failing the batch.

        Returns (embedded_file_count, skipped_file_count, failed_file_count).
        """
        files = []
        skipped_file_count = 0
        failed_file_count = 0

        for file_path in file_paths:
            file, outcome = self._read_file(Path(file_path))
            if outcome == "skipped":
                skipped_file_count += 1
            elif outcome == "failed":
                failed_file_count += 1
            else:
                files.append(file)

        files, duplicate_file_count = self._drop_duplicate_ids(files)
        skipped_file_count += duplicate_file_count

        embedded_file_count = self._upsert_in_batches(files)
        logger.info(
            f"Embedded {embedded_file_count} file(s), skipped: {skipped_file_count}, "
            f"failed: {failed_file_count}, collection holds: {self.collection.count()}"
        )
        return embedded_file_count, skipped_file_count, failed_file_count

    def delete_documents(self, document_ids):
        """Removes documents from the collection by id.

        Chroma ignores ids it does not hold, so this is safe to call with a
        document another run has already deleted. Returns how many ids were
        handed over."""
        document_ids = list(document_ids)
        if not document_ids:
            return 0

        logger.info(f"Deleting {len(document_ids)} document(s) from '{self.collection_name}'")
        self.collection.delete(ids=document_ids)
        logger.info(f"Collection holds: {self.collection.count()}")
        return len(document_ids)

    def _upsert_in_batches(self, files):
        embedded_file_count = 0
        for batch_start in range(0, len(files), FileEmbedderService.BATCH_SIZE):
            batch = files[batch_start:batch_start + FileEmbedderService.BATCH_SIZE]
            self.collection.upsert(
                ids=[file["id"] for file in batch],
                documents=[file["content"] for file in batch],
                metadatas=[file["metadata"] for file in batch],
            )
            embedded_file_count += len(batch)
            logger.info(f"Embedded {embedded_file_count}/{len(files)}")
        return embedded_file_count

    def _read_file(self, file_path):
        """One file, read and ready to upsert.

        Returns (file, outcome), where outcome is `ok`, `skipped` or `failed`
        and `file` is None for the last two. One definition of what counts as
        embeddable, shared by the folder walk and `embed_files`."""
        if not file_path.is_file():
            logger.info(f"Not on disk, skipping: {file_path}")
            return None, "skipped"

        if file_path.suffix.lower() not in FileEmbedderService.TEXT_EXTENSIONS:
            logger.debug(f"Not a text file, skipping: {file_path}")
            return None, "skipped"

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            logger.error(f"Failed: {file_path} - {error}")
            return None, "failed"

        if not content.strip():
            logger.info(f"Empty, skipping: {file_path}")
            return None, "skipped"

        return {
            "id": self._get_document_id(file_path),
            "content": content,
            "metadata": {
                "label": self._get_document_label(file_path),
                "modifiedTime": self._get_modified_time(file_path),
            },
        }, "ok"

    def _read_files_in_folder(self, folder_path):
        """Every embeddable file under the folder, read and ready to upsert."""
        files = []
        skipped_file_count = 0
        failed_file_count = 0

        for file_path in sorted(folder_path.iterdir()):
            if file_path.is_dir():
                logger.info(f"Entering folder: {file_path}")
                sub_files, sub_skipped_file_count, sub_failed_file_count = self._read_files_in_folder(file_path)
                files += sub_files
                skipped_file_count += sub_skipped_file_count
                failed_file_count += sub_failed_file_count
                continue

            file, outcome = self._read_file(file_path)
            if outcome == "skipped":
                skipped_file_count += 1
            elif outcome == "failed":
                failed_file_count += 1
            else:
                files.append(file)

        return files, skipped_file_count, failed_file_count

    def reset_collection(self):
        """Empties the collection - the store's other collections are untouched."""
        logger.info(f"Clearing collection '{self.collection_name}'")
        self.chroma_client.delete_collection(name=self.collection_name)
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.sentence_transformer,
        )

    @staticmethod
    def _drop_duplicate_ids(files):
        """Keeps the first of any repeated id, and says which file it dropped.

        Two documents sharing an id make chroma reject the whole upsert, which
        loses the entire run over one clash. Paths are unique, so this should
        never fire - it is here so that if it ever does, the log names the file
        instead of the run dying on `found duplicates of: <id>`."""
        files_by_id = {}
        duplicate_file_count = 0
        for file in files:
            if file["id"] in files_by_id:
                logger.warning(f"Duplicate id, skipping: {file['id']}")
                duplicate_file_count += 1
                continue
            files_by_id[file["id"]] = file
        return list(files_by_id.values()), duplicate_file_count

    def _get_document_id(self, file_path):
        """The path relative to the source folder, extension and all.

        The extension has to stay: one folder can hold two embeddable files
        with the same name - a Google Doc arrives as `Notes.md` while the
        image converter writes `Notes.txt` beside `Notes.jpg` - and dropping
        it made both documents the same id, which chroma rejects as a
        duplicate in the middle of an upsert."""
        return str(file_path.relative_to(self.source_dir))

    def _get_document_label(self, file_path):
        """What the document is called on screen - the id without its
        extension."""
        return str(file_path.relative_to(self.source_dir).with_suffix(""))

    @staticmethod
    def _get_modified_time(file_path):
        return datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc).isoformat()


