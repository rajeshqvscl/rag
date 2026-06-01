"""
Namespace Registry - Centralized namespace management

Ensures consistent namespace generation across all components:
- Embedder
- Retriever
- Vector Store
- Cache

Eliminates partial normalization and inconsistent propagation issues.
"""

import hashlib
from typing import Optional
from app.rag.embedder import CACHE_VERSION, EMBEDDING_DIM


class NamespaceRegistry:
    """
    Centralized namespace generation and validation.

    All systems MUST use this class to generate namespaces to ensure
    consistency across embedding, retrieval, and caching layers.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
        return cls._instance

    @staticmethod
    def generate(doc_id: str, embedding_dim: int = EMBEDDING_DIM) -> str:
        """
        Generate canonical namespace for a document.

        Args:
            doc_id: Unique document identifier (e.g., file hash)
            embedding_dim: Embedding dimension for version tracking

        Returns:
            Canonical namespace string
        """
        key = f"{doc_id}_emb{embedding_dim}"
        return key

    @staticmethod
    def from_filename(file_name: str) -> str:
        """
        Generate namespace from file name.

        Args:
            file_name: Original file name

        Returns:
            Namespace string
        """
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9]', '_', file_name.lower())
        sanitized = sanitized[:50]
        file_hash = hashlib.md5(file_name.encode()).hexdigest()[:8]
        return f"{sanitized}_{file_hash}"

    @staticmethod
    def from_doc_id(doc_id: str) -> str:
        """
        Generate namespace from doc_id.

        Args:
            doc_id: Document ID (usually file hash)

        Returns:
            Namespace string with version
        """
        return NamespaceRegistry.generate(doc_id)

    @staticmethod
    def validate(namespace: str) -> bool:
        """
        Validate namespace format.

        Args:
            namespace: Namespace to validate

        Returns:
            True if valid format
        """
        if not namespace:
            return False
        if len(namespace) < 3:
            return False
        return True

    @staticmethod
    def extract_doc_id(namespace: str) -> Optional[str]:
        """
        Extract doc_id from namespace.

        Args:
            namespace: Namespace string

        Returns:
            Original doc_id or None
        """
        parts = namespace.split("_")
        if len(parts) >= 2:
            return parts[-1]
        return None


def get_canonical_namespace(doc_id: str = None, file_name: str = None) -> str:
    """
    Get canonical namespace using available inputs.

    Priority: doc_id > file_name

    Args:
        doc_id: Document ID (preferred)
        file_name: File name (fallback)

    Returns:
        Canonical namespace
    """
    if doc_id:
        return NamespaceRegistry.from_doc_id(doc_id)
    elif file_name:
        return NamespaceRegistry.from_filename(file_name)
    else:
        raise ValueError("Either doc_id or file_name must be provided")


def normalize_namespace(namespace: str) -> str:
    """
    Normalize namespace to canonical format.

    Args:
        namespace: Input namespace (possibly inconsistent)

    Returns:
        Normalized namespace
    """
    if not namespace:
        return CACHE_VERSION

    namespace = namespace.strip()

    if "_emb" in namespace:
        return namespace

    if "_v" in namespace:
        parts = namespace.split("_v")
        return f"{parts[0]}_emb{EMBEDDING_DIM}"

    return f"{namespace}_emb{EMBEDDING_DIM}"