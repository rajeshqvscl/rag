"""
Strategy Intelligence Engine — sector-aware investor strategy generation.

Phase 5 of the accuracy improvement plan.
"""

from typing import Dict, List, Optional, Any


# Sector-specific strategy templates
_SECTOR_STRATEGIES = {
    "saas": {
        "next_step": "Validate retention metrics, CAC efficiency, and scalability of the onboarding funnel. Schedule a deep-dive on unit economics.",
        "reasoning": "The company exhibits recurring revenue characteristics typical of enterprise SaaS. Focus due diligence on cohort retention and net dollar retention trends.",
        "question": "What is your current net dollar retention and how has it trended across customer cohorts?",
        "risk_area": "Customer concentration and churn risk in early-stage enterprise SaaS.",
    },
    "deeptech": {
        "next_step": "Assess IP portfolio strength, R&D milestones, and go-to-market partnership status. Schedule a technology deep-dive with the founding team.",
        "reasoning": "The company's value lies in proprietary technology and defensible IP. Due diligence should focus on patent landscape, technical moat, and commercialization pathway.",
        "question": "What is your IP filing status and what key technical milestones are expected in the next 12 months?",
        "risk_area": "Technology risk and extended time-to-market for deep-tech commercialisation.",
    },
    "healthcare": {
        "next_step": "Evaluate institutional partnership status, regulatory compliance timeline, and recurring subscription behavior. Schedule a clinical validation review.",
        "reasoning": "Healthcare infrastructure plays benefit from sticky institutional relationships and regulatory barriers to entry. Focus on partnership depth and recurring revenue quality.",
        "question": "What is your current institutional pipeline and what regulatory milestones are pending?",
        "risk_area": "Regulatory approval timelines and dependence on institutional sales cycles.",
    },
    "defence": {
        "next_step": "Assess procurement conversion timelines and dependency on government contracts. Schedule a regulatory compliance review.",
        "reasoning": "Defence contracting involves long procurement cycles but provides high-value, multi-year contracts once secured. Focus on order book visibility and diversification.",
        "question": "What is the current status of your procurement contracts and what is the expected timeline for conversion?",
        "risk_area": "Government procurement dependency and extended sales cycles.",
    },
    "fintech": {
        "next_step": "Validate regulatory compliance status, transaction volume trends, and unit economics. Schedule a regulatory and compliance audit review.",
        "reasoning": "Fintech platforms benefit from transaction-driven revenue with scalability characteristics. Focus on regulatory positioning, take-rate trends, and risk management framework.",
        "question": "What is your current regulatory status and how do you manage compliance across operating regions?",
        "risk_area": "Regulatory risk and compliance costs in evolving fintech regulation.",
    },
    "climate": {
        "next_step": "Evaluate distribution scalability and economics of the deployment model. Schedule a site visit and operational review.",
        "reasoning": "Climate-tech infrastructure plays require capital-efficient scaling with strong policy tailwinds. Focus on project economics, offtake agreement quality, and regulatory positioning.",
        "question": "What is your current deployment pipeline and what is the expected IRR profile of your projects?",
        "risk_area": "Policy dependency and capital intensity of climate-tech deployment.",
    },
    "agritech": {
        "next_step": "Validate rural distribution network effectiveness and farmer adoption metrics. Schedule a field visit and partner review.",
        "reasoning": "Agritech platforms operate at the intersection of technology and rural supply chains. Focus on unit economics at the farmer level, network density, and repeat usage rates.",
        "question": "What is your farmer retention rate and how does unit economics vary across regions?",
        "risk_area": "Adoption risk in rural markets and dependency on last-mile distribution partners.",
    },
    "ai": {
        "next_step": "Assess model performance metrics, enterprise pilot outcomes, and data moat strength. Schedule a technical architecture review.",
        "reasoning": "AI-native companies benefit from data network effects and rapid technological advancement. Focus on model differentiation, data acquisition strategy, and enterprise adoption metrics.",
        "question": "What proprietary data assets do you have and what is your model's performance advantage over alternatives?",
        "risk_area": "Model commoditization risk and dependency on proprietary data access.",
    },
    "hrtech": {
        "next_step": "Validate recruitment SaaS model pricing, recruiter activity/productivity metrics, and background verification partner economics. Schedule a deep-dive on customer acquisition cost and net revenue retention.",
        "reasoning": "The company operates in HRTech / Recruiter productivity, benefiting from sticky B2B subscriptions and transaction volumes from verification/BGV. Due diligence should focus on user engagement metrics, pilot-to-subscription conversion, and cost of delivery.",
        "question": "What is the typical time-to-value for recruiters adopting your platform, and how are transaction-based services like BGV priced and delivered?",
        "risk_area": "Enterprise sales cycles in HR tech, recruiter churn, and BGV margin compression.",
    },
    "general": {
        "next_step": "Request customer references, detailed financial projections, and competitive positioning analysis. Schedule a management introduction call.",
        "reasoning": "The company operates in a growing addressable market with early commercial traction. Further due diligence is required to assess scalability and competitive positioning.",
        "question": "What are your key growth drivers and how do you plan to scale over the next 12-18 months?",
        "risk_area": "Early-stage execution risk and market adoption uncertainty.",
    },
}


