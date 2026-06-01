"""
Semantic Fallback Intelligence — infers business model, customer type, problem,
market category, and value proposition from deck snippets when direct extraction fails.

Phase 3 of the accuracy improvement plan.
"""

import re
from typing import Dict, List, Optional, Any, Tuple

CONFIDENCE_THRESHOLD = 0.45


# Semantic memory map: keyword → (business_model, customer_type, distribution_channel)
_SEMANTIC_MEMORY_MAP: Dict[str, Tuple[str, str, str]] = {
    # Distribution signals
    "franchise": ("franchise-led distribution", "local franchisees", "franchise network"),
    "subscription": ("subscription-based SaaS", "enterprise subscribers", "direct sales"),
    "marketplace": ("multi-sided marketplace", "buyers and sellers", "platform"),
    "platform": ("technology platform", "platform users", "direct and channel"),
    "direct sales": ("direct sales model", "enterprise customers", "field sales"),
    "channel partner": ("channel partner model", "SMEs", "partner network"),
    "distributor": ("distribution model", "retailers", "distributor network"),
    "agency": ("agency model", "brands", "direct outreach"),
    "consulting": ("consulting-led model", "enterprise clients", "consulting engagements"),

    # Business model signals
    "saas": ("subscription SaaS model", "enterprise and SMB", "direct and self-serve"),
    "b2b": ("B2B enterprise model", "business customers", "direct sales and partnerships"),
    "b2c": ("B2C direct-to-consumer", "consumers", "digital marketing"),
    "b2b2c": ("B2B2C platform model", "businesses and end-users", "partner-led"),
    "d2c": ("direct-to-consumer model", "consumers", "e-commerce and retail"),
    "wholesale": ("wholesale distribution", "retailers", "B2B sales"),
    "retail": ("retail model", "consumers", "retail outlets"),

    # Sector signals
    "procurement": ("B2B procurement platform", "government and enterprise", "direct sales"),
    "defense": ("defense contracting", "government/military", "procurement cycles"),
    "hospital": ("healthcare infrastructure", "hospitals", "institutional sales"),
    "clinic": ("healthcare services", "clinics and patients", "clinic network"),
    "diagnostic": ("diagnostics platform", "diagnostic labs", "B2B partnerships"),
    "telemedicine": ("telehealth platform", "patients", "digital channels"),
    "banking": ("fintech platform", "consumers", "digital banking"),
    "payment": ("payments platform", "merchants", "payment gateway"),
    "lending": ("lending platform", "borrowers", "digital lending"),
    "insurance": ("insurtech platform", "policyholders", "digital and agent"),

    # Customer type signals
    "enterprise": ("enterprise SaaS model", "enterprise", "direct sales"),
    "sme": ("SME-focused platform", "SMEs", "digital and channel"),
    "consumer": ("consumer platform", "consumers", "digital marketing"),
    "farmer": ("agritech platform", "farmers", "rural network"),
    "student": ("edtech platform", "students", "digital and institutional"),
    "doctor": ("healthtech platform", "doctors", "institutional sales"),
    "hospital": ("healthcare platform", "hospitals", "institutional sales"),

    # Technology signals
    "ai": ("AI-first platform", "enterprise", "direct and API"),
    "ml": ("ML-powered platform", "enterprise", "API and SaaS"),
    "iot": ("IoT platform", "enterprise", "hardware + SaaS"),
    "cloud": ("cloud platform", "enterprise", "SaaS"),
    "api": ("API-first platform", "developers", "self-serve"),
    "mobile": ("mobile-first platform", "consumers", "app stores"),

    # Revenue signals
    "commission": ("commission-based marketplace", "platform participants", "platform"),
    "transaction fee": ("transaction-based model", "platform users", "digital"),
    "licensing": ("licensing model", "enterprise", "direct sales"),
    "advertising": ("ad-supported model", "users and advertisers", "digital"),
    "freemium": ("freemium model", "users", "self-serve"),
    "usage-based": ("usage-based pricing", "platform users", "API"),
    "revenue share": ("revenue share model", "partners", "partner network"),
}


