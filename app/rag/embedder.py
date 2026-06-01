import os
import time
import random
import hashlib
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Optional

load_dotenv()

EMBEDDING_MODEL = "bge-base-en-v1.5"
EMBEDDING_DIM = 768

RERANKER_VERSION = "v1"
CHUNKER_VERSION = "v1"
ONTOLOGY_VERSION = "v1"
CACHE_VERSION = f"emb{EMBEDDING_DIM}-rer{RERANKER_VERSION}-chunk{CHUNKER_VERSION}-onto{ONTOLOGY_VERSION}"

JINA_API_KEY = os.getenv("JINA_API_KEY")

URL = "https://api.jina.ai/v1/embeddings"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
BATCH_SIZE = 10

_EMBED_CACHE: dict = {}
_CACHE_DIR = Path("cache/embeddings")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_LOCAL_EMBEDDER = None


def _get_local_embedder():
    global _LOCAL_EMBEDDER
    if _LOCAL_EMBEDDER is None:
        try:
            from sentence_transformers import SentenceTransformer
            _LOCAL_EMBEDDER = SentenceTransformer(EMBEDDING_MODEL, cache_folder="cache/sentence_transformers")
        except ImportError:
            _LOCAL_EMBEDDER = False
        except Exception:
            _LOCAL_EMBEDDER = False
    return _LOCAL_EMBEDDER if _LOCAL_EMBEDDER is not False else None


def get_embedding_dimension() -> int:
    """Return the expected embedding dimension."""
    return EMBEDDING_DIM


def validate_embedding_dimension(dim: int) -> bool:
    """Validate that a given dimension matches expected embedding dimension."""
    return dim == EMBEDDING_DIM


def get_cache_version() -> str:
    """Return the current cache version string for external cache keys."""
    return CACHE_VERSION


def _cache_key(text: str, namespace: str = "") -> str:
    raw = hashlib.md5(text.lower().strip().encode()).hexdigest()
    versioned_ns = f"{namespace}_{CACHE_VERSION}" if namespace else CACHE_VERSION
    return f"{versioned_ns}:{raw}"


def _disk_path(key: str) -> Path:
    safe = key.replace(":", "_").replace("/", "_")
    return _CACHE_DIR / f"{safe}.npy"


def _load_from_disk(key: str):
    path = _disk_path(key)
    if path.exists():
        try:
            return np.load(path).tolist()
        except Exception:
            pass
    return None


def _save_to_disk(key: str, embedding):
    try:
        np.save(_disk_path(key), np.array(embedding, dtype=np.float32))
    except Exception as e:
        print(f"[EMBEDDER] Disk cache write error: {e}")


def _embed_batch_jina(texts: List[str], namespace: str = "") -> Optional[List]:
    """Embed a single batch via Jina API with retries."""
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": "jina-embeddings-v2-base-en", "input": texts}

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            import requests
            response = requests.post(URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                return [item["embedding"] for item in data["data"]]
            last_error = f"Jina HTTP {response.status_code}: {response.text[:200]}"
        except requests.exceptions.Timeout:
            last_error = f"Timeout (attempt {attempt + 1}/{MAX_RETRIES})"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

        if attempt < MAX_RETRIES - 1:
            delay = (2 ** attempt) + random.uniform(0, 1)
            print(f"[EMBEDDER] Retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s: {last_error}")
            time.sleep(delay)

    print(f"[EMBEDDER] Jina failed after {MAX_RETRIES} retries: {last_error}")
    return None


def _embed_local(texts: List[str]) -> Optional[List]:
    """Fallback to local BGE embedding."""
    model = _get_local_embedder()
    if model is None:
        return None
    try:
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        return embeddings.tolist()
    except Exception as e:
        print(f"[EMBEDDER] Local embedding failed: {e}")
        return None


def _embed_batch(texts: List[str], namespace: str = "") -> Optional[List]:
    """Try Jina first, fallback to local."""
    if JINA_API_KEY:
        result = _embed_batch_jina(texts, namespace)
        if result:
            return result
    result = _embed_local(texts)
    if result:
        print(f"[EMBEDDER] Using local BGE fallback for {len(texts)} texts")
        return result
    return None


def embed_text(texts, namespace: str = ""):
    """Embed texts with in-memory + disk cache, batch processing, retry logic,
    and local BGE fallback when Jina is unavailable."""
    if isinstance(texts, str):
        texts = [texts]

    result = [None] * len(texts)
    to_fetch_indices = []
    to_fetch_texts = []

    for i, t in enumerate(texts):
        key = _cache_key(t, namespace)
        if key in _EMBED_CACHE:
            result[i] = _EMBED_CACHE[key]
        else:
            disk_val = _load_from_disk(key)
            if disk_val is not None:
                _EMBED_CACHE[key] = disk_val
                result[i] = disk_val
            else:
                to_fetch_indices.append(i)
                to_fetch_texts.append(t)

    if not to_fetch_texts:
        return result

    # Process in batches
    batches = [to_fetch_texts[i:i + BATCH_SIZE] for i in range(0, len(to_fetch_texts), BATCH_SIZE)]
    batch_offset = 0
    for batch_texts in batches:
        batch_embs = _embed_batch(batch_texts, namespace)
        if batch_embs is None:
            batch_embs = [np.zeros(EMBEDDING_DIM).tolist()] * len(batch_texts)
            print(f"[EMBEDDER] All embedding sources failed — using zero vectors for {len(batch_texts)} texts")
        for j, emb in enumerate(batch_embs):
            global_idx = to_fetch_indices[batch_offset + j]
            result[global_idx] = emb
            key = _cache_key(batch_texts[j], namespace)
            _EMBED_CACHE[key] = emb
            _save_to_disk(key, emb)
        batch_offset += len(batch_texts)

    return result
