from .pinecone_client import index
from .embedder import EMBEDDING_DIM
import time

NAMESPACE_VERSION = f"v{EMBEDDING_DIM}"


def version_namespace(base_namespace: str) -> str:
    """Add version suffix to namespace to prevent cross-dimension contamination."""
    if NAMESPACE_VERSION in base_namespace:
        return base_namespace
    return f"{base_namespace}_{NAMESPACE_VERSION}"


def clear_vector_store():
    """
    Clears all vectors in the index.
    Safe for serverless and pod-based indexes.
    """
    try:
        index.delete(delete_all=True)
        time.sleep(0.5)
        print("[SUCCESS] Vector store index wiped.")
    except Exception as e:
        print(f"[WARNING] Could not wipe index (might be empty or already clearing): {e}")
        raise e

def store_embeddings(chunks, embeddings, namespace="default", doc_id=None, domain="General"):
    """
    Store embeddings in Pinecone with metadata
    """
    versioned_ns = version_namespace(namespace)
    print(f"\n[DEBUG] STORING EMBEDDINGS")
    print(f"[DEBUG] Namespace: {namespace} -> {versioned_ns}")
    print(f"[DEBUG] Doc ID: {doc_id}")
    print(f"[DEBUG] Domain: {domain}")
    print(f"[DEBUG] Chunks: {len(chunks)}")

    vectors = []
    for i, (chunk_obj, embedding) in enumerate(zip(chunks, embeddings)):
        metadata = {
            "text": chunk_obj["content"],
            "source": versioned_ns,
            "page": chunk_obj["metadata"]["page"],
            "section": chunk_obj["metadata"]["section"],
            "doc_id": doc_id if doc_id else namespace,
            "domain": domain
        }

        vectors.append({
            "id": f"{versioned_ns}_{i}",
            "values": embedding,
            "metadata": metadata
        })

    # 🔥 Upsert to Pinecone with versioned namespace
    index.upsert(vectors=vectors, namespace=versioned_ns)
    print(f"[SUCCESS] Stored {len(vectors)} chunks in Pinecone (Namespace: {versioned_ns})\n")


def save_index(chunks, document_name=None):
    """
    Legacy function - stores chunks to Pinecone
    """
    from .embedder import embed_text

    if not chunks:
        return {"status": "no_chunks", "count": 0}

    namespace = document_name or "default"
    versioned_ns = version_namespace(namespace)
    texts = [c["content"] if isinstance(c, dict) else str(c) for c in chunks]
    embeddings = embed_text(texts, namespace=versioned_ns)

    store_embeddings(chunks, embeddings, namespace=namespace)

    return {"status": "stored", "count": len(chunks)}