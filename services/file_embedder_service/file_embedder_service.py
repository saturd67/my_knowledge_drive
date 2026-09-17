r"""Embeds the converted files into the chroma store.

Third step of the chain, after the downloader and the image converter, and
self-contained in the same way - it reads no setting itself. The folder, the
store, the collection and the model are arguments, so the caller decides where
a run reads and writes.

One file becomes one document per chunk `FileConvertService` cut it into, and
every chunk carries the file it belongs to in its metadata:

    id           Java\Spring Security.md::3     <- the chunk, unique
    documentId   Java\Spring Security.md        <- the file, shared by its chunks
    chunkIndex   3                              <- where it sits, from 0
    chunkCount   12                             <- how many the file has

So a search that lands on one chunk can fetch the whole file back with
`where={"documentId": ...}`, put it in order by `chunkIndex`, and tell from
`chunkCount` whether every part of it came back. `documentId` is the file's
path relative to the source folder - the same document id the rest of the app
knows the file by. The path without the extension is stored as `label`, which
is what the Library and the search results show.

Chunks are upserted, so running it again after a re-download refreshes what
changed instead of adding it twice - and a file that has shrunk loses the
chunks it no longer has, see `_delete_stale_chunks`.
"""

import logging
import re
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

    #: The line `FileConvertService` writes between two chunks of a file. An
    #: HTML comment, because the converter takes every tag out of the text -
    #: so it can never turn up inside a chunk - and a Markdown viewer opening
    #: the converted file draws nothing for it.
    CHUNK_SEPARATOR = "<!-- chunk -->"
    CHUNK_SEPARATOR_PATTERN = re.compile(rf"^{re.escape(CHUNK_SEPARATOR)}[ \t]*$", re.MULTILINE)

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
        """Removes documents from the collection - every chunk of each - by document id.

        Chroma ignores ids and filters that match nothing, so this is safe to
        call with a document another run has already deleted. Returns how many
        document ids were handed over."""
        document_ids = list(document_ids)
        if not document_ids:
            return 0

        logger.info(f"Deleting {len(document_ids)} document(s) from '{self.collection_name}'")
        for batch_start in range(0, len(document_ids), FileEmbedderService.BATCH_SIZE):
            batch_document_ids = document_ids[batch_start:batch_start + FileEmbedderService.BATCH_SIZE]
            self.collection.delete(where={"documentId": {"$in": batch_document_ids}})
            # Embedded before files were split, a document was one row keyed
            # by its bare path, with no `documentId` for the filter to find.
            self.collection.delete(ids=batch_document_ids)
        logger.info(f"Collection holds: {self.collection.count()}")
        return len(document_ids)

    def _upsert_in_batches(self, files):
        """Writes every chunk of these files, then deletes the chunks they no longer have.

        Returns how many files were written."""
        chunks = [chunk for file in files for chunk in file["chunks"]]
        embedded_chunk_count = 0
        for batch_start in range(0, len(chunks), FileEmbedderService.BATCH_SIZE):
            batch = chunks[batch_start:batch_start + FileEmbedderService.BATCH_SIZE]
            self.collection.upsert(
                ids=[chunk["id"] for chunk in batch],
                documents=[chunk["content"] for chunk in batch],
                metadatas=[chunk["metadata"] for chunk in batch],
            )
            embedded_chunk_count += len(batch)
            logger.info(f"Embedded {embedded_chunk_count}/{len(chunks)} chunks")

        self._delete_stale_chunks(files)
        return len(files)

    def _delete_stale_chunks(self, files):
        """Deletes what an earlier embedding of these files left that this one did not write.

        An upsert overwrites the chunks a file still has, but a file that got
        shorter has fewer of them, and its old tail would go on being found -
        and would come back as part of the file. A document embedded before
        files were split is one row keyed by its bare path, and goes the same
        way.

        After the upsert rather than before, so a file is never missing from
        the collection while it is being rewritten."""
        written_chunk_ids = {chunk["id"] for file in files for chunk in file["chunks"]}
        document_ids = [file["id"] for file in files]

        stale_chunk_ids = []
        for batch_start in range(0, len(document_ids), FileEmbedderService.BATCH_SIZE):
            batch_document_ids = document_ids[batch_start:batch_start + FileEmbedderService.BATCH_SIZE]
            chunk_result = self.collection.get(where={"documentId": {"$in": batch_document_ids}}, include=[])
            stale_chunk_ids += [chunk_id for chunk_id in chunk_result["ids"] if chunk_id not in written_chunk_ids]
            stale_chunk_ids += self.collection.get(ids=batch_document_ids, include=[])["ids"]

        if not stale_chunk_ids:
            return
        logger.info(f"Deleting {len(stale_chunk_ids)} chunk(s) these files no longer have")
        for batch_start in range(0, len(stale_chunk_ids), FileEmbedderService.BATCH_SIZE):
            self.collection.delete(ids=stale_chunk_ids[batch_start:batch_start + FileEmbedderService.BATCH_SIZE])

    def _read_file(self, file_path):
        """One file, read and cut into the chunks to upsert.

        Returns (file, outcome), where outcome is `ok`, `skipped` or `failed`
        and `file` is None for the last two. One definition of what counts as
        embeddable, shared by the folder walk and `embed_files`.

        A file with no separator in it - one the converter could not rewrite -
        is a single chunk of whatever it holds, and the model reads the opening
        of it, the way every file used to be embedded."""
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

        document_id = self._get_document_id(file_path)
        label = self._get_document_label(file_path)
        modified_time = self._get_modified_time(file_path)
        chunk_texts = [
            chunk_text.strip("\n")
            for chunk_text in FileEmbedderService.CHUNK_SEPARATOR_PATTERN.split(content)
            if chunk_text.strip()
        ]

        return {
            "id": document_id,
            "chunks": [
                {
                    "id": self._get_chunk_id(document_id, chunk_index),
                    "content": chunk_text,
                    "metadata": {
                        "label": label,
                        "modifiedTime": modified_time,
                        "documentId": document_id,
                        "chunkIndex": chunk_index,
                        "chunkCount": len(chunk_texts),
                    },
                }
                for chunk_index, chunk_text in enumerate(chunk_texts)
            ],
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

    @staticmethod
    def _get_chunk_id(document_id, chunk_index):
        """The document id, `::`, and where the chunk sits in the file.

        `::` rather than `#`, which a folder name can hold - this library has a
        `C#` folder. A Windows path cannot hold a `:` past its drive, so a
        chunk id can never be mistaken for a document id, nor overwrite a
        document embedded whole before files were split."""
        return f"{document_id}::{chunk_index}"

    def _get_document_label(self, file_path):
        """What the document is called on screen - the id without its
        extension."""
        return str(file_path.relative_to(self.source_dir).with_suffix(""))

    @staticmethod
    def _get_modified_time(file_path):
        return datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc).isoformat()


