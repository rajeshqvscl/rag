"""
Pipeline Orchestrator — fault-isolated staged execution for the RAG pipeline.

Solves the architectural failure identified in Phase 1b:
  - No failure isolation (every stage blocks the next)
  - No degraded-state awareness (confidence doesn't reflect infra health)
  - No resource budgeting (large decks get same treatment as small ones)
  - No per-document caching (expensive ops recomputed every time)

Design:
  Each stage runs in isolation. Failures and timeouts are caught and
  recorded in a StageResult. The orchestrator tracks all stage results
  and computes an infrastructure confidence multiplier that gets
  combined with the semantic confidence from the validation engine.
"""

import hashlib
import io
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Chunk Prioritization ─────────────────────────────────────────────────

_CHUNK_PRIORITY_KEYWORDS = {
    1: ["revenue", "financial", "tam", "sam", "som", "funding", "valuation",
        "profit", "margin", "ebitda", "arr", "growth rate", "p&l",
        "balance sheet", "income statement", "cash flow"],
    2: ["market size", "competition", "traction", "customers", "orders",
        "pipeline", "milestone", "product", "solution", "technology"],
    3: ["problem", "pain point", "business model", "go-to-market",
        "team", "founder", "background", "award", "recognition"],
}


def prioritize_chunks(chunks: list, max_chunks: int = 25) -> list:
    """
    Prioritize chunks by financial relevance before embedding.
    Keeps top-N chunks sorted by priority (P1 > P2 > P3 > rest).
    """
    if not chunks:
        return []

    scored = []
    for c in chunks:
        content = c["content"] if isinstance(c, dict) else str(c)
        cl = content.lower()
        priority = 4  # lowest
        for p, keywords in _CHUNK_PRIORITY_KEYWORDS.items():
            if any(kw in cl for kw in keywords):
                priority = min(priority, p)
        # Bonus for table content
        if isinstance(c, dict) and c.get("metadata", {}).get("has_table"):
            priority = min(priority, 1)
        scored.append((priority, len(content), c))

    scored.sort(key=lambda x: (x[0], -x[1]))
    selected = [item[2] for item in scored[:max_chunks]]
    discarded = len(chunks) - len(selected)
    if discarded > 0:
        print(f"[ORCHESTRATOR] Prioritized {len(selected)}/{len(chunks)} chunks (discarded {discarded} low-priority)")
    return selected


# ── Retrieval Snapshot Cache ─────────────────────────────────────────────

_RETRIEVAL_SNAPSHOT_DIR = Path("cache/retrieval_snapshots")
_RETRIEVAL_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def save_retrieval_snapshot(doc_id: str, chunks: list):
    """Save chunks to disk so retrieval works without Pinecone."""
    try:
        path = _RETRIEVAL_SNAPSHOT_DIR / f"{doc_id}_chunks.json"
        payload = []
        for c in chunks:
            if isinstance(c, dict):
                payload.append({"content": c.get("content", ""), "metadata": c.get("metadata", {})})
            else:
                payload.append({"content": str(c), "metadata": {}})
        path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    except Exception as e:
        print(f"[SNAPSHOT] Save failed: {e}")


def load_retrieval_snapshot(doc_id: str) -> Optional[list]:
    """Load chunks from disk snapshot (for fallback when Pinecone unavailable)."""
    path = _RETRIEVAL_SNAPSHOT_DIR / f"{doc_id}_chunks.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[SNAPSHOT] Load failed: {e}")
    return None


# ── Caching ──────────────────────────────────────────────────────────────

_DOC_CACHE_DIR = Path("cache/pipeline")
_DOC_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache version — increment to invalidate all caches
CACHE_VERSION = "v5"


def _doc_cache_path(doc_hash: str, key: str) -> Path:
    return _DOC_CACHE_DIR / f"{doc_hash}_{key}.json"


def cache_get(doc_hash: str, key: str) -> Optional[Any]:
    path = _doc_cache_path(doc_hash, key)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("_cache_version") != CACHE_VERSION:
                return None  # stale cache, ignore
            return payload.get("_data", payload) if isinstance(payload, dict) else payload
        except Exception:
            return None
    return None


def cache_set(doc_hash: str, key: str, data: Any):
    try:
        path = _doc_cache_path(doc_hash, key)
        payload = {"_cache_version": CACHE_VERSION, "_data": data}
        path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    except Exception:
        pass


def cache_clear(doc_hash: str = None, key: str = None):
    """Clear pipeline cache entries. If doc_hash is None, clear ALL."""
    try:
        if doc_hash and key:
            p = _doc_cache_path(doc_hash, key)
            if p.exists():
                p.unlink()
        elif doc_hash:
            for p in _DOC_CACHE_DIR.glob(f"{doc_hash}_*.json"):
                p.unlink()
        else:
            for p in _DOC_CACHE_DIR.glob("*.json"):
                p.unlink()
    except Exception:
        pass


# ── Stage result dataclass ───────────────────────────────────────────────

@dataclass
class StageResult:
    name: str
    status: str  # "success", "degraded", "failed", "skipped"
    duration_ms: float = 0.0
    error: str = ""
    skipped_reason: str = ""
    confidence_multiplier: float = 1.0
    # 1.0 = full confidence, 0.7 = degraded but usable, 0.3 = barely usable, 0.0 = failed


# ── Deck complexity scorer ───────────────────────────────────────────────

@dataclass
class DeckComplexity:
    page_count: int
    estimated_charts: int
    estimated_tables: int
    total_text_chars: int
    text_density: float  # chars per page
    has_embedded_images: bool
    complexity_score: float  # 0.0–1.0 simple→complex
    recommended_budget: Dict[str, int] = field(default_factory=dict)


