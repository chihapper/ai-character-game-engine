"""Long-term memory: local vector recall across sessions.

Each completed exchange (user turn + character reply) is embedded with a local
sentence-transformers model and stored in an embedded ChromaDB collection. On each
new turn we retrieve the top-k most relevant past exchanges and inject them into
the prompt — this is what makes the character feel like it remembers you between
sessions.

Everything runs locally and free: no embedding API calls. The embedding model and
Chroma client are heavy/blocking, so calls are dispatched to worker threads and
the model/client are created lazily and shared across characters.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from ..config import get_settings

logger = logging.getLogger(__name__)

# Long-term memory depends on the optional ML extras (chromadb +
# sentence-transformers). If they aren't installed, the app still runs — the
# character just won't have cross-session recall. We detect availability once.
try:
    import chromadb  # noqa: F401
    from sentence_transformers import SentenceTransformer  # noqa: F401

    _AVAILABLE = True
except Exception:  # ImportError, or a backend that failed to build
    _AVAILABLE = False

# Shared singletons — one embedding model and one Chroma client for the process.
_model = None
_client = None
_warned = False


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        logger.info("Loading embedding model '%s'...", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _get_client():
    global _client
    if _client is None:
        import chromadb

        settings = get_settings()
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
    return _client


def _warn_unavailable_once() -> None:
    global _warned
    if not _warned:
        logger.warning(
            "Long-term memory disabled: optional extras (chromadb + "
            "sentence-transformers) not installed. Install "
            "requirements-optional.txt to enable cross-session recall."
        )
        _warned = True


class LongTermMemory:
    def __init__(self, namespace: str) -> None:
        # One Chroma collection per character namespace keeps memories isolated.
        # Collection names must be 3-63 chars; namespaces from configs satisfy this.
        self._namespace = namespace
        self._top_k = get_settings().long_term_top_k

    def _collection(self):
        return _get_client().get_or_create_collection(name=self._namespace)

    # --- writes ---

    def _add_sync(self, user_text: str, assistant_text: str) -> None:
        document = f"User: {user_text}\n{self._namespace}: {assistant_text}"
        embedding = _get_model().encode(document).tolist()
        self._collection().add(
            ids=[uuid.uuid4().hex],
            documents=[document],
            embeddings=[embedding],
        )

    async def add_exchange(self, user_text: str, assistant_text: str) -> None:
        if not _AVAILABLE:
            _warn_unavailable_once()
            return
        if not user_text or not assistant_text:
            return
        await asyncio.to_thread(self._add_sync, user_text, assistant_text)

    # --- reads ---

    def _retrieve_sync(self, query: str, k: int) -> list[str]:
        collection = self._collection()
        if collection.count() == 0:
            return []
        embedding = _get_model().encode(query).tolist()
        result = collection.query(
            query_embeddings=[embedding],
            n_results=min(k, collection.count()),
        )
        docs = result.get("documents") or [[]]
        return docs[0]

    async def retrieve(self, query: str, k: int | None = None) -> list[str]:
        if not _AVAILABLE or not query:
            return []
        return await asyncio.to_thread(self._retrieve_sync, query, k or self._top_k)
