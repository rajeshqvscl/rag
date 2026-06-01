"""
Tests for PipelineOrchestrator:
1. Per-document caching (generation, retrieval stages)
2. Quality gates (skip/downgrade based on prerequisite health)
3. Degraded-state confidence adjustments
4. Budget reduction when text extraction is degraded
"""

import sys, os, json, hashlib, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.pipeline_orchestrator import (
    PipelineOrchestrator, DeckComplexityScorer, DeckComplexity,
    cache_get, cache_set, cache_clear,
    _CACHEABLE_STAGES, _QUALITY_GATES,
    run_pipeline,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

SAMPLE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)

SAMPLE_FILE_NAME = "test_deck.pdf"


def make_orch(content=None):
    return PipelineOrchestrator(content or SAMPLE_PDF, SAMPLE_FILE_NAME)


# ─── 1. Caching Tests ────────────────────────────────────────────────────

def test_cache_set_get_roundtrip():
    cache_clear()
    doc_hash = hashlib.md5(b"test").hexdigest()[:16]
    cache_set(doc_hash, "generation", {"summary": "test", "email": "hello"})
    val = cache_get(doc_hash, "generation")
    assert val is not None
    assert val["summary"] == "test"
    assert val["email"] == "hello"
    cache_clear(doc_hash)


def test_cache_get_miss_returns_none():
    cache_clear()
    val = cache_get("nonexistent123", "generation")
    assert val is None


def test_clear_by_doc_hash():
    doc_hash = hashlib.md5(b"clear_test").hexdigest()[:16]
    cache_set(doc_hash, "generation", {"data": 1})
    cache_set(doc_hash, "retrieval", {"data": 2})
    assert cache_get(doc_hash, "generation") is not None
    assert cache_get(doc_hash, "retrieval") is not None
    cache_clear(doc_hash)
    assert cache_get(doc_hash, "generation") is None
    assert cache_get(doc_hash, "retrieval") is None


def test_clear_all():
    h1 = hashlib.md5(b"doc1").hexdigest()[:16]
    h2 = hashlib.md5(b"doc2").hexdigest()[:16]
    cache_set(h1, "generation", {"x": 1})
    cache_set(h2, "generation", {"x": 2})
    cache_clear()
    assert cache_get(h1, "generation") is None
    assert cache_get(h2, "generation") is None


def test_cacheable_stages_defined():
    assert "retrieval" in _CACHEABLE_STAGES
    assert "generation" not in _CACHEABLE_STAGES  # removed — outputs go stale


def test_orchestrator_cache_hit_tracked():
    cache_clear()
    orch = make_orch()
    doc_hash = orch.doc_hash
    # Manually populate cache for retrieval (cacheable stage)
    cache_set(doc_hash, "retrieval", {"sections": {"financials": ["cached data"]}})
    def _mock_fn(*a, **kw):
        raise AssertionError("Stage should NOT execute — cache should serve")
    result = orch.run_stage("retrieval", _mock_fn)
    assert result == {"sections": {"financials": ["cached data"]}}
    assert "retrieval" in orch._cache_hits
    assert "retrieval" in orch.get_cache_hits()
    cache_clear(doc_hash)


def test_orchestrator_cache_miss_runs_fn():
    cache_clear()
    orch = make_orch()
    doc_hash = orch.doc_hash
    cache_clear(doc_hash)  # ensure no cache
    ran = {"called": False}
    def _mock_fn(*a, **kw):
        ran["called"] = True
        return {"sections": {"financials": ["fresh data"]}}
    result = orch.run_stage("retrieval", _mock_fn)
    assert ran["called"]
    assert result == {"sections": {"financials": ["fresh data"]}}


def test_orchestrator_cache_writes_after_success():
    cache_clear()
    orch = make_orch()
    doc_hash = orch.doc_hash
    cache_clear(doc_hash)
    def _mock_fn(*a, **kw):
        return {"sections": {"financials": ["now cached"]}}
    orch.run_stage("retrieval", _mock_fn)
    # Verify it was written to disk cache
    cached = cache_get(doc_hash, "retrieval")
    assert cached is not None
    assert cached["sections"]["financials"] == ["now cached"]
    cache_clear(doc_hash)


