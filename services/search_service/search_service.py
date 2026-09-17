"""Semantic search over the Chroma collection.

Unlike `LibraryService`, this one needs the embedding function: the query has
to be embedded with the same model the documents were, or the distances mean
nothing. That model is loaded lazily and cached, so the first search of a
process takes seconds and the rest are quick - which is why the screen runs a
search on a worker thread rather than on the event loop.

The model is the only thing cached, and it is cached on its own name, so
changing it on the Settings screen loads the new one rather than quietly
searching with the old. The collection itself is fetched fresh every time -
see `collection()` for why caching it was a bug.
"""

import logging

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from constant.settings import (
    EMBEDDING_COLLECTION,
    EMBEDDING_MODEL,
    EMBEDDING_RESULTS_PER_QUERY,
    PATHS_CHROMA_STORE,
)
from model.SearchResult import SearchResult
from services.SettingService import settingService
from services.file_convert_service.file_convert_service import FileConvertService

logger = logging.getLogger(__name__)


class SearchService:

    #: How many chunks are ranked for each file a search wants, to begin with.
    #: Several chunks of one file are often the closest few, and they make one
    #: hit between them.
    CHUNKS_PER_RESULT = 4

    def __init__(self):
        #: The loaded sentence-transformer and the model name it was built
        #: from. The only thing worth keeping between calls: loading it is the
        #: seconds, and everything else here is a metadata lookup.
        self._embedding_model = None
        self._embedding_function = None

    def search(self, query):
        """The closest documents to `query`, closest first - one hit per file.

        Each hit carries the chunk that matched and the whole file rebuilt
        from its chunks. An empty list for a blank query, and for a collection
        that is not there - nothing has been embedded, which is not an error.
        """
        query = query.strip()
        if not query:
            return []

        collection = self.collection()
        if collection is None:
            return []

        wanted = int(settingService.find_active_by_key(EMBEDDING_RESULTS_PER_QUERY))
        # Asking for more than the collection holds is an error in chroma, and
        # a fresh library can easily hold fewer than the configured five.
        chunk_count = collection.count()
        if not chunk_count:
            return []

        search_results = self._find_closest_files(collection, query, wanted, chunk_count)

        file_texts_by_document_id = self._find_file_texts(
            collection, [search_result.document_id for search_result in search_results]
        )
        for search_result in search_results:
            # Absent only for a document embedded whole, before files were
            # split - and then the chunk that matched is all of it.
            search_result.file_text = file_texts_by_document_id.get(
                search_result.document_id, search_result.chunk_text
            )
            search_result.chunk_text = FileConvertService.remove_header(
                search_result.document_id, search_result.chunk_text
            )
        return search_results

    def _find_closest_files(self, collection, query, wanted, chunk_count):
        """The `wanted` closest files, closest first, each scored by its closest chunk.

        Chroma ranks chunks and knows nothing of files, and one long note can
        fill the top of the ranking on its own. So more chunks are asked for
        than files are wanted, and the ask doubles until enough different files
        turn up or every chunk has been ranked.
        """
        n_results = min(wanted * SearchService.CHUNKS_PER_RESULT, chunk_count)
        while True:
            logger.info(f"Searching '{query}' for the closest {n_results} of {chunk_count} chunks")
            result = collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

            search_results_by_document_id = {}
            for chunk_id, metadata, distance, chunk_text in zip(
                result["ids"][0],
                result["metadatas"][0],
                result["distances"][0],
                result["documents"][0],
            ):
                search_result = SearchResult.from_chroma(chunk_id, metadata, distance, chunk_text)
                # Closest first, so the first chunk seen of a file is its best.
                search_results_by_document_id.setdefault(search_result.document_id, search_result)

            search_results = list(search_results_by_document_id.values())[:wanted]
            if len(search_results) >= wanted or n_results >= chunk_count:
                return search_results
            n_results = min(n_results * 2, chunk_count)

    @staticmethod
    def _find_file_texts(collection, document_ids):
        """document id -> the whole file, put back together from its chunks.

        This is what the `documentId` on every chunk is for: whichever chunk a
        search landed on, the filter brings back all of them, and `chunkIndex`
        puts them in order. Each chunk's header - the path and the headings it
        was embedded under - is taken off, so the file reads once, not once per
        chunk. A file with fewer chunks than its `chunkCount` says was cut off
        part way through being written; what there is is still returned.
        """
        if not document_ids:
            return {}

        result = collection.get(
            where={"documentId": {"$in": document_ids}},
            include=["documents", "metadatas"],
        )
        chunks_by_document_id = {}
        for chunk_text, metadata in zip(result["documents"], result["metadatas"]):
            chunks_by_document_id.setdefault(metadata["documentId"], []).append(
                (metadata["chunkIndex"], metadata["chunkCount"], chunk_text)
            )

        file_texts_by_document_id = {}
        for document_id, chunks in chunks_by_document_id.items():
            chunks.sort()
            if len(chunks) != chunks[0][1]:
                logger.warning(f"{document_id} has {len(chunks)} of its {chunks[0][1]} chunks")
            file_texts_by_document_id[document_id] = "\n".join(
                FileConvertService.remove_header(document_id, chunk_text) for _, _, chunk_text in chunks
            )
        return file_texts_by_document_id

    def init_collection(self):
        """Load the embedding model now, so the first search does not.

        `collection()` caches what it builds, and building it is what costs
        the seconds - loading the sentence-transformer. Called as the user
        portal opens, that wait overlaps with reading the screen and typing a
        query, instead of landing in front of someone who has just asked a
        question and is watching a spinner.

        Blocking, so call it on a worker thread. Failures are logged and
        swallowed: this is a head start, not a search. A missing store or a
        model that will not load is reported properly by `search()`, which is
        where somebody is actually waiting on the answer.
        """
        logger.info("Initialising the collection, ahead of the first search")
        try:
            self.collection()
        except Exception as error:
            logger.warning(f"Could not initialise the collection - {error}")

    def collection(self):
        """The collection to query, or None when it does not exist yet.

        Fetched fresh every call, deliberately. A reset does not empty the
        collection, it deletes it and creates another
        (`FileEmbedderService.reset_collection`), and the new one carries a new
        internal id. A handle held across that reset therefore points at
        something chroma has dropped, and every query after it fails with
        `Collection [<uuid>] does not exist` - while none of the settings this
        used to key its cache on has changed, so nothing could notice.

        Only the model is cached, and it is the part that costs: loading it is
        seconds, while listing and getting a collection are metadata lookups.
        """
        chroma_store_dir = settingService.get_path(PATHS_CHROMA_STORE)
        collection_name = settingService.find_active_by_key(EMBEDDING_COLLECTION)
        embedding_model = settingService.find_active_by_key(EMBEDDING_MODEL)

        client = chromadb.PersistentClient(
            path=chroma_store_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        names = [
            collection.name if hasattr(collection, "name") else collection
            for collection in client.list_collections()
        ]
        if collection_name not in names:
            logger.info(f"No collection '{collection_name}' in {chroma_store_dir}")
            return None

        return client.get_collection(
            name=collection_name,
            embedding_function=self.embedding_function(embedding_model),
        )

    def embedding_function(self, embedding_model):
        """The sentence-transformer, loaded once per model name.

        This is the load `init_collection` exists to get out of the way of the
        first search, so it is kept for the life of the process - keyed on the
        model it was built from, so changing that on the Settings screen loads
        the new one instead of searching with the old.
        """
        if embedding_model != self._embedding_model:
            logger.info(f"Loading embedding model {embedding_model}")
            self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=embedding_model
            )
            self._embedding_model = embedding_model
        return self._embedding_function


# Shared instance - the cached model is what keeps the load to the first
# search of the process rather than every search.
searchService = SearchService()