class DeckComplexityScorer:
    """Pre-scan PDF to estimate complexity before running the pipeline."""

    @classmethod
    def scan(cls, file_content: bytes, file_name: str) -> DeckComplexity:
        try:
            import fitz
            doc = fitz.open(stream=file_content, filetype="pdf")
            page_count = len(doc)

            total_chars = 0
            total_images = 0
            total_tables = 0

            for page in doc:
                text = page.get_text()
                total_chars += len(text)
                images = page.get_images(full=True)
                total_images += len(images)

            doc.close()

            # Quick pdfplumber table estimate
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    for p in pdf.pages:
                        tbls = p.find_tables()
                        total_tables += len(tbls)
            except Exception:
                pass

            text_density = total_chars / max(page_count, 1)
            has_images = total_images > 0

            # Complexity score: weighted combination
            page_score = min(page_count / 50, 1.0) * 0.3
            image_score = min(total_images / 30, 1.0) * 0.25
            table_score = min(total_tables / 20, 1.0) * 0.2
            density_score = min(text_density / 3000, 1.0) * 0.15
            density_penalty = 0.1 if text_density < 200 else 0  # low text = scanned = complex
            complexity = round(min(page_score + image_score + table_score + density_score + density_penalty, 1.0), 2)

            # Resource budget based on complexity
            if is_fast_mode():
                budget = {
                    "max_charts_to_analyze": 0,
                    "max_tables_to_process": 0,
                    "max_chunks": 15,
                    "retrieval_top_k": 4,
                    "max_retrieval_sections": 3,
                }
                print("[ORCHESTRATOR] Fast mode active: using minimized budget settings")
            else:
                budget = {
                    "max_charts_to_analyze": 30 if complexity < 0.5 else 15 if complexity < 0.7 else 8,
                    "max_tables_to_process": 20 if complexity < 0.5 else 10,
                    "max_chunks": 40 if complexity < 0.5 else 25,
                    "retrieval_top_k": 8 if complexity < 0.5 else 5,
                    "max_retrieval_sections": 7 if complexity < 0.5 else 5,
                }

            return DeckComplexity(
                page_count=page_count,
                estimated_charts=total_images,
                estimated_tables=total_tables,
                total_text_chars=total_chars,
                text_density=text_density,
                has_embedded_images=has_images,
                complexity_score=complexity,
                recommended_budget=budget,
            )

        except Exception as e:
            if is_fast_mode():
                recommended_budget = {"max_charts_to_analyze": 0, "max_tables_to_process": 0,
                                      "max_chunks": 15, "retrieval_top_k": 4, "max_retrieval_sections": 3}
            else:
                recommended_budget = {"max_charts_to_analyze": 10, "max_tables_to_process": 10,
                                      "max_chunks": 30, "retrieval_top_k": 6, "max_retrieval_sections": 5}
            return DeckComplexity(
                page_count=0, estimated_charts=0, estimated_tables=0,
                total_text_chars=0, text_density=0, has_embedded_images=False,
                complexity_score=0.5,  # neutral fallback
                recommended_budget=recommended_budget,
            )


# ── Pipeline orchestrator ────────────────────────────────────────────────

_STAGE_PRIORITY = {
    "text_extraction": 1,
    "domain_detection": 1,
    "triage": 1,
    "chunking": 1,
    "embedding": 1,
    "retrieval": 1,
    "generation": 2,
    "scoring": 2,
    "strategy": 2,
}

# Stages whose results can be cached per-document hash across runs
# Generation NOT cached — outputs go stale (LLM updates, schema changes)
_CACHEABLE_STAGES = {"retrieval"}

# Quality gates: before running a stage, check if prerequisite stage quality is sufficient
#   (stage_name) -> (prerequisite, min_confidence_multiplier, action)
_QUALITY_GATES: Dict[str, tuple] = {
    "retrieval":  ("embedding",        0.3, "skip"),       # skip retrieval if embedding badly degraded
    "generation": ("retrieval",        0.3, "degrade"),    # mark generation degraded if retrieval confidence < 0.3
    "scoring":    ("generation",       None, "degrade"),   # always degrade scoring if generation was degraded/failed
    "strategy":   ("generation",       None, "degrade"),   # always degrade strategy if generation was degraded/failed
}

# Sub-components within stages that can fail independently
_SUB_COMPONENTS = {
    "generation": ["llm_extraction", "visual_intelligence", "semantic_fallback",
                   "ontology_reject", "financial_candidate", "canonical_build"],
    "retrieval":  ["vector_search", "keyword_fallback", "reranking"],
}