class FallbackInferenceEngine:
    """Infer business details from available deck snippets when direct extraction is empty."""

    @staticmethod
    def infer_business_model(chunks_text: str, existing_data: dict) -> Dict[str, str]:
        """Infer business model, customer type, distribution from text keywords."""
        if not chunks_text:
            return {}
        text_lower = chunks_text.lower()
        result = {"model": "", "revenue_model": "", "target_customers": "", "gtm": ""}

        best_match: Optional[str] = None
        best_score = 0
        for keyword, (model, customer, gtm) in _SEMANTIC_MEMORY_MAP.items():
            if keyword in text_lower:
                count = text_lower.count(keyword)
                score = count * len(keyword)
                if score > best_score:
                    best_score = score
                    best_match = keyword
                    result["model"] = model
                    result["target_customers"] = customer
                    result["gtm"] = gtm

        if best_match:
            # Revenue model inference
            if any(k in text_lower for k in ["subscription", "saas", "monthly", "annual"]):
                result["revenue_model"] = "subscription fees"
            elif any(k in text_lower for k in ["commission", "transaction", "marketplace"]):
                result["revenue_model"] = "commission on transactions"
            elif any(k in text_lower for k in ["licensing", "license"]):
                result["revenue_model"] = "software licensing"
            elif any(k in text_lower for k in ["advertis", "sponsor"]):
                result["revenue_model"] = "advertising"
            elif any(k in text_lower for k in ["procurement", "contract", "government"]):
                result["revenue_model"] = "government contracts"
            elif any(k in text_lower for k in ["consulting", "services"]):
                result["revenue_model"] = "consulting fees"
            else:
                result["revenue_model"] = f"{model.split()[0]} fees"

        return result

    @staticmethod
    def infer_problem_statement(chunks_text: str) -> str:
        """Infer problem statement from pain-point keywords."""
        if not chunks_text:
            return ""
        text_lower = chunks_text.lower()

        pain_patterns = [
            (r'(?:pain|challenge|problem|issue|difficult|hard|complex)\s+(?:point|area|is|of|in|with)?\s*.{10,100}?\.',
             "The market faces challenges including "),
            (r'(?:lack of|absence of|no|limited|insufficient|inadequate)\s+.{10,60}',
             "Key market gaps include "),
            (r'(?:inefficient|fragmented|manual|outdated|slow|costly|expensive).{10,60}',
             "Current approaches are "),
        ]

        for pattern, prefix in pain_patterns:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m:
                return f"{prefix}{m.group(0).strip().lstrip(',. ')}."

        # Fallback: keyword-based problem synthesis
        pain_keywords = {
            "inefficient": "inefficient manual processes",
            "fragmented": "fragmented market with no single solution",
            "expensive": "high cost of existing solutions",
            "manual": "manual processes requiring automation",
            "paper": "paper-based workflows",
            "offline": "offline processes needing digitization",
            "middlemen": "middlemen-driven supply chain",
            "waste": "significant waste and inefficiency",
        }

        found_pains = []
        for kw, pain_desc in pain_keywords.items():
            if kw in text_lower:
                found_pains.append(pain_desc)

        if found_pains:
            return f"The market is characterized by {' and '.join(found_pains[:3])}."
        return ""

    @staticmethod
    def infer_value_proposition(chunks_text: str) -> str:
        """Infer value proposition from keywords."""
        if not chunks_text:
            return ""
        text_lower = chunks_text.lower()

        value_signals = {
            "cost": "cost reduction",
            "save": "cost savings",
            "efficiency": "operational efficiency",
            "automation": "process automation",
            "speed": "faster execution",
            "transparent": "transparency",
            "track": "tracking and visibility",
            "real-time": "real-time visibility",
            "quality": "quality improvement",
            "access": "broader access",
            "convenience": "convenience",
            "digital": "digital transformation",
            "platform": "platform consolidation",
        }

        signals_found = []
        for kw, signal in value_signals.items():
            if kw in text_lower:
                signals_found.append(signal)

        if signals_found:
            return f"The platform delivers {' and '.join(signals_found[:3])}."
        return ""

    @staticmethod
    def infer_sector(chunks_text: str) -> str:
        """Infer sector/category from keywords."""
        if not chunks_text:
            return ""
        text_lower = chunks_text.lower()

        sector_signals = {
            "health": "healthcare",
            "medical": "healthcare",
            "hospital": "healthcare",
            "clinic": "healthcare",
            "pharma": "healthcare",
            "defence": "defence",
            "defense": "defence",
            "military": "defence",
            "security": "defence",
            "bank": "fintech",
            "payment": "fintech",
            "insurance": "fintech",
            "lending": "fintech",
            "loan": "fintech",
            "farm": "agritech",
            "crop": "agritech",
            "agriculture": "agritech",
            "solar": "climate",
            "renewable": "climate",
            "clean energy": "climate",
            "carbon": "climate",
            "sustainable": "climate",
            "saas": "saas",
            "cloud": "saas",
            "subscription": "saas",
            "ai": "ai",
            "machine learning": "ai",
            "deep learning": "ai",
            "patent": "deeptech",
            "r&d": "deeptech",
            "research": "deeptech",
        }

        scores: Dict[str, int] = {}
        for kw, sector in sector_signals.items():
            if kw in text_lower:
                scores[sector] = scores.get(sector, 0) + 1

        if scores:
            return max(scores, key=scores.get)
        return ""

    @classmethod
    def infer_all(cls, chunks_text: str, existing_data: dict) -> Dict[str, Any]:
        """Run all fallback inferences. Returns dict with only the missing fields filled."""
        if not chunks_text:
            return {}

        biz_data = existing_data.get("business_overview", {}) or {}
        prob_data = existing_data.get("problem", {}) or {}
        brief_data = existing_data.get("company_brief", {}) or {}

        result = {}

        # Infer business model if missing
        biz_model = cls.infer_business_model(chunks_text, existing_data)
        if biz_model.get("model") and not biz_data.get("model"):
            if "business_overview" not in result:
                result["business_overview"] = {}
            result["business_overview"]["model"] = biz_model["model"]
            if biz_model.get("revenue_model") and not biz_data.get("revenue_model"):
                result["business_overview"]["revenue_model"] = biz_model["revenue_model"]
            if biz_model.get("target_customers") and not biz_data.get("target_customers"):
                result["business_overview"]["target_customers"] = biz_model["target_customers"]
            if biz_model.get("gtm") and not biz_data.get("gtm"):
                result["business_overview"]["gtm"] = biz_model["gtm"]
        else:
            # Even if model exists, fill revenue_model if missing
            if biz_model.get("revenue_model") and not biz_data.get("revenue_model"):
                if "business_overview" not in result:
                    result["business_overview"] = {}
                result["business_overview"]["revenue_model"] = biz_model["revenue_model"]

        # Infer problem if missing
        if not prob_data.get("statement"):
            inferred_problem = cls.infer_problem_statement(chunks_text)
            if inferred_problem:
                if "problem" not in result:
                    result["problem"] = {}
                result["problem"]["statement"] = inferred_problem

        # Infer value proposition as differentiator if missing
        if not biz_data.get("differentiator"):
            inferred_vp = cls.infer_value_proposition(chunks_text)
            if inferred_vp:
                if "business_overview" not in result:
                    result["business_overview"] = {}
                result["business_overview"]["differentiator"] = inferred_vp

        # Infer sector if missing
        if not brief_data.get("sector"):
            inferred_sector = cls.infer_sector(chunks_text)
            if inferred_sector:
                if "company_brief" not in result:
                    result["company_brief"] = {}
                result["company_brief"]["sector"] = inferred_sector

        return result