class StrategyEngine:
    """Generate sector-aware investor strategy intelligence."""

    @staticmethod
    def detect_sector(structured_data: dict) -> str:
        """Detect sector from structured data."""
        brief = structured_data.get("company_brief", {}) or {}
        sector = brief.get("sector", "")
        if sector:
            sl = sector.lower()
            for known_sector in _SECTOR_STRATEGIES:
                if known_sector == "general":
                    continue
                if known_sector in sl or sl in known_sector:
                    return known_sector

        # Keyword-based fallback
        text = str(structured_data)
        text_lower = text.lower()
        sector_keywords = {
            "saas": ["saas", "subscription", "cloud software", "b2b saas"],
            "deeptech": ["deep tech", "patent", "r&d", "proprietary", "ip"],
            "healthcare": ["healthcare", "diagnostic", "hospital", "clinic", "medical"],
            "defence": ["defence", "defense", "military", "government contract"],
            "fintech": ["fintech", "payment", "lending", "banking", "insurance"],
            "climate": ["renewable", "solar", "clean energy", "carbon", "climate"],
            "agritech": ["agritech", "agriculture", "farm", "rural", "crop"],
            "ai": ["artificial intelligence", "machine learning", "ai-powered"],
            "hrtech": ["hrtech", "recruitment", "hiring", "ats", "bgv", "sourcing", "staffing"],
        }
        scores = {}
        for sector, keywords in sector_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[sector] = scores.get(sector, 0) + 1
        if scores:
            return max(scores, key=scores.get)
        return "general"

    @staticmethod
    def get_strategy(sector: str) -> dict:
        """Get strategy template for a sector."""
        return _SECTOR_STRATEGIES.get(sector, _SECTOR_STRATEGIES["general"])

    @staticmethod
    def generate_next_step(structured_data: dict) -> str:
        """Generate next-step recommendation based on sector."""
        sector = StrategyEngine.detect_sector(structured_data)
        strategy = StrategyEngine.get_strategy(sector)
        return strategy["next_step"]

    @staticmethod
    def generate_reasoning(structured_data: dict) -> str:
        """Generate investor reasoning based on sector."""
        sector = StrategyEngine.detect_sector(structured_data)
        strategy = StrategyEngine.get_strategy(sector)
        return strategy["reasoning"]

    @staticmethod
    def generate_question(structured_data: dict) -> str:
        """Generate follow-up question based on sector."""
        sector = StrategyEngine.detect_sector(structured_data)
        strategy = StrategyEngine.get_strategy(sector)
        return strategy["question"]

    @staticmethod
    def generate_risk_area(structured_data: dict) -> str:
        """Generate key risk area based on sector."""
        sector = StrategyEngine.detect_sector(structured_data)
        strategy = StrategyEngine.get_strategy(sector)
        return strategy["risk_area"]

    @staticmethod
    def generate_all(structured_data: dict) -> Dict[str, str]:
        """Generate all strategy fields."""
        sector = StrategyEngine.detect_sector(structured_data)
        strategy = StrategyEngine.get_strategy(sector)
        return {
            "sector": sector,
            "next_step": strategy["next_step"],
            "reasoning": strategy["reasoning"],
            "question": strategy["question"],
            "risk_area": strategy["risk_area"],
        }
