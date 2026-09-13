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

logger = logging.getLogger(__name__)


class SearchService:

    def __init__(self):
        #: The loaded sentence-transformer and the model name it was built
        #: from. The only thing worth keeping between calls: loading it is the
        #: seconds, and everything else here is a metadata lookup.
        self._embedding_model = None
        self._embedding_function = None

    def search(self, query):
        """The closest documents to `query`, closest first.

        An empty list for a blank query, and for a collection that is not
        there - nothing has been embedded, which is not an error.
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
        count = collection.count()
        if not count:
            return []

        logger.info(f"Searching '{query}' for the closest {min(wanted, count)} of {count}")
        result = collection.query(
            query_texts=[query],
            n_results=min(wanted, count),
            include=["documents", "metadatas", "distances"],
        )

        return [
            SearchResult.from_chroma(document_id, metadata, distance, file_text)
            for document_id, metadata, distance, file_text in zip(
                result["ids"][0],
                result["metadatas"][0],
                result["distances"][0],
                result["documents"][0],
            )
        ]

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