# ─── 2. Quality Gate Tests ───────────────────────────────────────────────

def test_quality_gates_defined():
    assert "retrieval" in _QUALITY_GATES
    assert "generation" in _QUALITY_GATES
    assert "scoring" in _QUALITY_GATES
    assert "strategy" in _QUALITY_GATES


def test_quality_gate_skips_retrieval_when_embedding_failed():
    orch = make_orch()
    orch.stages["embedding"] = type("SR", (), {
        "name": "embedding", "status": "failed",
        "confidence_multiplier": 0.0,
        "duration_ms": 10, "error": "failed",
        "skipped_reason": "",
    })()
    def _mock_fn(*a, **kw):
        raise AssertionError("Should not run — quality gate should skip")
    result = orch.run_stage("retrieval", _mock_fn)
    assert result is None
    assert orch.stages["retrieval"].status == "skipped"
    assert "quality gate" in orch.stages["retrieval"].skipped_reason


def test_quality_gate_skips_retrieval_when_embedding_low_confidence():
    orch = make_orch()
    orch.stages["embedding"] = type("SR", (), {
        "name": "embedding", "status": "degraded",
        "confidence_multiplier": 0.2,  # below 0.3 threshold
        "duration_ms": 10, "error": "",
        "skipped_reason": "",
    })()
    def _mock_fn(*a, **kw):
        raise AssertionError("Should not run")
    result = orch.run_stage("retrieval", _mock_fn)
    assert result is None
    assert orch.stages["retrieval"].status == "skipped"


def test_quality_gate_allows_retrieval_when_embedding_ok():
    orch = make_orch()
    orch.stages["embedding"] = type("SR", (), {
        "name": "embedding", "status": "degraded",
        "confidence_multiplier": 0.5,  # above 0.3 threshold
        "duration_ms": 10, "error": "",
        "skipped_reason": "",
    })()
    ran = {"called": False}
    def _mock_fn(*a, **kw):
        ran["called"] = True
        return {"sections": {"financials": ["data"]}}
    result = orch.run_stage("retrieval", _mock_fn)
    assert ran["called"]
    assert result == {"sections": {"financials": ["data"]}}


def test_quality_gate_no_effect_when_prereq_not_run():
    """If prerequisite hasn't run yet, quality gate should pass through."""
    orch = make_orch()
    ran = {"called": False}
    def _mock_fn(*a, **kw):
        ran["called"] = True
        return "ok"
    # Generation gate checks 'retrieval' — which hasn't run yet
    result = orch.run_stage("generation", _mock_fn)
    assert ran["called"]
    assert result == "ok"


def test_quality_gate_skips_chain_on_critical_failure():
    """When text_extraction fails, pipeline aborts and all subsequent stages skip."""
    orch = make_orch()
    orch.run_stage("text_extraction", lambda: (_ for _ in ()).throw(Exception("crash")))
    assert orch._aborted
    assert orch.stages["text_extraction"].status == "failed"
    # All subsequent stages should be skipped
    def _mock_fn(*a, **kw):
        raise AssertionError("Should not run")
    result = orch.run_stage("domain_detection", _mock_fn)
    assert result is None
    assert orch.stages["domain_detection"].status == "skipped"


# ─── 3. Degraded Confidence Tests ────────────────────────────────────────

def test_infra_confidence_all_success():
    orch = make_orch()
    orch.stages["text_extraction"] = type("SR", (), {
        "name": "text_extraction", "status": "success",
        "confidence_multiplier": 1.0,
        "duration_ms": 100, "error": "",
        "skipped_reason": "",
    })()
    orch.stages["embedding"] = type("SR", (), {
        "name": "embedding", "status": "success",
        "confidence_multiplier": 1.0,
        "duration_ms": 100, "error": "",
        "skipped_reason": "",
    })()
    conf = orch.get_infra_confidence()
    assert conf == 1.0


