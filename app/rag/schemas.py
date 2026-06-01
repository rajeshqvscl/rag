from pydantic import BaseModel, Field, validator
from typing import List, Optional, Any
from enum import Enum


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class RevenueData(BaseModel):
    value: str = ""
    period: str = ""
    confidence: int = 50

    @validator('value', pre=True)
    def validate_value(cls, v):
        if v is None:
            return ""
        if isinstance(v, str) and len(v) < 2:
            return ""
        return v


class OrdersData(BaseModel):
    value: str = ""
    confidence: int = 50

    @validator('value', pre=True)
    def validate_value(cls, v):
        if v is None:
            return ""
        if isinstance(v, str) and len(v) < 2:
            return ""
        return v


class TractionData(BaseModel):
    revenue: RevenueData = Field(default_factory=RevenueData)
    orders: OrdersData = Field(default_factory=OrdersData)
    growth_rate: str = ""
    clients: List[str] = []
    key_metrics: List[str] = []
    confidence: int = 50

    @validator('growth_rate', pre=True)
    def clean_growth(cls, v):
        if v is None:
            return ""
        return str(v)


class UnitEconomicsData(BaseModel):
    margin: str = ""
    ticket_size: str = ""
    cac: str = ""
    ltv: str = ""
    ltv_cac_ratio: str = ""
    confidence: int = 50


class MarketData(BaseModel):
    tam: str = ""
    sam: str = ""
    som: str = ""
    growth_rate: str = ""
    market_notes: str = ""
    confidence: int = 50


class CompetitionData(BaseModel):
    competitors: List[str] = []
    differentiation: str = ""
    advantage: str = ""
    barriers_to_entry: str = ""
    confidence: int = 50


class TeamData(BaseModel):
    founders: List[str] = []
    advisors: List[str] = []
    team_size: str = ""
    key_hires: List[str] = []
    background: str = ""
    confidence: int = 50


class FundingData(BaseModel):
    amount_raising: str = ""
    use_of_funds: List[str] = []
    runway: str = ""
    previous_funding: str = ""
    valuation: str = ""
    investors: List[str] = []
    confidence: int = 50


class PartnershipsData(BaseModel):
    strategic: List[str] = []
    technical: List[str] = []
    distribution: List[str] = []


class RecognitionData(BaseModel):
    awards: List[str] = []
    certifications: List[str] = []
    media: List[str] = []


class RiskData(BaseModel):
    key_risks: List[str] = []
    risk_level: str = ""
    mitigation: str = ""
    confidence: int = 50


class InsightsData(BaseModel):
    key_signal: str = ""
    investment_thesis: str = ""
    strengths: List[str] = []
    weaknesses: List[str] = []
    outlook: str = ""


class CompanyInfoData(BaseModel):
    name: str = ""
    stage: str = ""
    sector: str = ""
    founded_year: str = ""
    headquarters: str = ""
    tagline: str = ""

    @validator('sector', pre=True)
    def clean_sector(cls, v):
        if v is None:
            return "technology"
        return str(v)


class StructuredExtraction(BaseModel):
    company_info: CompanyInfoData = Field(default_factory=CompanyInfoData)
    traction: TractionData = Field(default_factory=TractionData)
    economics: UnitEconomicsData = Field(default_factory=UnitEconomicsData)
    market: MarketData = Field(default_factory=MarketData)
    competition: CompetitionData = Field(default_factory=CompetitionData)
    team: TeamData = Field(default_factory=TeamData)
    funding: FundingData = Field(default_factory=FundingData)
    partnerships: PartnershipsData = Field(default_factory=PartnershipsData)
    recognition: RecognitionData = Field(default_factory=RecognitionData)
    risks: RiskData = Field(default_factory=RiskData)
    insights: InsightsData = Field(default_factory=InsightsData)
    missing_data: List[str] = []

    def to_dict(self):
        result = {}
        for field_name, field_value in self.__dict__.items():
            if hasattr(field_value, '__dict__'):
                result[field_name] = field_value.__dict__
            else:
                result[field_name] = field_value
        return result


def validate_extraction(extraction_dict: dict) -> StructuredExtraction:
    """
    Validate and normalize extraction dict using Pydantic schema
    """
    try:
        validated = StructuredExtraction(**extraction_dict)
        return validated
    except Exception as e:
        print(f"[WARNING] Validation error: {e}")
        try:
            normalized = normalize_for_schema(extraction_dict)
            validated = StructuredExtraction(**normalized)
            return validated
        except Exception as e2:
            print(f"[ERROR] Could not normalize extraction: {e2}")
            return StructuredExtraction()


def normalize_for_schema(data: dict) -> dict:
    """
    Normalize extraction dict to match Pydantic schema
    """
    defaults = {
        "company_info": {"name": "", "stage": "", "sector": "", "founded_year": "", "headquarters": "", "tagline": ""},
        "traction": {"revenue": {"value": "", "period": "", "confidence": 50}, "orders": {"value": "", "confidence": 50},
                     "growth_rate": "", "clients": [], "key_metrics": [], "confidence": 50},
        "economics": {"margin": "", "ticket_size": "", "cac": "", "ltv": "", "unit_economics": "", "ltv_cac_ratio": "", "confidence": 50},
        "market": {"tam": "", "sam": "", "som": "", "growth_rate": "", "market_notes": "", "confidence": 50},
        "competition": {"competitors": [], "differentiation": "", "advantage": "", "barriers_to_entry": "", "confidence": 50},
        "team": {"founders": [], "advisors": [], "team_size": "", "key_hires": [], "background": "", "confidence": 50},
        "funding": {"amount_raising": "", "use_of_funds": [], "runway": "", "previous_funding": "", "valuation": "", "investors": [], "confidence": 50},
        "partnerships": {"strategic": [], "technical": [], "distribution": []},
        "recognition": {"awards": [], "certifications": [], "media": []},
        "risks": {"key_risks": [], "risk_level": "", "mitigation": "", "confidence": 50},
        "insights": {"key_signal": "", "investment_thesis": "", "strengths": [], "weaknesses": [], "outlook": ""},
        "missing_data": []
    }

    normalized = {}
    for key, default_value in defaults.items():
        if key in data and data[key]:
            normalized[key] = data[key]
        else:
            normalized[key] = default_value

    return normalized


def validate_metric_realism(key: str, value: str) -> tuple:
    """
    Validate metrics for realism - reject impossible values
    Returns (validated_value, is_valid, warning)
    """
    if not value:
        return value, True, ""

    value_str = str(value).lower()

    rules = {
        "margin": {"max": 95, "unit": "%", "reject": ["100", "99", "98"]},
        "growth_rate": {"max": 500, "unit": "%", "reject": ["1000", "10000"]},
        "revenue": {"reject_patterns": [r"^\d{1,3}$"]},
    }

    if key in rules:
        rule = rules[key]

        if "reject" in rule:
            for reject_val in rule["reject"]:
                if reject_val in value_str:
                    return value, False, f"Value {value} appears unrealistic for {key}"

        if "max" in rule:
            try:
                num_match = "".join(filter(lambda x: x.isdigit() or x == ".", value_str))
                if num_match:
                    num = float(num_match)
                    if num > rule["max"]:
                        return value, False, f"Value {value} exceeds realistic maximum for {key}"
            except:
                pass

    return value, True, ""


def enforce_minimum_data(data: dict) -> dict:
    """
    Ensure minimum required fields exist
    """
    if not data.get("company_info"):
        data["company_info"] = {}
    if not data["company_info"].get("sector"):
        data["company_info"]["sector"] = "technology"

    return data