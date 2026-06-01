"""
Canonical Financial Metric Schema
==================================
Unified schema for all financial metrics extracted from pitch decks.
This is the single source of truth for financial data structures.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# Enums for type safety
# ─────────────────────────────────────────────────────────────────────────────

class MetricCategory(str, Enum):
    """High-level category of metric"""
    REVENUE = "revenue"
    GROWTH = "growth"
    CUSTOMER = "customer"
    MARKET = "market"
    FINANCIAL_HEALTH = "financial_health"
    FUNDRAISING = "fundraising"
    OPERATIONS = "operations"
    PROJECTION = "projection"
    UNKNOWN = "unknown"


class MetricSubcategory(str, Enum):
    """Granular subcategory for specific metric types"""
    # Revenue
    ARR = "arr"
    MRR = "mrr"
    REVENUE_TOTAL = "revenue_total"
    REVENUE_YOY = "revenue_yoy"
    BOOKINGS = "bookings"
    
    # Growth
    GROWTH_RATE = "growth_rate"
    MOM_GROWTH = "mom_growth"
    YoY_GROWTH = "yoy_growth"
    COGS_REDUCTION = "cogs_reduction"
    
    # Customer
    CUSTOMERS_TOTAL = "customers_total"
    CUSTOMERS_NEW = "customers_new"
    CUSTOMERS_RETENTION = "customers_retention"
    LTV = "ltv"
    CAC = "cac"
    LTV_CAC_RATIO = "ltv_cac_ratio"
    
    # Market
    TAM = "tam"
    SAM = "sam"
    SOM = "som"
    MARKET_SHARE = "market_share"
    
    # Financial Health
    MARGIN = "margin"
    BURN_RATE = "burn_rate"
    RUNWAY = "runway"
    EBITDA = "ebitda"
    PROFIT = "profit"
    CASH_POSITION = "cash_position"
    
    # Fundraising
    RAISE_AMOUNT = "raise_amount"
    VALUATION = "valuation"
    LEAD_INVESTOR = "lead_investor"
    
    # Operations
    EMPLOYEES = "employees"
    PARTNERS = "partners"
    LOCATIONS = "locations"
    
    # Projection
    PROJECTED_REVENUE = "projected_revenue"
    PROJECTED_ARR = "projected_arr"
    PROJECTED_CUSTOMERS = "projected_customers"
    
    UNKNOWN = "unknown"


class TemporalType(str, Enum):
    """Temporal classification of metric"""
    HISTORICAL = "historical"
    CURRENT = "current"
    PROJECTION = "projection"
    PIPELINE = "pipeline"
    CONTRACT = "contract"
    GRANT = "grant"


class ConfidenceTier(str, Enum):
    """Confidence classification tier"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Currency(str, Enum):
    """Supported currencies"""
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


# ─────────────────────────────────────────────────────────────────────────────
# Value Objects
# ─────────────────────────────────────────────────────────────────────────────

class NormalizedValue(BaseModel):
    """Normalized numeric representation"""
    raw: str = ""
    numeric: float = 0.0
    currency: Currency = Currency.INR
    scale: str = ""  # Cr, Lakh, Mn, Bn, K, units
    original_scale: str = ""  # Original unit from text
    
    @field_validator('numeric', mode='before')
    @classmethod
    def parse_numeric(cls, v):
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            import re
            cleaned = re.sub(r'[₹$£€,\s]', '', v)
            try:
                return float(cleaned)
            except:
                return 0.0
        return 0.0


class ConfidenceScore(BaseModel):
    """Detailed confidence scoring"""
    overall: float = 0.0
    tier: ConfidenceTier = ConfidenceTier.UNKNOWN
    factors: Dict[str, float] = Field(default_factory=dict)
    source_quality: float = 0.0
    context_clarity: float = 0.0
    value_plausibility: float = 0.0
    
    @field_validator('overall', mode='before')
    @classmethod
    def clamp_overall(cls, v):
        if v is None:
            return 0.0
        return max(0.0, min(1.0, float(v)))


class Evidence(BaseModel):
    """Source evidence for a metric"""
    slide_number: Optional[int] = None
    text: str = ""
    coordinates: Optional[Dict[str, float]] = None  # x, y, width, height
    extracted_from: str = ""  # table, text, chart, ocr
    context: str = ""  # surrounding text for context


# ─────────────────────────────────────────────────────────────────────────────
# Canonical Metric
# ─────────────────────────────────────────────────────────────────────────────