class PipelineOrchestrator:
    """
    Orchestrates the RAG pipeline with stage isolation, caching, and
    degraded-state tracking.

    Usage:
        orch = PipelineOrchestrator(file_content, file_name)
        result = orch.run()
        # result includes "_pipeline_stages" with per-stage diagnostics
    """

    STAGE_TIMEOUTS = {
        "text_extraction": 60,
        "domain_detection": 5,
        "triage": 15,
        "chunking": 10,
        "embedding": 30,
        "retrieval": 30,
        "generation": 120,
        "scoring": 10,
        "strategy": 5,
    }

    def __init__(self, file_content: bytes, file_name: str):
        self.file_content = file_content
        self.file_name = file_name
        self.doc_hash = hashlib.md5(file_content).hexdigest()[:16]
        self.stages: Dict[str, StageResult] = {}
        self.complexity: DeckComplexity = DeckComplexityScorer.scan(file_content, file_name)
        self._aborted = False
        self._cache_hits: set = set()
        self._sub_components: Dict[str, Dict[str, StageResult]] = {}

    def run_stage(self, name: str, fn: Callable, *args, **kwargs) -> Any:
        """
        Execute a pipeline stage with isolation, caching, and quality gates.
        ALL telemetry/logging is non-blocking — never crashes the pipeline.
        Returns the result if successful, None if failed/skipped.
        Records status, duration, error in self.stages.
        """
        try:
            if self._aborted:
                self._record_skipped(name, "pipeline aborted due to prior critical failure")
                return None

            # ── Quality gate check ──────────────────────────────────────
            gate_ok, reason = self._check_quality_gate(name)
            if not gate_ok:
                self._record_skipped(name, f"quality gate: {reason}")
                return None

            # ── Cache check (for cacheable stages) ──────────────────────
            if name in _CACHEABLE_STAGES:
                try:
                    cached = cache_get(self.doc_hash, name)
                    if cached is not None:
                        self.stages[name] = StageResult(
                            name=name, status="success",
                            duration_ms=0, confidence_multiplier=1.0,
                        )
                        self._cache_hits.add(name)
                        return cached
                except Exception:
                    pass  # cache failure is non-blocking

            start = time.time()
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                error_msg = f"{type(e).__name__}: {e}"
                self._record_failure(name, elapsed_ms, error_msg)
                return None

            elapsed_ms = (time.time() - start) * 1000
            degraded = self._compute_degraded(name, elapsed_ms)

            try:
                if degraded:
                    self.stages[name] = StageResult(
                        name=name, status="degraded",
                        duration_ms=round(elapsed_ms, 1),
                        confidence_multiplier=0.7,
                        error=f"completed but degraded (took {elapsed_ms:.0f}ms)",
                    )
                else:
                    self.stages[name] = StageResult(
                        name=name, status="success",
                        duration_ms=round(elapsed_ms, 1),
                        confidence_multiplier=1.0,
                    )
            except Exception:
                pass  # telemetry is non-blocking

            # ── Cache write (cacheable stages only) ─────────────────────
            if name in _CACHEABLE_STAGES and result is not None:
                try:
                    cache_set(self.doc_hash, name, result)
                except Exception:
                    pass  # cache write failure is non-blocking

            return result

        except Exception as e:
            # Absolute outer catch — NO exception escapes run_stage
            error_msg = f"{type(e).__name__}: {e}"
            self._record_failure(name, 0, error_msg)
            return None

    def _record_skipped(self, name: str, reason: str):
        try:
            self.stages[name] = StageResult(
                name=name, status="skipped",
                skipped_reason=reason,
                confidence_multiplier=0.0,
            )
        except Exception:
            pass

    def _record_failure(self, name: str, elapsed_ms: float, error_msg: str):
        try:
            is_critical = _STAGE_PRIORITY.get(name, 1) == 1
            self.stages[name] = StageResult(
                name=name, status="failed",
                duration_ms=round(elapsed_ms, 1),
                error=error_msg,
                confidence_multiplier=0.0 if is_critical else 0.3,
            )
            if is_critical:
                self._aborted = True
        except Exception:
            pass

    def _check_quality_gate(self, name: str) -> tuple:
        """
        Check quality gate for a stage before execution.
        Returns (ok: bool, reason: str).
        """
        if name not in _QUALITY_GATES:
            return True, ""

        prereq, min_conf, action = _QUALITY_GATES[name]
        if prereq not in self.stages:
            return True, ""  # prerequisite hasn't run yet, allow

        prereq_stage = self.stages[prereq]
        if prereq_stage.status == "failed":
            return (False, f"prerequisite '{prereq}' failed") if action == "skip" else (True, "degrading")

        if min_conf is not None and prereq_stage.confidence_multiplier < min_conf:
            return (False, f"prerequisite '{prereq}' confidence {prereq_stage.confidence_multiplier} < {min_conf}") if action == "skip" else (True, "degrading")

        return True, ""

    def _compute_degraded(self, name: str, elapsed_ms: float) -> bool:
        timeout = self.STAGE_TIMEOUTS.get(name, 30) * 1000
        if elapsed_ms > timeout * 0.8:
            return True
        return False

    def add_external_stage(self, name: str, confidence_multiplier: float,
                           status: str = "unknown", error: str = "",
                           skipped_reason: str = ""):
        """Add or update a stage result from outside the orchestrator (e.g., visual analysis, chart parsing)."""
        self.stages[name] = StageResult(
            name=name,
            status=status,
            confidence_multiplier=confidence_multiplier,
            error=error,
            skipped_reason=skipped_reason,
        )

    def get_infra_confidence(self) -> float:
        """
        Compute overall infrastructure confidence based on stage health.
        Includes sub-component failures (visual intelligence, reranking, etc.).
        Returns 0.0–1.0 multiplier that gets combined with semantic confidence.
        """
        if not self.stages:
            return 1.0

        weights = {
            "text_extraction": 0.20,
            "embedding": 0.15,
            "retrieval": 0.15,
            "generation": 0.15,
            "chunking": 0.05,
            "domain_detection": 0.02,
            "triage": 0.03,
            "scoring": 0.03,
            "strategy": 0.02,
        }

        # Sub-component penalty: each failed sub-component reduces parent weight by 30%
        sub_component_mult = 1.0
        for stage, subs in self._sub_components.items():
            failed_count = sum(1 for r in subs.values() if r.status == "failed")
            degraded_count = sum(1 for r in subs.values() if r.status == "degraded")
            total = max(len(subs), 1)
            health_ratio = (total - failed_count - 0.5 * degraded_count) / total
            sub_component_mult = min(sub_component_mult, health_ratio)

        score = 0.0
        total_weight = 0.0
        for name, stage in self.stages.items():
            w = weights.get(name, 0.05)
            # Apply sub-component penalty to parent stage weight
            if name in self._sub_components:
                subs = self._sub_components[name]
                failed_count = sum(1 for r in subs.values() if r.status == "failed")
                degraded_count = sum(1 for r in subs.values() if r.status == "degraded")
                if failed_count > 0:
                    w *= 0.7
                if degraded_count > 0:
                    w *= 0.85
            total_weight += w
            score += w * stage.confidence_multiplier

        if total_weight == 0:
            return 1.0
        base = score / total_weight
        final = base * (0.8 + 0.2 * sub_component_mult)
        return round(min(final, 1.0), 2)

    def get_retrieval_confidence(self) -> float:
        """Compute retrieval-specific confidence based on chunk relevance."""
        if "retrieval" not in self.stages:
            return 0.8
        stage = self.stages["retrieval"]
        if stage.status == "failed":
            return 0.2
        elif stage.status == "degraded":
            return 0.5
        return 0.85

    def get_extraction_confidence(self) -> float:
        """Compute extraction-specific confidence based on text/visual extraction."""
        text_stage = self.stages.get("text_extraction")
        if not text_stage:
            return 0.8

        if text_stage.status == "failed":
            return 0.3
        elif text_stage.status == "degraded":
            return 0.6

        base = text_stage.confidence_multiplier
        if "visual_analysis" in self._sub_components.get("text_extraction", {}):
            visual = self._sub_components["text_extraction"].get("visual_analysis", None)
            if visual and visual.status in ("failed", "degraded"):
                base *= 0.7
        return round(min(base, 1.0), 2)

    def get_financial_confidence(self) -> float:
        """Compute financial metric extraction confidence."""
        generation_stage = self.stages.get("generation")
        if not generation_stage:
            return 0.6

        if generation_stage.status == "failed":
            return 0.2
        elif generation_stage.status == "degraded":
            return 0.5

        sub_comp = self._sub_components.get("generation", {})
        has_ontology = sub_comp.get("ontology_reject", None)
        has_extraction = sub_comp.get("llm_extraction", None)

        score = 0.7
        if has_ontology and has_ontology.status == "degraded":
            score -= 0.2
        if has_extraction:
            if has_extraction.status == "degraded":
                score -= 0.15
            elif has_extraction.status == "failed":
                score -= 0.3

        return round(max(score, 0.1), 2)

    def get_all_confidence_layers(self) -> Dict[str, float]:
        """Get all confidence layers as a dictionary."""
        return {
            "infra": self.get_infra_confidence(),
            "retrieval": self.get_retrieval_confidence(),
            "extraction": self.get_extraction_confidence(),
            "financial": self.get_financial_confidence(),
        }

    def get_degraded_stages(self) -> List[Dict]:
        """Return list of degraded/failed stages for diagnostics."""
        result = []
        for name, stage in self.stages.items():
            if stage.status in ("degraded", "failed", "skipped"):
                entry = {
                    "name": name,
                    "status": stage.status,
                    "error": stage.error,
                    "duration_ms": stage.duration_ms,
                }
                # Include sub-component failures for this stage
                if name in self._sub_components:
                    sub_statuses = {}
                    for sname, sresult in self._sub_components[name].items():
                        if sresult.status in ("degraded", "failed"):
                            sub_statuses[sname] = sresult.status
                    if sub_statuses:
                        entry["sub_components"] = sub_statuses
                result.append(entry)
        return result

    def get_cache_hits(self) -> list:
        return sorted(self._cache_hits)

    def track_sub_component(self, stage: str, sub: str, status: str,
                            conf_mult: float = 1.0, error: str = ""):
        """Track a sub-component failure within a stage."""
        if stage not in self._sub_components:
            self._sub_components[stage] = {}
        self._sub_components[stage][sub] = StageResult(
            name=sub, status=status, error=error,
            confidence_multiplier=conf_mult,
        )
        # Update parent stage confidence based on sub-component health
        if status in ("failed", "degraded") and stage in self.stages:
            parent = self.stages[stage]
            if parent.status == "success":
                parent.status = "degraded"
                parent.error = parent.error or f"sub-component '{sub}' {status}"
                parent.confidence_multiplier = min(parent.confidence_multiplier, conf_mult)

    def get_sub_component_summary(self) -> str:
        parts = []
        for stage, subs in self._sub_components.items():
            failed = [s for s, r in subs.items() if r.status == "failed"]
            degraded = [s for s, r in subs.items() if r.status == "degraded"]
            if failed:
                parts.append(f"{stage}:{','.join(failed)}✗")
            if degraded:
                parts.append(f"{stage}:{','.join(degraded)}~")
        return "; ".join(parts) if parts else "all_ok"

    def get_complexity_summary(self) -> str:
        c = self.complexity
        return (f"Deck: {c.page_count}p | {c.estimated_charts} charts | "
                f"{c.estimated_tables} tables | {c.total_text_chars} chars | "
                f"complexity={c.complexity_score}")

    def get_stage_summary(self) -> str:
        parts = []
        for name in ["text_extraction", "domain_detection", "triage", "chunking",
                       "embedding", "retrieval", "generation", "scoring", "strategy"]:
            stage = self.stages.get(name)
            if stage:
                icon = {"success": "OK", "degraded": "~", "failed": "X", "skipped": "-"}
                sub_info = ""
                if name in self._sub_components:
                    failing = [s for s, r in self._sub_components[name].items()
                               if r.status in ("degraded", "failed")]
                    if failing:
                        sub_info = f"[{','.join(failing)}]"
                parts.append(f"{icon.get(stage.status, '?')}{name}({stage.duration_ms:.0f}ms){sub_info}")
        return " | ".join(parts)


