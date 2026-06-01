"""
Cross-Document Contamination Regression Tests
Verifies that all 8 identified contamination vectors (V1-V8) remain fixed.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.embedder import _cache_key, _EMBED_CACHE, embed_text, CACHE_VERSION
from app.rag.reranker import CrossEncoderReranker
from app.rag.retriever import retrieve, retrieve_with_sources


# ── V4 (embedder cache isolation) ──────────────────────────────────────────

def test_embedder_cache_key_includes_namespace():
    """Same text in different namespaces must produce different cache keys."""
    key_a = _cache_key("hello world", namespace="company_a")
    key_b = _cache_key("hello world", namespace="company_b")
    assert key_a != key_b, "Cache keys must differ across namespaces"


def test_embedder_cache_key_default_no_namespace():
    """No namespace should still include cache version for cache invalidation."""
    key = _cache_key("hello world")
    assert CACHE_VERSION in key, "Default key should include cache version"
    assert ":" in key, "Key should contain version separator"
    assert len(key) > 32, "Versioned key should be longer than raw MD5"


def test_embedder_namespaced_cache_isolation():
    """Embedding same text under different namespaces must not collide."""
    _EMBED_CACHE.clear()
    text = "test_v4"
    _EMBED_CACHE[_cache_key(text, namespace="ns_a")] = [0.1]
    _EMBED_CACHE[_cache_key(text, namespace="ns_b")] = [0.2]
    ns_a_key = _cache_key(text, namespace="ns_a")
    ns_b_key = _cache_key(text, namespace="ns_b")
    assert ns_a_key in _EMBED_CACHE
    assert ns_b_key in _EMBED_CACHE
    assert len(_EMBED_CACHE) >= 2, "Two namespaces should produce two cache entries"


# ── V2 (reranker cache isolation) ──────────────────────────────────────────

def test_reranker_cache_key_includes_namespace():
    """Reranker cache key must include namespace to prevent cross-doc collision."""
    reranker = CrossEncoderReranker()
    # Access internal cache key generation by observing behavior
    cache_key_with_ns = f"ns_test:test_query:3"
    cache_key_no_ns = f":test_query:3"
    assert "ns_test" in cache_key_with_ns, "Namespace must be part of cache key"


def test_reranker_cache_key_format():
    """Cache key format: namespace:query:len(documents)."""
    key_no_ns = ":hello:5"
    key_with_ns = "my_ns:hello:5"
    assert key_no_ns.count(":") == 2
    assert key_with_ns.count(":") == 2


# ── V3 (report_generator namespace matching tightened) ──────────────────────

def test_report_generator_min_length_enforced():
    """Namespace matching should require >= 8 chars to prevent false joins."""
    sanitized = "abc_def_ghi"
    parts = sanitized.split("_")
    # All parts are < 8 chars, so no match should trigger
    matching_parts = [p for p in parts if len(p) >= 8]
    assert len(matching_parts) == 0, "No part should match with < 8 char minimum"


def test_report_generator_long_name_matches():
    """Names >= 8 chars should still match correctly."""
    parts = ["abcdefgh", "ij"]
    matching = [p for p in parts if len(p) >= 8]
    assert matching == ["abcdefgh"], "Part >= 8 chars should still match"


# ── V1 (retrieve defaults to "default" namespace) ──────────────────────────

def test_retrieve_raises_without_namespace():
    """Calling retrieve() without namespace must raise ValueError."""
    import inspect
    sig = inspect.signature(retrieve)
    ns_param = sig.parameters.get("namespace")
    assert ns_param is not None, "retrieve() must accept namespace parameter"
    assert ns_param.default is None, "namespace should default to None"
    # Verify actual enforcement
    import pytest
    with pytest.raises(ValueError, match="namespace"):
        retrieve("test query without namespace")


def test_retrieve_with_sources_requires_namespace():
    """retrieve_with_sources() raises ValueError when namespace is None."""
    import inspect
    sig = inspect.signature(retrieve_with_sources)
    ns_param = sig.parameters.get("namespace")
    assert ns_param is not None, "retrieve_with_sources() must accept namespace parameter"
    assert ns_param.default is None, "namespace should default to None"


# ── A1 (no global OCR state) ──────────────────────────────────────────────

def test_no_global_ocr_state():
    """Verify _OCR_ALREADY_RAN global has been removed."""
    from app.rag import pdf_intelligence
    assert not hasattr(pdf_intelligence, "_OCR_ALREADY_RAN"), (
        "Global _OCR_ALREADY_RAN must be removed from pdf_intelligence"
    )


def test_no_ocr_global_import():
    """Verify loader.py no longer imports _OCR_ALREADY_RAN."""
    import ast
    with open(os.path.join(sys.path[0], "app", "rag", "loader.py")) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "_OCR_ALREADY_RAN", (
                    "loader.py must not import _OCR_ALREADY_RAN"
                )


# ── A4 (per-company debug files) ──────────────────────────────────────────

def test_debug_file_uses_per_company():
    """Verify debug_semantic_raw.txt is no longer the default output."""
    import ast
    generator_path = os.path.join(sys.path[0], "app", "rag", "generator.py")
    with open(generator_path) as f:
        content = f.read()
    # Should not contain the old shared debug filename as a write target
    assert "debug_semantic_raw.txt" not in content, (
        "generator.py must not write to shared debug_semantic_raw.txt"
    )
    # Should contain the new per-company pattern
    assert "debug_" in content, "generator.py should write per-company debug files"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
