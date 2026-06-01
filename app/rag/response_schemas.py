"""
Strict Pydantic response schemas for the FastAPI API contract.

Ensures every endpoint returns consistent shapes regardless of pipeline version.
Frontend code relies on these field names and types — never return None where an
object/list is expected.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any, List, Dict
from datetime import datetime


def _serialize_metric_value(val: Any) -> str:
    """Convert any metric value to a frontend-safe string.
    Never returns dict or list — prevents [object Object] rendering."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, dict):
        return str(val.get("value", val.get("display_value", val.get("label", ""))))
    if isinstance(val, list):
        return ", ".join(str(v) if not isinstance(v, dict) else str(v.get("value", "")) for v in val[:3])
    return str(val)


def _flatten_metric_dict(d: dict) -> dict:
    """Flatten a dict of metric objects to simple key-value pairs.
    {'tam': {'value': '₹250 Cr'}} → {'tam': '₹250 Cr'}"""
    if not isinstance(d, dict):
        return d
    result = {}
    for key, value in d.items():
        if isinstance(value, dict) and "value" in value:
            result[key] = _serialize_metric_value(value)
        elif isinstance(value, dict):
            result[key] = _flatten_metric_dict(value)
        elif isinstance(value, list):
            result[key] = [_flatten_metric_dict(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    return result


# ── Nested Value Object ─────────────────────────────────────────────

class MetricValue(BaseModel):
    """Standard metric value object used across all financial/metric fields."""
    value: str = ""
    source_slide: Optional[int] = None
    evidence_text: str = ""
    metric_type: str = ""
    confidence_tier: Optional[str] = None
    confidence: Optional[float] = 0.0


# ── Insights Response ───────────────────────────────────────────────

class InsightsResponse(BaseModel):
    """Normalized shape of pipeline output returned to frontend."""
    summary: str = ""
    email: str = ""
    key_signal: str = "N/A"
    score: Optional[float] = None
    confidence: float = 0.0
    rag_status: str = ""
    status: str = ""
    deal_status: str = ""

    # Structured data sections
    intent: dict = Field(default_factory=dict)
    strategy: dict = Field(default_factory=dict)
    financial_highlights: dict = Field(default_factory=dict)
    chart_data: dict = Field(default_factory=dict)
    confidence_by_section: dict = Field(default_factory=dict)
    canonical_metrics: dict = Field(default_factory=dict)
    field_confidence: dict = Field(default_factory=dict)
    pipeline_health: dict = Field(default_factory=lambda: {
        "rag": True, "agent": True, "email": True
    })

    # Metadata (aliased to match backend underscore-prefixed keys)
    data_warnings: List[str] = Field(default_factory=list)
    chart_metrics: List[dict] = Field(default_factory=list)
    infra_confidence: Optional[float] = Field(None, alias="_infra_confidence")
    degraded_stages: List[dict] = Field(default_factory=list, alias="_degraded_stages")
    chart_confidence: Optional[float] = Field(None, alias="_chart_confidence")
    visual_confidence: Optional[float] = Field(None, alias="_visual_confidence")

    class Config:
        populate_by_name = True

    @classmethod
    def from_raw(cls, raw: Optional[dict]) -> InsightsResponse:
        """Construct from any dict — missing fields get safe defaults.
        Flattens nested metric objects to prevent [object Object] rendering."""
        if not raw or not isinstance(raw, dict):
            return cls()

        return cls(
            summary=raw.get("summary") or "",
            email=raw.get("email") or "",
            key_signal=raw.get("key_signal") or "N/A",
            score=raw.get("score"),
            confidence=raw.get("confidence") or 0.0,
            rag_status=raw.get("rag_status") or "",
            status=raw.get("status") or raw.get("deal_status") or "",
            deal_status=raw.get("deal_status") or raw.get("status") or "",
            intent=raw.get("intent") or {},
            strategy=raw.get("strategy") or {},
            financial_highlights=_flatten_metric_dict(raw.get("financial_highlights") or {}),
            chart_data=raw.get("chart_data") or {},
            confidence_by_section=raw.get("confidence_by_section") or {},
            canonical_metrics=_flatten_metric_dict(raw.get("canonical_metrics") or {}),
            field_confidence=raw.get("field_confidence") or {},
            pipeline_health=raw.get("pipeline_health") or {
                "rag": True, "agent": True, "email": True
            },
            data_warnings=(
                raw.get("data_warnings")
                if isinstance(raw.get("data_warnings"), list)
                else []
            ),
            chart_metrics=(
                raw.get("chart_metrics")
                if isinstance(raw.get("chart_metrics"), list)
                else []
            ),
            infra_confidence=raw.get("_infra_confidence"),
            degraded_stages=(
                raw.get("_degraded_stages")
                if isinstance(raw.get("_degraded_stages"), list)
                else []
            ),
            chart_confidence=raw.get("_chart_confidence"),
            visual_confidence=raw.get("_visual_confidence"),
        )


# ── Status Response ─────────────────────────────────────────────────

class StatusResponse(BaseModel):
    """Response for GET /status/{item_id}."""
    id: int
    job_id: Optional[int] = None
    company: str = ""
    status: str = "processing"
    stage: str = "processing"
    progress: int = 0
    elapsed_time: Optional[float] = None
    error: str = ""
    insights: InsightsResponse = Field(default_factory=InsightsResponse)

    @classmethod
    def from_orm_row(cls, insight, raw_data: dict) -> StatusResponse:
        """Build from DB row + raw insights dict."""
        # Detect if raw_data is the insights dictionary itself or contains a sub-key
        insights_source = raw_data.get("insights") or raw_data.get("insight")
        if not insights_source:
            # Fall back to raw_data itself if it looks like an insights dict
            if any(k in raw_data for k in ["summary", "email", "canonical_metrics", "key_signal"]):
                insights_source = raw_data
            else:
                insights_source = {}

        return cls(
            id=raw_data.get("id", insight.id),
            job_id=raw_data.get("job_id"),
            company=raw_data.get("company") or getattr(insight, "company", ""),
            status=raw_data.get("status", "processing"),
            stage=raw_data.get("stage", "processing"),
            progress=raw_data.get("progress", 0),
            elapsed_time=raw_data.get("elapsed_time"),
            error=raw_data.get("error") or "",
            insights=InsightsResponse.from_raw(insights_source),
        )


# ── Result Response ─────────────────────────────────────────────────

class ResultResponse(BaseModel):
    """Response for GET /result/{item_id}."""
    id: int
    company: str = ""
    status: str = ""
    insights: InsightsResponse = Field(default_factory=InsightsResponse)
    result_available: bool = False


# ── Process Response ────────────────────────────────────────────────

class ProcessResponse(BaseModel):
    """Response for POST /process."""
    status: str = "processing"
    id: int
    job_id: Optional[int] = None
    summary: str = ""
    email: str = ""


# ── Pipeline Stage Response ─────────────────────────────────────────

class PipelineStageInfo(BaseModel):
    name: str = ""
    status: str = ""
    duration_ms: float = 0.0
    error: str = ""
    confidence_multiplier: float = 1.0