import threading
_thread_local = threading.local()

def set_fast_mode(enabled: bool):
    _thread_local.fast_mode = enabled
    print(f"[ORCHESTRATOR] Thread-local FAST_MODE set to: {enabled}")

def is_fast_mode() -> bool:
    return getattr(_thread_local, "fast_mode", False)


# ── Main pipeline entry point ────────────────────────────────────────────

def run_pipeline(file_content: bytes, file_name: str) -> Dict:
    """
    Full pipeline with stage isolation, caching, and degraded-state tracking.
    Returns the same result dict as process_email() in email_processor.py,
    plus additional `_pipeline_stages` and `_infra_confidence` keys.

    This is the drop-in replacement for email_processor.py::process_email().
    """
    orch = PipelineOrchestrator(file_content, file_name)
    print(f"[ORCHESTRATOR] {orch.get_complexity_summary()}")
    print(f"[ORCHESTRATOR] Budget: {orch.complexity.recommended_budget}")

    # ── Stage 1: Text Extraction ────────────────────────────────────
    from app.rag.loader import load_pdf as _load_pdf
    load_result = orch.run_stage("text_extraction", _load_pdf, file_content)

    full_text, pages = "", []
    if load_result and isinstance(load_result, tuple):
        full_text, pages = load_result
    elif load_result and isinstance(load_result, dict):
        full_text = load_result.get("full_text", "")
        pages = load_result.get("pages", [])

    if not full_text.strip():
        print("[ORCHESTRATOR] Aborting — no extractable text")
        return _abort_result(orch, "No text could be extracted from the PDF.")

    # ── Apply quality-driven budget reduction if text extraction degraded ──
    tex_stage = orch.stages.get("text_extraction")
    if tex_stage and tex_stage.confidence_multiplier < 0.7:
        budget = orch.complexity.recommended_budget
        budget["max_charts_to_analyze"] = min(budget.get("max_charts_to_analyze", 10), 5)
        budget["max_chunks"] = min(budget.get("max_chunks", 25), 15)
        budget["retrieval_top_k"] = max(budget.get("retrieval_top_k", 5) - 2, 3)
        print(f"[ORCHESTRATOR] Reduced budgets due to degraded text extraction "
              f"(confidence={tex_stage.confidence_multiplier})")

    # ── Stage 2: Domain Detection ────────────────────────────────────
    from app.utils.text_utils import safe_lower

    def _detect_domain(text):
        t = safe_lower(text[:15000])
        counts = {
            "hrtech": sum(1 for k in ["hr", "hiring", "recruitment", "recruiter", "ats", "workforce", "staffing", "onboarding", "bgv", "sourcing", "verification"] if k in t),
            "health": sum(1 for k in ["lab", "diagnostic", "health", "clinical", "patient", "medical", "healthcare", "pharma"] if k in t),
            "agri": sum(1 for k in ["agri", "farm", "rural", "crop", "agritech", "fertilizer", "tractor"] if k in t),
            "defense": sum(1 for k in ["defence", "defense", "military", "tactical", "drdo", "idel", "navy", "army", "airforce"] if k in t),
            "saas": sum(1 for k in ["saas", "software", "subscription", "cloud", "platform", "b2b"] if k in t),
            "climatetech": sum(1 for k in ["climate", "carbon", "emission", "sustainability", "esg", "green", "mitigation"] if k in t),
            "renewable_energy": sum(1 for k in ["solar", "wind", "renewable", "energy", "grid", "battery", "infra", "ev"] if k in t),
            "marketplace": sum(1 for k in ["marketplace", "platform", "connect", "buyers", "sellers", "commission", "gmv", "matchmaking"] if k in t),
            "fintech": sum(1 for k in ["fintech", "payment", "banking", "lending", "credit", "finance", "insurance", "transaction"] if k in t),
        }
        
        total = sum(counts.values())
        if total == 0:
            return [("General", 1.0)]
            
        scored = [(dom, round(count / total, 2)) for dom, count in counts.items() if count > 0]
        scored.sort(key=lambda x: -x[1])
        return scored

    domain_list = orch.run_stage("domain_detection", _detect_domain, full_text) or [("General", 1.0)]
    domain = domain_list[0][0] if isinstance(domain_list, list) and domain_list else "General"
    print(f"[ORCHESTRATOR] Multi-Label Domains detected: {domain_list} (Primary: {domain})")

    # ── Stage 3: Triage ──────────────────────────────────────────────
    from app.agents.triage_agent import triage_document

    triage = orch.run_stage("triage", triage_document, full_text[:4000])
    if triage is None:
        triage = {"type": "investor", "intent": "neutral", "company": "Unknown", "signals": []}

    doc_type = triage.get("type", "investor")
    intent = triage.get("intent", "neutral")
    
    from app.rag.company_resolver import CompanyIdentityResolver
    raw_company = triage.get("company", "Unknown")
    company = CompanyIdentityResolver.resolve(
        llm_name=raw_company,
        first_page_text=full_text[:4000],
        filename=file_name
    ) or raw_company
    
    signals = triage.get("signals", [])

    if doc_type == "client" and len(full_text) > 300:
        doc_type = "investor"

    if doc_type == "client":
        from app.agents.strategy_agent import generate_strategy
        strategy = generate_strategy({"intent": intent, "confidence": 1.0, "signals": signals}, full_text[:2000])
        return {
            "type": "client", "company": company,
            "intent": {"intent": intent, "confidence": 1.0, "signals": signals},
            "strategy": strategy, "query_type": "Business Inquiry", "urgency": "Standard",
            "email": "Hi, thanks for reaching out. We have received your inquiry and will get back to you shortly.",
            "status": "completed",
            "_pipeline_stages": {n: vars(s) for n, s in orch.stages.items()},
            "_infra_confidence": orch.get_infra_confidence(),
        }

    # ── Stage 4: Chunking ────────────────────────────────────────────
    from app.rag.loader import chunk_text as _chunk_text

    chunks = orch.run_stage("chunking", _chunk_text, pages) or []
    if not chunks:
        print("[ORCHESTRATOR] Aborting — no chunks after chunking")
        return _abort_result(orch, "Could not chunk the extracted text.")

    file_name_hash = hashlib.md5(file_name.encode("utf-8")).hexdigest()[:12]
    from app.rag.namespace_registry import get_canonical_namespace, normalize_namespace
    namespace = get_canonical_namespace(doc_id=file_name_hash, file_name=file_name)
    namespace = normalize_namespace(namespace)
    doc_id = file_name_hash

    # ── Dynamic Retrieval Depth based on complexity ──────────────────────
    page_count = len(pages) if pages else 0
    if page_count < 10:
        dynamic_top_k = 5
    elif page_count < 20:
        dynamic_top_k = 8
    elif page_count < 40:
        dynamic_top_k = 12
    else:
        dynamic_top_k = 15
    print(f"[ORCHESTRATOR] Dynamic retrieval: {page_count} pages -> top_k={dynamic_top_k}")

    # ── Stage 5: Embedding (with chunk prioritization) ────────────────
    from app.rag.embedder import embed_text
    from app.rag.vector_store import store_embeddings

    budget = orch.complexity.recommended_budget
    embedding_failed = False

    # Prioritize chunks: drop low-priority chunks before embedding
    max_embed_chunks = budget.get("max_chunks", 25)
    chunks_prioritized = prioritize_chunks(chunks, max_chunks=max_embed_chunks)
    if not chunks_prioritized:
        chunks_prioritized = chunks[:max_embed_chunks]  # safe fallback

    # Save retrieval snapshot BEFORE embedding (BM25 fallback uses this)
    save_retrieval_snapshot(doc_id, chunks_prioritized)

    # Metrics tracking
    try:
        from app.monitoring.metrics import MetricsCollector
        _metrics = MetricsCollector()
        _metrics.increment("pdf_processing", tags={"stage": "embedding", "doc_id": doc_id})
    except Exception:
        pass  # Metrics are optional

    embed_arg = [c["content"] if isinstance(c, dict) else c for c in chunks_prioritized]

    def _embed_and_store():
        emb = embed_text(embed_arg, namespace=namespace or "default")
        try:
            store_embeddings(chunks_prioritized, emb, namespace=namespace, doc_id=doc_id, domain=domain)
        except Exception as se:
            print(f"[ORCHESTRATOR] Store embeddings failed (non-critical): {se}")
        return emb

    embed_result = orch.run_stage("embedding", _embed_and_store)
    if embed_result is None:
        embedding_failed = True

    # ── Stage 6: Retrieval (with BM25 fallback) ──────────────────────
    from app.rag.retriever import retrieve

    def _bm25_fallback(doc_id_local: str, query: str, top_k: int) -> list:
        """Fallback retrieval using BM25 from local snapshot."""
        try:
            snapshot = load_retrieval_snapshot(doc_id_local)
            if not snapshot:
                return []
            from app.rag.hybrid_retriever import BM25Retriever
            bm25 = BM25Retriever()
            docs = [c["content"] if isinstance(c, dict) else str(c) for c in snapshot]
            bm25.index(docs)
            scores = bm25.get_scores(query)
            ranked = sorted(enumerate(scores), key=lambda x: -x[1])
            results = []
            for idx, score in ranked[:top_k]:
                if score > 0:
                    c = snapshot[idx]
                    content = c["content"] if isinstance(c, dict) else str(c)
                    results.append(content)
            print(f"[BM25 FALLBACK] Retrieved {len(results)} chunks for '{query[:40]}...'")
            return results
        except Exception as e:
            print(f"[BM25 FALLBACK] Error: {e}")
            return []

    # ── Retrieval Sections with Per-Section Limits ─────────────────────────────
    SECTION_LIMITS = {
        "financial": 8,
        "market": 6,
        "business": 6,
        "leadership": 5,
        "traction": 6,
        "competition": 4,
    }

    sections_config = {
        "financial": ("revenue ARR sales traction orders funding valuation growth profit margin actuals projected invoiced PO grant pipeline",
                      SECTION_LIMITS["financial"]),
        "business": ("product technology platform AI solution features GTM go-to-market business model IPUSP differentiation",
                     SECTION_LIMITS["business"]),
        "market": ("TAM SAM SOM market size opportunity growth competition differentiation defence defense",
                   SECTION_LIMITS["market"]),
        "leadership": ("founder CEO team IIT MDI experience background expertise leadership founders defense procurement advisors",
                       SECTION_LIMITS["leadership"]),
    }

    traction_keywords = "customers growth milestones traction adoption orders bookings pipeline expected"
    sections_config["traction"] = (traction_keywords, SECTION_LIMITS.get("traction", 6))

    competition_keywords = "competition competitor moat differentiation advantage naukri linkedin other players market share"
    sections_config["competition"] = (competition_keywords, SECTION_LIMITS.get("competition", 4))

    import threading
    _retrieval_lock = threading.Lock()

    def _run_retrieval():
        result = {}
        # Try Pinecone first — process in batches of 2 to avoid rate limits
        if not embedding_failed:
            section_list = list(sections_config.items())
            max_concurrent = min(budget.get("max_retrieval_sections", 5), 2)
            for batch_start in range(0, len(section_list), max_concurrent):
                batch = section_list[batch_start:batch_start + max_concurrent]
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                    future_map = {}
                    for section, (query, top_k) in batch:
                        future = executor.submit(retrieve, query, namespace=namespace,
                                                 section=section, doc_id=doc_id, top_k=top_k)
                        future_map[future] = section
                    for future in concurrent.futures.as_completed(future_map):
                        section = future_map[future]
                        try:
                            section_chunks = future.result()
                            if section_chunks:
                                with _retrieval_lock:
                                    result[section] = section_chunks
                        except Exception as e:
                            print(f"[RETRIEVAL] Section '{section}' error: {e}")

        # If Pinecone returned nothing, try BM25 from snapshot
        if not result or sum(len(v) for v in result.values()) == 0:
            print(f"[RETRIEVAL] Pinecone returned empty — trying BM25 fallback")
            for section, (query, top_k) in sections_config.items():
                try:
                    bm25_chunks = _bm25_fallback(doc_id, query, top_k)
                    if bm25_chunks:
                        result[section] = bm25_chunks
                except Exception as e:
                    print(f"[RETRIEVAL] BM25 fallback error for '{section}': {e}")

        # Final fallback: keyword matching on raw chunks
        if not result or sum(len(v) for v in result.values()) == 0:
            print(f"[RETRIEVAL] BM25 also empty — using keyword fallback")
            for section, (query, top_k) in sections_config.items():
                query_lower = query.lower()
                matched = []
                for c in chunks_prioritized:
                    content = c["content"] if isinstance(c, dict) else str(c)
                    meta_section = c.get("metadata", {}).get("section", "") if isinstance(c, dict) else ""
                    score = sum(1 for kw in query_lower.split() if kw in content.lower())
                    if meta_section == section:
                        score += 3
                    if score >= 2:
                        matched.append((score, content))
                matched.sort(key=lambda x: -x[0])
                selected = [m[1] for m in matched[:top_k]]
                if selected:
                    result[section] = selected
        return result

    import concurrent.futures
    chunks_by_section = orch.run_stage("retrieval", _run_retrieval) or {}

    total_retrieved = sum(len(v) for v in chunks_by_section.values())
    print(f"[ORCHESTRATOR] Retrieved {total_retrieved} chunks across {len(chunks_by_section)} sections")
    
    # Metrics: retrieval complete
    try:
        from app.monitoring.metrics import MetricsCollector
        _metrics.increment("retrieval_calls", tags={"doc_id": doc_id, "chunks": total_retrieved})
    except Exception:
        pass

    # ── Stage 7: Generation ──────────────────────────────────────────
    from app.rag.generator import generate_all

    result = orch.run_stage("generation", generate_all,
                            chunks_by_section, intent, company, domain=domain)
    
    # Metrics: generation complete
    try:
        from app.monitoring.metrics import MetricsCollector
        _metrics.increment("llm_calls", tags={"doc_id": doc_id})
    except Exception:
        pass
    
    if result is None:
        result = {
            "summary": "Analysis completed with errors",
            "email": f"Hi,\n\nThanks for your interest in {company}.",
            "key_signal": "N/A",
            "rag_status": "error",
            "intent": {"intent": "neutral", "confidence": 0, "signals": []},
            "strategy": {"next_step": "Retry analysis", "reasoning": "Generation failed", "priority": "Low"},
            "score": 0,
            "verdict": "Unknown",
            "deal_status": "Unknown",
            "confidence": 0,
            "financial_highlights": {},
            "confidence_by_section": {},
            "data_warnings": ["Generation stage failed"],
            "canonical_metrics": {},
            "chart_data": {},
        }

    # ── Post-Generation: Track visual analysis & chart parsing confidence ──
    if result:
        # Fallback chart exporter from canonical metrics if visual parsing fails or is empty
        _chart_data = result.get("chart_data", {})
        if not _chart_data or all(not v for v in _chart_data.values()):
            from app.rag.chart_exporter import export_chart_data_from_canonical
            _canon = result.get("canonical_metrics", {})
            if _canon:
                fallback_charts = export_chart_data_from_canonical(_canon)
                if fallback_charts:
                    result["chart_data"] = fallback_charts
                    print(f"[ORCHESTRATOR] Successfully generated {len(fallback_charts)} fallback charts from canonical metrics!")

        visual_conf = result.get("_visual_confidence", None)
        if visual_conf is not None:
            if visual_conf >= 0.5:
                orch.add_external_stage("visual_analysis", visual_conf, "success")
            else:
                orch.add_external_stage("visual_analysis", visual_conf, "degraded",
                                        error=f"visual confidence {visual_conf}")
            print(f"[ORCHESTRATOR] Visual analysis confidence: {visual_conf}")
        else:
            orch.add_external_stage("visual_analysis", 0.0, "skipped",
                                    skipped_reason="no visual analysis data in generator output")
            print(f"[ORCHESTRATOR] Visual analysis: not tracked in generator output")

        chart_conf = result.get("_chart_confidence", None)
        if chart_conf is not None:
            orch.add_external_stage("chart_parsing", chart_conf, "success")
            print(f"[ORCHESTRATOR] Chart parsing confidence: {chart_conf}")
        else:
            has_chart_data = bool(result.get("chart_data"))
            if has_chart_data:
                orch.add_external_stage("chart_parsing", 0.7, "degraded",
                                        error="chart data present but confidence not reported")
            else:
                orch.add_external_stage("chart_parsing", 0.0, "skipped",
                                        skipped_reason="no chart data in result")

    # ── Track sub-component failures from generation result ─────────────
    if result:
        _canon = result.get("canonical_metrics", {})
        _chart_data = result.get("chart_data", {})
        _warnings = result.get("data_warnings", [])

        # Visual intelligence health
        if _chart_data and len(_chart_data) == 0:
            # Has canonical metrics but no chart data — visual likely failed
            if any(True for v in _canon.values() if isinstance(v, dict) and v.get("normalized_value", 0) > 0):
                orch.track_sub_component("generation", "visual_intelligence", "failed", 0.3)

        # LLM extraction quality
        field_conf = result.get("field_confidence", {})
        if field_conf:
            avg_conf = sum(field_conf.values()) / max(len(field_conf), 1)
            if avg_conf < 0.3:
                orch.track_sub_component("generation", "llm_extraction", "degraded", 0.5)
            elif avg_conf < 0.5:
                orch.track_sub_component("generation", "llm_extraction", "degraded", 0.7)

        # Ontology violations
        ontology_warnings = [w for w in _warnings if "ontology" in str(w).lower() or "reject" in str(w).lower()]
        if ontology_warnings:
            orch.track_sub_component("generation", "ontology_reject", "degraded", 0.7,
                                     error=f"{len(ontology_warnings)} violations")

        # Semantic fallback
        if result.get("key_signal", "") in ("N/A", "", "Insufficient data to determine a strong investment signal."):
            if result.get("rag_status") == "success":
                orch.track_sub_component("generation", "semantic_fallback", "degraded", 0.6)

    # ── Stage 8: Scoring ─────────────────────────────────────────────
    def _score(result_data):
        summary_text = result_data.get("summary", "")
        summary_lower = summary_text.lower()

        has_revenue = any(x in summary_lower for x in ["revenue", "\u20b9", "cr", "lakh", "$", "inr"]) \
            and "not" not in summary_lower[max(0, summary_lower.find("revenue") - 10):summary_lower.find("revenue") + 10] \
            if "revenue" in summary_lower else any(x in summary_lower for x in ["revenue", "\u20b9", "cr", "lakh", "$", "inr"])

        orders_pos = summary_lower.find("orders")
        has_orders = False
        if orders_pos != -1:
            context = summary_lower[max(0, orders_pos - 20):orders_pos + 30]
            has_orders = "not" not in context and "unknown" not in context
        else:
            has_orders = "booking" in summary_lower

        has_growth = ("growth" in summary_lower or "yoy" in summary_lower) and "not provided" not in summary_lower
        has_margin = "margin" in summary_lower and "not" not in summary_lower[max(0, summary_lower.find("margin") - 10):summary_lower.find("margin") + 20] if "margin" in summary_lower else "margin" in summary_lower
        has_pipeline = "pipeline" in summary_lower and "not" not in summary_lower
        has_clients = ("labs" in summary_lower or "clients" in summary_lower) and "not" not in summary_lower[max(0, summary_lower.find("labs") - 10):summary_lower.find("labs") + 20] if "labs" in summary_lower else ("labs" in summary_lower or "clients" in summary_lower)

        data_points = sum([has_revenue, has_orders, has_growth, has_margin, has_pipeline, has_clients])

        score = 50
        if has_revenue:
            score += 15
        if has_orders:
            score += 8
        if has_growth:
            score += 10
        if has_margin:
            score += 7
        if has_pipeline:
            score += 5
        if has_clients:
            score += 5

        missing_data = []
        if "cac" in summary_lower and ("not" in summary_lower or "unknown" in summary_lower or "not available" in summary_lower or "not provided" in summary_lower):
            missing_data.append("CAC")
        if "clv" in summary_lower and ("not" in summary_lower or "unknown" in summary_lower or "not available" in summary_lower or "not provided" in summary_lower):
            missing_data.append("CLV")
        if "retention" in summary_lower and ("not" in summary_lower or "unknown" in summary_lower or "not available" in summary_lower or "not provided" in summary_lower):
            missing_data.append("Retention")

        if len(missing_data) >= 2:
            score -= 15
        elif len(missing_data) == 1:
            score -= 8

        if data_points <= 3:
            score -= 10

        is_unknown = "unknown" in company.lower() or company.lower().startswith("unknown") or company.startswith("#")
        weak_extraction = data_points <= 2 and not has_revenue
        if is_unknown or weak_extraction:
            score = min(score, 45)

        final_score = max(30, min(score, 95))

        confidence = 50
        if data_points >= 5:
            confidence = 85
        elif data_points >= 4:
            confidence = 75
        elif data_points >= 3:
            confidence = 60
        elif data_points >= 2:
            confidence = 45

        # Apply infrastructure confidence multiplier
        infra_conf = orch.get_infra_confidence()
        confidence = round(confidence * infra_conf)
        confidence = max(10, min(confidence, 95))

        if final_score >= 75:
            verdict = "Strong Investment Candidate"
        elif final_score >= 60:
            verdict = "Moderate Opportunity"
        else:
            verdict = "Neutral"

        if intent == "interested" and final_score >= 70:
            deal_status = "Hot Lead"
        elif intent == "interested" and final_score >= 55:
            deal_status = "Warm Lead"
        elif final_score >= 65:
            deal_status = "Warm Lead"
        else:
            deal_status = "In Review"

        return final_score, confidence, verdict, deal_status, data_points

    score_result = orch.run_stage("scoring", _score, result)
    if score_result:
        final_score, final_confidence, final_verdict, deal_status, data_points = score_result
    else:
        final_score, final_confidence, final_verdict, deal_status = 50, 30, "Neutral", "Cold"

    # ── Stage 9: Strategy ────────────────────────────────────────────
    def _run_strategy(res):
        from app.rag.strategy_engine import StrategyEngine
        s = StrategyEngine.generate_all(res)
        priority = "High" if final_score >= 75 else ("Medium" if final_score >= 60 else "Low")
        return {
            "next_step": s.get("next_step", "Track for additional data points before engagement"),
            "reasoning": s.get("reasoning", "Insufficient data to assess."),
            "priority": priority,
        }

    strategy_result = orch.run_stage("strategy", _run_strategy, result) or {
        "next_step": "Track for additional data points before engagement",
        "reasoning": "Insufficient data to assess.",
        "priority": "Low",
    }

    # ── Build final response ─────────────────────────────────────────
    print(f"[ORCHESTRATOR] {orch.get_stage_summary()}")
    infra_conf = orch.get_infra_confidence()
    confidence_layers = orch.get_all_confidence_layers()
    degraded = orch.get_degraded_stages()
    if degraded:
        print(f"[ORCHESTRATOR] Degraded stages: {[d['name'] for d in degraded]}")
    print(f"[ORCHESTRATOR] Confidence layers: {confidence_layers}")
    print(f"[ORCHESTRATOR] Overall confidence: {final_confidence}")

    # Determine final rag_status with hard failure detection
    gen_rag_status = result.get("rag_status", "success")
    critical_stage_failures = [
        name for name, stage in orch.stages.items()
        if stage.status == "failed"
    ]
    if gen_rag_status == "error" or critical_stage_failures:
        final_rag_status = "failed"
    elif not chunks_by_section:
        final_rag_status = "empty_rag"
    else:
        final_rag_status = "success"

    return {
        "type": "investor",
        "company": company,
        "summary": result.get("summary", "Analysis completed"),
        "email": result.get("email", f"Hi,\n\nThanks for your interest in {company}."),
        "key_signal": result.get("key_signal", "N/A"),
        "rag_status": final_rag_status,
        "intent": {"intent": intent, "confidence": final_confidence, "signals": signals},
        "strategy": strategy_result,
        "score": final_score,
        "verdict": final_verdict,
        "deal_status": deal_status,
        "confidence": final_confidence,
        "financial_highlights": result.get("financial_highlights", {}),
        "confidence_by_section": result.get("confidence_by_section", {}),
        "data_warnings": result.get("data_warnings", []),
        "canonical_metrics": result.get("canonical_metrics", {}),
        "chart_data": result.get("chart_data", {}),
        "reasoning_traces": result.get("reasoning_traces", []),
        "_pipeline_stages": {n: vars(s) for n, s in orch.stages.items()},
        "_sub_components": {
            stage: {s: r.status for s, r in subs.items()}
            for stage, subs in orch._sub_components.items()
        },
        "_infra_confidence": infra_conf,
        "_confidence_layers": confidence_layers,
        "_degraded_stages": degraded,
        "_cache_hits": orch.get_cache_hits(),
        "_complexity": {
            "pages": orch.complexity.page_count,
            "estimated_charts": orch.complexity.estimated_charts,
            "estimated_tables": orch.complexity.estimated_tables,
            "complexity_score": orch.complexity.complexity_score,
        },
    }


def _abort_result(orch: PipelineOrchestrator, reason: str) -> Dict:
    return {
        "type": "investor",
        "company": "Unknown",
        "summary": f"WARNING: Analysis Failed — {reason}",
        "status": "empty_rag",
        "rag_status": "empty_rag",
        "confidence": 30,
        "_pipeline_stages": {n: vars(s) for n, s in orch.stages.items()},
        "_sub_components": {
            stage: {s: r.status for s, r in subs.items()}
            for stage, subs in orch._sub_components.items()
        },
        "_infra_confidence": orch.get_infra_confidence(),
        "_degraded_stages": orch.get_degraded_stages(),
        "_cache_hits": orch.get_cache_hits(),
        "_complexity": {
            "pages": orch.complexity.page_count,
            "estimated_charts": orch.complexity.estimated_charts,
            "estimated_tables": orch.complexity.estimated_tables,
            "complexity_score": orch.complexity.complexity_score,
        },
    }
