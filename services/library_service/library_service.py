"""Read-only view of what is in the Chroma collection.

What the Library screen reads. It only ever gets metadata, never the embedded
text and never a query, so it builds no embedding function - which is what
keeps it off the SentenceTransformer model that `FileEmbedderService` loads in
its constructor.

Like the other standalone services it takes its store and collection as
arguments, defaulting to the setting table.
"""

import logging

import chromadb
from chromadb.config import Settings

from constant.settings import EMBEDDING_COLLECTION, PATHS_CHROMA_STORE
from model.Document import Document
from services.SettingService import settingService

logger = logging.getLogger(__name__)


class LibraryService:

    def __init__(self, chroma_store_dir=None, collection_name=None):
        self.chroma_store_dir = chroma_store_dir or settingService.get_path(PATHS_CHROMA_STORE)
        self.collection_name = (
            collection_name or settingService.find_active_by_key(EMBEDDING_COLLECTION)
        )

    def find_all_documents(self):
        """Every document in the collection, sorted by label.

        An empty list when the collection does not exist - never embedded, or
        a reset dropped it and stopped before refilling it. That is an empty
        library, not an error, and the screen says so.
        """
        client = self._client()
        if not self.collection_exists(client):
            logger.info(f"No collection '{self.collection_name}' in {self.chroma_store_dir}")
            return []

        collection = client.get_collection(self.collection_name)
        result = collection.get(include=["metadatas"])
        documents = [
            Document.from_chroma(document_id, metadata)
            for document_id, metadata in zip(result["ids"], result["metadatas"])
        ]
        documents.sort(key=lambda document: document.label.lower())
        logger.info(f"Read {len(documents)} documents from '{self.collection_name}'")
        return documents

    def collection_exists(self, client):
        """Asked rather than caught: `get_collection` raises a different
        exception type across chroma versions, and the name list does not."""
        return self.collection_name in [
            getattr(collection, "name", collection)
            for collection in client.list_collections()
        ]

    def _client(self):
        return chromadb.PersistentClient(
            path=self.chroma_store_dir,
            settings=Settings(anonymized_telemetry=False),
        )