def test_infra_confidence_with_degraded():
    orch = make_orch()
    for name, mult in [("text_extraction", 1.0), ("embedding", 0.7),
                        ("retrieval", 0.7), ("generation", 0.7)]:
        orch.stages[name] = type("SR", (), {
            "name": name, "status": "degraded" if mult < 1 else "success",
            "confidence_multiplier": mult,
            "duration_ms": 100, "error": "",
            "skipped_reason": "",
        })()
    conf = orch.get_infra_confidence()
    assert conf > 0.5
    assert conf < 1.0


def test_infra_confidence_with_failure():
    orch = make_orch()
    # With text_extraction (weight 0.20, mult 1.0) and embedding (weight 0.15, mult 0.0):
    # weighted avg = (0.20*1.0 + 0.15*0.0) / (0.20+0.15) = 0.20/0.35 ≈ 0.57
    for name, mult in [("text_extraction", 1.0), ("embedding", 0.0)]:
        orch.stages[name] = type("SR", (), {
            "name": name, "status": "failed" if mult == 0 else "success",
            "confidence_multiplier": mult,
            "duration_ms": 10, "error": "",
            "skipped_reason": "",
        })()
    conf = orch.get_infra_confidence()
    assert conf < 0.7  # should be reduced from 1.0
    assert conf == 0.57  # updated weight calc


def test_infra_confidence_empty_stages():
    orch = make_orch()
    assert orch.get_infra_confidence() == 1.0


def test_get_degraded_stages():
    orch = make_orch()
    orch.stages["text_extraction"] = type("SR", (), {
        "name": "text_extraction", "status": "success",
        "confidence_multiplier": 1.0, "duration_ms": 10,
        "error": "", "skipped_reason": "",
    })()
    orch.stages["embedding"] = type("SR", (), {
        "name": "embedding", "status": "failed",
        "confidence_multiplier": 0.0, "duration_ms": 10,
        "error": "API error", "skipped_reason": "",
    })()
    orch.stages["generation"] = type("SR", (), {
        "name": "generation", "status": "degraded",
        "confidence_multiplier": 0.7, "duration_ms": 5000,
        "error": "completed but degraded", "skipped_reason": "",
    })()
    degraded = orch.get_degraded_stages()
    names = [d["name"] for d in degraded]
    assert "embedding" in names
    assert "generation" in names
    assert "text_extraction" not in names


# ─── 4. DeckComplexityScorer Tests ──────────────────────────────────────

def test_complexity_scorer_fallback():
    # Empty/invalid bytes should produce fallback complexity
    c = DeckComplexityScorer.scan(b"not a pdf", "bad.pdf")
    assert c.page_count == 0
    assert c.complexity_score == 0.5  # neutral fallback
    assert c.recommended_budget["max_charts_to_analyze"] == 10


def test_complexity_scorer_recommended_budget():
    c = DeckComplexityScorer.scan(SAMPLE_PDF, SAMPLE_FILE_NAME)
    assert c.page_count >= 1
    assert "max_charts_to_analyze" in c.recommended_budget
    assert "max_chunks" in c.recommended_budget
    assert "retrieval_top_k" in c.recommended_budget


def test_complexity_summary():
    orch = make_orch()
    summary = orch.get_complexity_summary()
    assert "Deck:" in summary
    assert "complexity=" in summary


def test_stage_summary():
    orch = make_orch()
    orch.stages["text_extraction"] = type("SR", (), {
        "name": "text_extraction", "status": "success",
        "confidence_multiplier": 1.0, "duration_ms": 50,
        "error": "", "skipped_reason": "",
    })()
    summary = orch.get_stage_summary()
    assert "text_extraction" in summary
    assert "OK" in summary or "~" in summary or "X" in summary


# ─── 5. Edge cases ──────────────────────────────────────────────────────