class CanonicalMetric(BaseModel):
    """
    The canonical metric object - single source of truth for all financial metrics.
    This is what gets stored, versioned, and served to frontend.
    """
    # Identity
    id: Optional[str] = None
    namespace: str = ""  # Company/document namespace
    
    # Classification
    category: MetricCategory = MetricCategory.UNKNOWN
    subcategory: MetricSubcategory = MetricSubcategory.UNKNOWN
    label: str = ""  # Human-readable label
    
    # Temporal
    temporal_type: TemporalType = TemporalType.UNKNOWN
    fiscal_year: Optional[str] = None  # FY24, FY25, etc.
    period: Optional[str] = None  # Q1 2024, H1 2024, etc.
    
    # Value
    normalized_value: Optional[NormalizedValue] = None
    display_value: str = ""  # Formatted for display
    
    # Confidence
    confidence: ConfidenceScore = Field(default_factory=ConfidenceScore)
    
    # Evidence
    evidence: List[Evidence] = Field(default_factory=list)
    primary_source: Optional[Evidence] = None
    
    # Metadata
    extraction_method: str = ""  # llm, regex, chart_extraction
    is_derived: bool = False  # Calculated from other metrics
    derived_from: List[str] = Field(default_factory=list)  # IDs of source metrics
    warnings: List[str] = Field(default_factory=list)
    
    # Timestamps
    extracted_at: datetime = Field(default_factory=datetime.now)
    validated_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True


# ─────────────────────────────────────────────────────────────────────────────
# Metric Collections
# ─────────────────────────────────────────────────────────────────────────────

class MetricCollection(BaseModel):
    """Container for a collection of metrics"""
    namespace: str = ""
    company: str = ""
    document_id: str = ""
    
    # All extracted metrics
    metrics: List[CanonicalMetric] = Field(default_factory=list)
    
    # Aggregated values for quick access
    revenue: Optional[CanonicalMetric] = None
    arr: Optional[CanonicalMetric] = None
    mrr: Optional[CanonicalMetric] = None
    customers: Optional[CanonicalMetric] = None
    valuation: Optional[CanonicalMetric] = None
    raise_amount: Optional[CanonicalMetric] = None
    
    # Market sizing
    tam: Optional[CanonicalMetric] = None
    sam: Optional[CanonicalMetric] = None
    som: Optional[CanonicalMetric] = None
    
    # Growth metrics
    growth_rate: Optional[CanonicalMetric] = None
    
    # Extracted at
    extracted_at: datetime = Field(default_factory=datetime.now)
    
    def get_by_subcategory(self, subcategory: MetricSubcategory) -> List[CanonicalMetric]:
        """Get all metrics matching a subcategory"""
        return [m for m in self.metrics if m.subcategory == subcategory]
    
    def get_by_category(self, category: MetricCategory) -> List[CanonicalMetric]:
        """Get all metrics matching a category"""
        return [m for m in self.metrics if m.category == category]
    
    def get_high_confidence(self, min_confidence: float = 0.8) -> List[CanonicalMetric]:
        """Get metrics with confidence above threshold"""
        return [m for m in self.metrics if m.confidence.overall >= min_confidence]


# ─────────────────────────────────────────────────────────────────────────────
# Flat representations for API
# ─────────────────────────────────────────────────────────────────────────────

class FlatMetric(BaseModel):
    """Flattened metric for simple API responses"""
    label: str
    display_value: str
    category: str
    subcategory: str
    temporal_type: str
    confidence: float
    confidence_tier: str
    slide: Optional[int] = None
    source_text: str = ""
    is_approximate: bool = False
    
    @classmethod
    def from_canonical(cls, metric: CanonicalMetric) -> FlatMetric:
        """Convert canonical metric to flat representation"""
        evidence_text = ""
        slide_num = None
        if metric.primary_source:
            evidence_text = metric.primary_source.text
            slide_num = metric.primary_source.slide_number
        
        return cls(
            label=metric.label,
            display_value=metric.display_value,
            category=metric.category.value,
            subcategory=metric.subcategory.value,
            temporal_type=metric.temporal_type.value,
            confidence=metric.confidence.overall,
            confidence_tier=metric.confidence.tier.value,
            slide=slide_num,
            source_text=evidence_text,
            is_approximate=any('approximate' in w.lower() for w in metric.warnings)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Serialization helpers
# ─────────────────────────────────────────────────────────────────────────────

def serialize_for_json(metric: CanonicalMetric) -> dict:
    """Serialize canonical metric to JSON-safe dict"""
    return {
        "id": metric.id,
        "namespace": metric.namespace,
        "label": metric.label,
        "display_value": metric.display_value,
        "numeric_value": metric.normalized_value.numeric if metric.normalized_value else 0.0,
        "category": metric.category.value,
        "subcategory": metric.subcategory.value,
        "temporal_type": metric.temporal_type.value,
        "confidence": metric.confidence.overall,
        "confidence_tier": metric.confidence.tier.value,
        "slide": metric.primary_source.slide_number if metric.primary_source else None,
        "source_text": metric.primary_source.text if metric.primary_source else "",
        "fiscal_year": metric.fiscal_year,
        "period": metric.period,
        "extraction_method": metric.extraction_method,
        "warnings": metric.warnings,
        "extracted_at": metric.extracted_at.isoformat() if metric.extracted_at else None
    }


def serialize_collection_for_json(collection: MetricCollection) -> dict:
    """Serialize metric collection to JSON-safe dict"""
    return {
        "namespace": collection.namespace,
        "company": collection.company,
        "document_id": collection.document_id,
        "metrics": [serialize_for_json(m) for m in collection.metrics],
        "extracted_at": collection.extracted_at.isoformat() if collection.extracted_at else None,
        "total_metrics": len(collection.metrics),
        "high_confidence_count": len(collection.get_high_confidence())
    }