class ConfidenceBasedFallback:
    """Routes to uncertainty responses when retrieval confidence is low."""

    @staticmethod
    def calculate_retrieval_confidence(chunks: List[Any], scores: List[float] = None) -> float:
        """Calculate retrieval confidence based on chunk count and scores."""
        if not chunks:
            return 0.0

        base_confidence = min(len(chunks) / 3, 1.0) * 0.4

        if scores:
            avg_score = sum(scores) / len(scores)
            score_confidence = min(avg_score / 0.8, 1.0) * 0.6
        else:
            score_confidence = 0.6

        return min(base_confidence + score_confidence, 1.0)

    @staticmethod
    def should_hallucinate(retrieval_confidence: float, field: str) -> bool:
        """Return True if we should NOT synthesize and instead return uncertainty."""
        if retrieval_confidence < CONFIDENCE_THRESHOLD:
            return True
        critical_fields = {"strategy", "revenue", "funding", "valuation"}
        if field in critical_fields and retrieval_confidence < 0.6:
            return True
        return False

    @staticmethod
    def get_uncertainty_response(field: str) -> Dict[str, Any]:
        """Return uncertainty response for a field when confidence is low."""
        uncertainty_responses = {
            "strategy": {"value": "Insufficient data to determine strategy", "confidence_tier": "uncertain"},
            "revenue": {"value": "N/A", "confidence_tier": "uncertain"},
            "funding": {"value": "N/A", "confidence_tier": "uncertain"},
            "valuation": {"value": "N/A", "confidence_tier": "uncertain"},
            "traction": {"value": "N/A", "confidence_tier": "uncertain"},
            "market": {"value": "N/A", "confidence_tier": "uncertain"},
            "competition": {"value": "N/A", "confidence_tier": "uncertain"},
        }
        return uncertainty_responses.get(field, {"value": "Insufficient data", "confidence_tier": "uncertain"})

    @classmethod
    def check_and_route(cls, chunks: List[Any], scores: List[float], field: str) -> Tuple[bool, Any]:
        """
        Check retrieval confidence and route to fallback if needed.
        Returns (should_use_fallback, value).
        """
        confidence = cls.calculate_retrieval_confidence(chunks, scores)
        if cls.should_hallucinate(confidence, field):
            return True, cls.get_uncertainty_response(field)
        return False, None
