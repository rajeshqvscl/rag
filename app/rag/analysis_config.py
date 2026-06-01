"""
Pitch Deck Analysis Configuration - Customizable analysis dimensions per deck type
"""

from typing import Dict, List
from dataclasses import dataclass
from enum import Enum


class DeckType(Enum):
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    GROWTH = "growth"


@dataclass
class AnalysisDimension:
    name: str
    description: str
    weight: float
    keywords: List[str]


@dataclass
class DeckTypeConfig:
    name: str
    tagline: str
    dimensions: List[AnalysisDimension]
    focus_areas: List[str]
    critical_metrics: List[str]
    red_flags: List[str]


class AnalysisConfig:
    """
    Configurable analysis dimensions for different pitch deck types.
    Each deck type has unique dimensions relevant to their stage.
    """
    
    DIMENSIONS: Dict[DeckType, DeckTypeConfig] = {
        DeckType.SEED: DeckTypeConfig(
            name="Seed Round",
            tagline="Early-stage startup pitch deck",
            dimensions=[
                AnalysisDimension("problem", "Problem statement & pain point", 1.2, ["problem", "pain", "issue", "challenge"]),
                AnalysisDimension("solution", "Proposed solution & uniqueness", 1.2, ["solution", "product", "offering", "unique"]),
                AnalysisDimension("founder_vision", "Founders' vision & commitment", 1.1, ["founder", "team", "vision", "experience"]),
                AnalysisDimension("market_size", "TAM/SAM analysis", 1.0, ["market", "TAM", "opportunity", "size"]),
                AnalysisDimension("traction", "Early traction indicators", 1.3, ["traction", "customer", "pilot", "mvp"]),
                AnalysisDimension("business_model", "Revenue model viability", 0.9, ["model", "revenue", "pricing"]),
                AnalysisDimension("funding_use", "Use of funds clarity", 0.8, ["funds", "use", "capital", "invest"]),
            ],
            focus_areas=["Problem-solution fit", "Founder credibility", "Early traction", "Market opportunity"],
            critical_metrics=["Customer acquisition rate", "Retention", "Unit economics"],
            red_flags=["No customer validation", "Unrealistic projections", "Overvalued"]
        ),
        DeckType.SERIES_A: DeckTypeConfig(
            name="Series A",
            tagline="Growth-stage startup pitch deck",
            dimensions=[
                AnalysisDimension("traction_metrics", "Revenue & user growth", 1.3, ["growth", "revenue", "users", "arr", "mrr"]),
                AnalysisDimension("unit_economics", "LTV, CAC, burn rate", 1.2, ["unit economics", "ltv", "cac", "burn", "margins"]),
                AnalysisDimension("market_position", "Competitive landscape", 1.1, ["competition", "competitive", "market share"]),
                AnalysisDimension("scalability", "Growth potential", 1.1, ["scale", "scalable", "growth", "expand"]),
                AnalysisDimension("team_strength", "Team depth & execution", 1.0, ["team", "hiring", "executive", "cto", "cfo"]),
                AnalysisDimension("product_market_fit", "PMF evidence", 1.2, ["pmf", "product-market", "fit", "adoption"]),
                AnalysisDimension("funding_efficiency", "Previous round utilization", 0.9, ["funds", " runway", "burn"]),
                AnalysisDimension("business_model", "Scalable revenue model", 1.0, ["model", "revenue", "pricing", "saas"]),
            ],
            focus_areas=["Product-market fit", "Unit economics", "Scalable growth", "Market position"],
            critical_metrics=["YoY growth", "Net revenue retention", "CAC/LTV ratio", "Runway"],
            red_flags=["High burn with low growth", "Churning customers", "Market saturation"]
        ),
        DeckType.SERIES_B: DeckTypeConfig(
            name="Series B",
            tagline="Expansion-stage startup pitch deck",
            dimensions=[
                AnalysisDimension("market_dominance", "Market share & position", 1.3, ["market share", "dominance", "leader"]),
                AnalysisDimension("financial_scale", "Revenue scale & margins", 1.2, ["revenue", "margin", "profit", "ebitda"]),
                AnalysisDimension("operational_efficiency", "Scaling operations", 1.1, ["operations", "efficiency", "process", "automation"]),
                AnalysisDimension("expansion_strategy", "Geographic/product expansion", 1.1, ["expansion", "geo", "product", "enter"]),
                AnalysisDimension("competitive_defense", "Moat & barriers", 1.2, ["competitive", "moat", "barrier", "defense"]),
                AnalysisDimension("team_depth", "Executive team strength", 1.0, ["team", "executive", "c-suite", "leadership"]),
                AnalysisDimension("acquisition_channels", "Sustainable growth channels", 1.0, ["acquisition", "channel", "sales", "marketing"]),
                AnalysisDimension("exit_potential", "M&A and IPO readiness", 0.9, ["exit", "acquisition", "ipo", "strategic"]),
            ],
            focus_areas=["Market leadership", "Financial scale", "Operational excellence", "Competitive moat"],
            critical_metrics=["Market share growth", "Gross margins", "Path to profitability", "NPS scores"],
            red_flags=["Market share decline", "Margin compression", "Increased churn"]
        ),
        DeckType.GROWTH: DeckTypeConfig(
            name="Growth / Late Stage",
            tagline="Late-stage company pitch deck",
            dimensions=[
                AnalysisDimension("profitability", "Path to sustainable profits", 1.3, ["profit", "profitability", "ebitda", "cash flow"]),
                AnalysisDimension("market_leadership", "Clear market leader position", 1.2, ["leadership", "market", "leader", "winner"]),
                AnalysisDimension("financial_health", "Revenue quality & balance sheet", 1.2, ["revenue", "balance", "cash", "quality"]),
                AnalysisDimension("governance", "Corporate governance & compliance", 1.1, ["governance", "board", "compliance", "sox"]),
                AnalysisDimension("risk_management", "Risk mitigation strategies", 1.0, ["risk", "mitigation", "hedging", "insurance"]),
                AnalysisDimension("exit_readiness", "IPO/M&A preparation", 1.1, ["ipo", "exit", "readiness", "prospectus"]),
                AnalysisDimension("stakeholder_returns", "Value creation & distribution", 1.0, ["return", "dividend", "buyback", "value"]),
                AnalysisDimension(" ESG", "ESG & sustainability", 0.8, ["esg", "sustainability", "governance", "carbon"]),
            ],
            focus_areas=["Profitability", "Market leadership", "Governance", "Exit readiness"],
            critical_metrics=["EBITDA margins", "Market cap growth", "Governance scores", "Customer concentration"],
            red_flags=["Revenue concentration", "Governance issues", "Regulatory risk"]
        ),
    }
    
    @classmethod
    def get_config(cls, deck_type: DeckType) -> DeckTypeConfig:
        return cls.DIMENSIONS.get(deck_type, cls.DIMENSIONS[DeckType.SEED])
    
    @classmethod
    def get_config_by_name(cls, deck_type_name: str) -> DeckTypeConfig:
        try:
            deck_type = DeckType(deck_type_name.lower())
            return cls.get_config(deck_type)
        except ValueError:
            return cls.DIMENSIONS[DeckType.SEED]
    
    @classmethod
    def get_dimensions(cls, deck_type: DeckType, mode: str = "detailed") -> List[str]:
        config = cls.get_config(deck_type)
        dimensions = [d.name for d in config.dimensions]
        
        if mode == "quick":
            return dimensions[:4]
        elif mode == "detailed":
            return dimensions[:6]
        else:
            return dimensions
    
    @classmethod
    def get_weighted_dimensions(cls, deck_type: DeckType) -> List[Dict]:
        config = cls.get_config(deck_type)
        return [
            {"name": d.name, "description": d.description, "weight": d.weight}
            for d in config.dimensions
        ]
    
    @classmethod
    def get_all_types(cls) -> List[Dict]:
        return [
            {
                "value": dt.value,
                "name": config.name,
                "tagline": config.tagline,
                "focus_areas": config.focus_areas,
                "dimension_count": len(config.dimensions)
            }
            for dt, config in cls.DIMENSIONS.items()
        ]
    
    @classmethod
    def build_comparison_prompt_context(cls, deck_type: DeckType) -> str:
        config = cls.get_config(deck_type)
        
        context = f"""
## {config.name} Analysis Focus
{config.tagline}

### Key Focus Areas:
{chr(10).join(f"- {area}" for area in config.focus_areas)}

### Critical Metrics to Evaluate:
{chr(10).join(f"- {metric}" for metric in config.critical_metrics)}

### Red Flags to Watch:
{chr(10).join(f"- {flag}" for flag in config.red_flags)}

### Analysis Dimensions:
"""
        for dim in config.dimensions:
            context += f"\n- **{dim.name}** ({dim.weight}x weight): {dim.description}"
        
        return context