def test_quality_gate_nonexistent_stage_allowed():
    """Stages not in quality gates should always be allowed."""
    orch = make_orch()
    ok, reason = orch._check_quality_gate("nonexistent_stage")
    assert ok


def test_cache_clear_by_key():
    cache_clear()
    doc_hash = hashlib.md5(b"key_test").hexdigest()[:16]
    cache_set(doc_hash, "generation", {"a": 1})
    cache_set(doc_hash, "retrieval", {"b": 2})
    cache_clear(doc_hash, "generation")
    assert cache_get(doc_hash, "generation") is None
    assert cache_get(doc_hash, "retrieval") is not None
    cache_clear(doc_hash)


def test_cache_invalid_json_handled():
    """Corrupt cache file returns None instead of crashing."""
    cache_clear()
    doc_hash = hashlib.md5(b"corrupt").hexdigest()[:16]
    path = os.path.join("cache", "pipeline", f"{doc_hash}_generation.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("{invalid json}")
    val = cache_get(doc_hash, "generation")
    assert val is None
    os.unlink(path)


def test_get_cache_hits_empty():
    orch = make_orch()
    assert orch.get_cache_hits() == []


# ─── 6. Sub-Component Tracking Tests ────────────────────────────────────

def test_track_sub_component_records():
    orch = make_orch()
    orch.stages["generation"] = type("SR", (), {
        "name": "generation", "status": "success",
        "confidence_multiplier": 1.0, "duration_ms": 100,
        "error": "", "skipped_reason": "",
    })()
    orch.track_sub_component("generation", "visual_intelligence", "failed", 0.3)
    assert "generation" in orch._sub_components
    assert orch._sub_components["generation"]["visual_intelligence"].status == "failed"
    # parent stage should be degraded
    assert orch.stages["generation"].status == "degraded"
    assert orch.stages["generation"].confidence_multiplier < 1.0


def test_track_sub_component_degraded_lowers_confidence():
    orch = make_orch()
    orch.stages["generation"] = type("SR", (), {
        "name": "generation", "status": "success",
        "confidence_multiplier": 1.0, "duration_ms": 100,
        "error": "", "skipped_reason": "",
    })()
    orch.track_sub_component("generation", "llm_extraction", "degraded", 0.5)
    assert orch.stages["generation"].status == "degraded"
    assert orch.stages["generation"].confidence_multiplier == 0.5


def test_sub_component_summary():
    orch = make_orch()
    orch.stages["generation"] = type("SR", (), {
        "name": "generation", "status": "success",
        "confidence_multiplier": 1.0, "duration_ms": 100,
        "error": "", "skipped_reason": "",
    })()
    orch.track_sub_component("generation", "visual_intelligence", "failed", 0.3)
    orch.track_sub_component("generation", "semantic_fallback", "degraded", 0.6)
    summary = orch.get_sub_component_summary()
    assert "visual_intelligence" in summary
    assert "semantic_fallback" in summary
    assert "generation:" in summary


def test_sub_component_in_degraded_stages():
    orch = make_orch()
    orch.stages["generation"] = type("SR", (), {
        "name": "generation", "status": "success",
        "confidence_multiplier": 1.0, "duration_ms": 100,
        "error": "", "skipped_reason": "",
    })()
    orch.track_sub_component("generation", "visual_intelligence", "failed", 0.3)
    degraded = orch.get_degraded_stages()
    gen_entry = [d for d in degraded if d["name"] == "generation"]
    assert len(gen_entry) == 1
    assert "sub_components" in gen_entry[0]
    assert gen_entry[0]["sub_components"].get("visual_intelligence") == "failed"


def test_sub_component_affects_infra_confidence():
    orch = make_orch()
    for name in ["text_extraction", "embedding", "retrieval", "generation"]:
        orch.stages[name] = type("SR", (), {
            "name": name, "status": "success",
            "confidence_multiplier": 1.0, "duration_ms": 100,
            "error": "", "skipped_reason": "",
        })()
    conf_before = orch.get_infra_confidence()
    orch.track_sub_component("generation", "visual_intelligence", "failed", 0.3)
    conf_after = orch.get_infra_confidence()
    assert conf_after < conf_before, "Sub-component failure should lower infra confidence"


# ─── 7. Cache Versioning Tests ──────────────────────────────────────────

def test_cache_version_stale_ignored():
    cache_clear()
    from app.rag.pipeline_orchestrator import CACHE_VERSION
    doc_hash = hashlib.md5(b"version_test").hexdigest()[:16]
    # Write a cache entry with wrong version
    import json
    path = os.path.join("cache", "pipeline", f"{doc_hash}_retrieval.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"_cache_version": "v0_stale", "_data": {"key": "old"}}, f)
    val = cache_get(doc_hash, "retrieval")
    assert val is None, "Stale cache should be ignored"


def test_cache_version_current_accepted():
    cache_clear()
    from app.rag.pipeline_orchestrator import CACHE_VERSION
    doc_hash = hashlib.md5(b"version_test2").hexdigest()[:16]
    import json
    path = os.path.join("cache", "pipeline", f"{doc_hash}_retrieval.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"_cache_version": CACHE_VERSION, "_data": {"key": "current"}}, f)
    val = cache_get(doc_hash, "retrieval")
    assert val is not None
    assert val["key"] == "current"
    cache_clear(doc_hash)


# ─── 8. Metric Serializer Tests ─────────────────────────────────────────

def test_serialize_metric_string():
    from app.rag.metric_serializer import serialize_metric
    assert serialize_metric("₹9 Cr") == "₹9 Cr"
    assert serialize_metric("") == ""
    assert serialize_metric(42) == "42"
    assert serialize_metric(None) == ""


def test_serialize_metric_dict():
    from app.rag.metric_serializer import serialize_metric
    assert serialize_metric({"value": "₹9 Cr"}) == "₹9 Cr"
    assert serialize_metric({"display_value": "₹10 Cr", "value": "₹9 Cr"}) == "₹10 Cr"
    assert serialize_metric({"label": "Revenue"}) == "Revenue"


def test_serialize_metric_list():
    from app.rag.metric_serializer import serialize_metric
    result = serialize_metric([{"value": "₹9 Cr"}, {"value": "₹10 Cr"}])
    assert "₹9 Cr" in result
    assert "₹10 Cr" in result


def test_sanitize_financial_highlights():
    from app.rag.metric_serializer import sanitize_financial_highlights
    raw = {"revenue": {"value": "₹9 Cr"}, "orders": "100 units", "customers": None}
    clean = sanitize_financial_highlights(raw)
    assert isinstance(clean["revenue"], str)
    assert clean["revenue"] == "₹9 Cr"
    assert clean["orders"] == "100 units"
    assert clean["customers"] == ""


def test_sanitize_chart_data_empty():
    from app.rag.metric_serializer import sanitize_chart_data
    assert sanitize_chart_data({}) == {}
    assert sanitize_chart_data(None) == {}
    assert sanitize_chart_data("invalid") == {}


def test_sanitize_chart_data_valid():
    from app.rag.metric_serializer import sanitize_chart_data
    raw = {
        "revenue": {
            "type": "revenue_trend",
            "title": "Revenue",
            "data": [{"label": "FY24", "value": 100, "display": "₹100 Cr", "confidence": 0.9}],
            "display_unit": "INR",
            "calculated": {"cagr": 25},
            "chart_options": {"x_axis": "label", "y_axis": "value", "unit": "INR", "color_scheme": "revenue"},
        }
    }
    clean = sanitize_chart_data(raw)
    assert "revenue" in clean
    assert clean["revenue"]["data"][0]["value"] == 100.0
    assert clean["revenue"]["data"][0]["display"] == "₹100 Cr"


def test_sanitize_data_warnings():
    from app.rag.metric_serializer import sanitize_data_warnings
    raw = ["error 1", {"message": "error 2"}, 42]
    clean = sanitize_data_warnings(raw)
    assert isinstance(clean, list)
    assert all(isinstance(w, str) for w in clean)
    assert "error 1" in clean


# ─── 9. Chunk Prioritization Tests ──────────────────────────────────────

def test_prioritize_chunks_keeps_top_n():
    from app.rag.pipeline_orchestrator import prioritize_chunks
    chunks = [{"content": f"Page {i} content"} for i in range(50)]
    selected = prioritize_chunks(chunks, max_chunks=25)
    assert len(selected) == 25


def test_prioritize_chunks_p1_first():
    from app.rag.pipeline_orchestrator import prioritize_chunks
    chunks = [
        {"content": "Team background and founder experience"},
        {"content": "Revenue grew to ₹9 Cr with 80% margin"},
        {"content": "Market TAM of ₹45,000 Cr with SOM of ₹250 Cr"},
    ]
    selected = prioritize_chunks(chunks, max_chunks=3)
    # Financial chunks (revenue, TAM) should come first
    texts = [c["content"] for c in selected]
    assert any("Revenue" in t for t in texts[:2])
    assert any("TAM" in t for t in texts[:2])


def test_prioritize_chunks_empty():
    from app.rag.pipeline_orchestrator import prioritize_chunks
    assert prioritize_chunks([], max_chunks=10) == []


def test_prioritize_chunks_string_input():
    from app.rag.pipeline_orchestrator import prioritize_chunks
    chunks = ["This is a text chunk about revenue"]
    selected = prioritize_chunks(chunks, max_chunks=5)
    assert len(selected) == 1


# ─── 10. Retrieval Snapshot Tests ───────────────────────────────────────

def test_save_load_retrieval_snapshot():
    from app.rag.pipeline_orchestrator import save_retrieval_snapshot, load_retrieval_snapshot
    import tempfile, os
    doc_id = "test_snapshot_doc"
    chunks = [{"content": "revenue data", "metadata": {"section": "financials"}},
              {"content": "team info", "metadata": {"section": "team"}}]
    save_retrieval_snapshot(doc_id, chunks)
    loaded = load_retrieval_snapshot(doc_id)
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0]["content"] == "revenue data"
    assert loaded[0]["metadata"]["section"] == "financials"
    # Cleanup
    import shutil
    shutil.rmtree("cache/retrieval_snapshots", ignore_errors=True)


def test_load_retrieval_snapshot_missing():
    from app.rag.pipeline_orchestrator import load_retrieval_snapshot
    assert load_retrieval_snapshot("nonexistent_doc") is None


# ─── 11. Embedder Resilience Tests ──────────────────────────────────────

def test_embedder_cache_key_namespace():
    from app.rag.embedder import _cache_key
    key_a = _cache_key("hello", namespace="ns1")
    key_b = _cache_key("hello", namespace="ns2")
    assert key_a != key_b


def test_embedder_cache_key_no_namespace():
    from app.rag.embedder import _cache_key
    key = _cache_key("hello")
    assert ":" in key


# ─── 12. Financial Chart Classification Tests ──────────────────────────

def test_is_financial_chart_revenue():
    from app.rag.visual_intelligence import _is_financial_chart, ChartAnalysis
    chart = ChartAnalysis(page=1, chart_type="bar", title="Revenue Growth",
                          metrics=[], confidence=0.8, source="heuristic")
    assert _is_financial_chart(chart, "Financial Summary")


def test_is_financial_chart_non_financial():
    from app.rag.visual_intelligence import _is_financial_chart, ChartAnalysis
    chart = ChartAnalysis(page=1, chart_type="other", title="Company Logo",
                          metrics=[], confidence=0.8, source="heuristic")
    assert not _is_financial_chart(chart, "")


def test_is_financial_chart_roadmap_rejected():
    from app.rag.visual_intelligence import _is_financial_chart, ChartAnalysis
    chart = ChartAnalysis(page=1, chart_type="other", title="Product Roadmap 2026",
                          metrics=[], confidence=0.8, source="heuristic")
    assert not _is_financial_chart(chart, "Roadmap")


# ─── 13. BM25 Fallback Tests ────────────────────────────────────────────

def test_bm25_retriever_from_snapshot():
    """BM25Retriever works with snapshot content for fallback retrieval."""
    from app.rag.hybrid_retriever import BM25Retriever
    docs = [
        "revenue grew 50% to ₹9 Cr with 80% margin",
        "team has 25 engineers across 3 offices",
        "TAM of ₹45,000 Cr and SAM of ₹8,000 Cr",
    ]
    bm25 = BM25Retriever()
    bm25.index(docs)
    scores = bm25.get_scores("revenue margin")
    ranked = sorted(enumerate(scores), key=lambda x: -x[1])
    top = [docs[idx] for idx, _ in ranked[:2]]
    assert any("revenue" in d.lower() for d in top)
    assert bm25.get_scores("") is not None  # empty query doesn't crash


def test_bm25_retriever_empty_index():
    from app.rag.hybrid_retriever import BM25Retriever
    bm25 = BM25Retriever()
    bm25.index([])
    scores = bm25.get_scores("test query")
    assert scores is not None


if __name__ == "__main__":
    test_cache_set_get_roundtrip()
    print("OK: test_cache_set_get_roundtrip")
    test_cache_get_miss_returns_none()
    print("OK: test_cache_get_miss_returns_none")
    test_clear_by_doc_hash()
    print("OK: test_clear_by_doc_hash")
    test_clear_all()
    print("OK: test_clear_all")
    test_cacheable_stages_defined()
    print("OK: test_cacheable_stages_defined")
    test_orchestrator_cache_hit_tracked()
    print("OK: test_orchestrator_cache_hit_tracked")
    test_orchestrator_cache_miss_runs_fn()
    print("OK: test_orchestrator_cache_miss_runs_fn")
    test_orchestrator_cache_writes_after_success()
    print("OK: test_orchestrator_cache_writes_after_success")
    test_quality_gates_defined()
    print("OK: test_quality_gates_defined")
    test_quality_gate_skips_retrieval_when_embedding_failed()
    print("OK: test_quality_gate_skips_retrieval_when_embedding_failed")
    test_quality_gate_skips_retrieval_when_embedding_low_confidence()
    print("OK: test_quality_gate_skips_retrieval_when_embedding_low_confidence")
    test_quality_gate_allows_retrieval_when_embedding_ok()
    print("OK: test_quality_gate_allows_retrieval_when_embedding_ok")
    test_quality_gate_no_effect_when_prereq_not_run()
    print("OK: test_quality_gate_no_effect_when_prereq_not_run")
    test_quality_gate_skips_chain_on_critical_failure()
    print("OK: test_quality_gate_skips_chain_on_critical_failure")
    test_infra_confidence_all_success()
    print("OK: test_infra_confidence_all_success")
    test_infra_confidence_with_degraded()
    print("OK: test_infra_confidence_with_degraded")
    test_infra_confidence_with_failure()
    print("OK: test_infra_confidence_with_failure")
    test_infra_confidence_empty_stages()
    print("OK: test_infra_confidence_empty_stages")
    test_get_degraded_stages()
    print("OK: test_get_degraded_stages")
    test_complexity_scorer_fallback()
    print("OK: test_complexity_scorer_fallback")
    test_complexity_scorer_recommended_budget()
    print("OK: test_complexity_scorer_recommended_budget")
    test_complexity_summary()
    print("OK: test_complexity_summary")
    test_stage_summary()
    print("OK: test_stage_summary")
    test_quality_gate_nonexistent_stage_allowed()
    print("OK: test_quality_gate_nonexistent_stage_allowed")
    test_cache_clear_by_key()
    print("OK: test_cache_clear_by_key")
    test_cache_invalid_json_handled()
    print("OK: test_cache_invalid_json_handled")
    test_get_cache_hits_empty()
    print("OK: test_get_cache_hits_empty")
    print("\nAll 28 orchestrator tests passed")
