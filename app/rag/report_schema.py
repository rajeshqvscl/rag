"""
Structured Report Schema — canonical Pydantic models for all report sections.
Transforms extracted dicts into validated objects before deterministic rendering.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class CompanyBrief(BaseModel):
    name: str = ""
    tagline: str = ""
    one_liner: str = ""
    stage: str = ""
    sector: str = ""


class BusinessOverview(BaseModel):
    model: str = ""
    revenue_model: str = ""
    target_customers: str = ""
    gtm: str = ""
    differentiator: str = ""


class IndustryOverview(BaseModel):
    tam: str = ""
    sam: str = ""
    som: str = ""
    market_context: str = ""
    key_trends: List[str] = []


class Problem(BaseModel):
    statement: str = ""
    pain_points: List[str] = []


class Solution(BaseModel):
    description: str = ""
    key_features: List[str] = []
    technology: str = ""
    usp: str = ""


class Traction(BaseModel):
    revenue: str = ""
    revenue_time_type: str = ""
    orders: str = ""
    orders_time_type: str = ""
    customers: str = ""
    customers_time_type: str = ""
    key_milestones: List[str] = []


class Funding(BaseModel):
    current_raise: str = ""
    valuation: str = ""
    previous_rounds: List[Any] = []
    investors: List[str] = []
    use_of_funds: List[Any] = []


class Pipeline(BaseModel):
    pipeline_value: str = ""
    lois: str = ""
    prospects: List[Any] = []


class RevenueProjection(BaseModel):
    period: str = ""
    value: str = ""


class RevenueDetails(BaseModel):
    current_revenue: str = ""
    current_revenue_time_type: str = ""
    projections: List[RevenueProjection] = []


class Competition(BaseModel):
    competitors: List[str] = []
    differentiation: str = ""
    moat: str = ""
    market_position: str = ""


class Recognition(BaseModel):
    awards: List[str] = []
    certifications: List[str] = []
    media_coverage: List[str] = []


class AdditionalMetric(BaseModel):
    key: str = ""
    value: str = ""
    context: str = ""


class ReportSections(BaseModel):
    company_brief: CompanyBrief = Field(default_factory=CompanyBrief)
    business_overview: BusinessOverview = Field(default_factory=BusinessOverview)
    industry_overview: IndustryOverview = Field(default_factory=IndustryOverview)
    problem: Problem = Field(default_factory=Problem)
    solution: Solution = Field(default_factory=Solution)
    traction: Traction = Field(default_factory=Traction)
    funding: Funding = Field(default_factory=Funding)
    pipeline: Pipeline = Field(default_factory=Pipeline)
    revenue_details: RevenueDetails = Field(default_factory=RevenueDetails)
    competition: Competition = Field(default_factory=Competition)
    recognition: Recognition = Field(default_factory=Recognition)
    additional_metrics: List[AdditionalMetric] = []


def hydrate_report_sections(structured_data: dict) -> ReportSections:
    """Convert raw structured_data dict into validated ReportSections."""
    raw = {}

    for section_name in ReportSections.model_fields:
        if section_name == "additional_metrics":
            raw["additional_metrics"] = structured_data.get("additional_metrics", [])
            continue
        section_raw = structured_data.get(section_name, {})
        if not isinstance(section_raw, dict):
            section_raw = {}
        raw[section_name] = section_raw

    return ReportSections(**raw)
