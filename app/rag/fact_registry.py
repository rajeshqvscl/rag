import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FactConfidence(Enum):
    HIGH = 95
    MEDIUM = 80
    LOW = 60
    UNVERIFIED = 40


class FactSource(Enum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    IMAGE = "image"
    HEADER = "header"
    CAPTION = "caption"


@dataclass
class ExtractedFact:
    name: str
    value: Any
    page: int
    source_type: FactSource = FactSource.TEXT
    source_detail: str = ""
    confidence: int = 85
    section: str = "general"
    extracted_at: datetime = field(default_factory=datetime.now)
    validated: bool = False
    metadata: Dict = field(default_factory=dict)
    fiscal_period: str = ""
    fiscal_year: int = 0
    comparison_period: str = ""
    growth_percentage: float = 0.0
    unit: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "value": self.value,
            "page": self.page,
            "source_type": self.source_type.value,
            "source_detail": self.source_detail,
            "confidence": self.confidence,
            "section": self.section,
            "validated": self.validated,
            "extracted_at": self.extracted_at.isoformat(),
            "metadata": self.metadata,
            "fiscal_period": self.fiscal_period,
            "fiscal_year": self.fiscal_year,
            "comparison_period": self.comparison_period,
            "growth_percentage": self.growth_percentage,
            "unit": self.unit
        }


class FactRegistry:
    def __init__(self):
        self._facts: Dict[str, List[ExtractedFact]] = {}
        self._index: Dict[str, str] = {}
    
    def add(self, fact: ExtractedFact) -> None:
        key = fact.name.lower().replace(" ", "_")
        if key not in self._facts:
            self._facts[key] = []
        
        existing = [f for f in self._facts[key] if f.value == fact.value and f.page == fact.page]
        if not existing:
            self._facts[key].append(fact)
            self._index[key] = key
    
    def get(self, name: str) -> List[ExtractedFact]:
        key = name.lower().replace(" ", "_")
        return self._facts.get(key, [])
    
    def get_best(self, name: str) -> Optional[ExtractedFact]:
        facts = self.get(name)
        if not facts:
            return None
        return max(facts, key=lambda f: f.confidence)
    
    def get_by_section(self, section: str) -> List[ExtractedFact]:
        results = []
        for facts in self._facts.values():
            results.extend([f for f in facts if f.section == section])
        return sorted(results, key=lambda f: f.confidence, reverse=True)
    
    def get_all_facts(self) -> List[ExtractedFact]:
        all_facts = []
        for facts in self._facts.values():
            all_facts.extend(facts)
        return all_facts
    
    def to_structured_json(self) -> Dict:
        return {
            "company": self._extract_category(["company", "founder", "established", "headquarters", "founded"]),
            "market": self._extract_category(["market", "tam", "sam", "som", "industry", "opportunity"]),
            "traction": self._extract_category(["revenue", "customers", "growth", "traction", "users", "adoption"]),
            "financials": self._extract_category(["revenue", "profit", "margin", "burn", "runway", "ebitda"]),
            "team": self._extract_category(["team", "founder", "cto", "ceo", "experience"]),
            "funding": self._extract_category(["funding", "raising", "investment", "round", "valuation"]),
            "competition": self._extract_category(["competition", "competitor", "advantage", "differentiation"]),
            "product": self._extract_category(["product", "technology", "platform", "feature"]),
            "awards": self._extract_category(["award", "recognition", "certification"]),
            "impact_metrics": self._extract_category(["impact", "esg", "carbon", "social"]),
            "risks": self._extract_category(["risk", "challenge", "concern"])
        }
    
    def _extract_category(self, keywords: List[str]) -> Dict:
        category_facts = {}
        for fact in self.get_all_facts():
            if any(kw in fact.name.lower() or kw in fact.section for kw in keywords):
                category_facts[fact.name] = {
                    "value": fact.value,
                    "page": fact.page,
                    "confidence": fact.confidence,
                    "source": fact.source_type.value
                }
        return category_facts
    
    def merge(self, other: 'FactRegistry') -> None:
        for fact in other.get_all_facts():
            self.add(fact)
    
    def get_stats(self) -> Dict:
        all_facts = self.get_all_facts()
        return {
            "total_facts": len(all_facts),
            "by_section": {
                section: len([f for f in all_facts if f.section == section])
                for section in set(f.section for f in all_facts)
            },
            "by_confidence": {
                "high": len([f for f in all_facts if f.confidence >= 90]),
                "medium": len([f for f in all_facts if 70 <= f.confidence < 90]),
                "low": len([f for f in all_facts if f.confidence < 70])
            },
            "validated": len([f for f in all_facts if f.validated])
        }


class FactExtractionPatterns:
    SECTION_PATTERNS = {
        "traction": ["traction", "milestones", "customers", "adoption", "revenue growth", "orders"],
        "financials": ["financial", "revenue", "profit", "ebitda", "margin", "unit economics", "pricing", "burn rate", "runway"],
        "market": ["market", "tam", "sam", "som", "opportunity", "industry", "size"],
        "competition": ["competition", "competitor", "differentiation", "advantage", "moat"],
        "team": ["team", "founder", "ceo", "cto", "advisor", "experience", "background"],
        "funding": ["funding", "raising", "investment", "capital", "valuation", "series", "round"],
        "product": ["product", "technology", "platform", "solution", "feature", "ip"],
        "awards": ["award", "recognition", "achievement", "certification"],
        "impact": ["impact", "sustainability", "esg", "social", "environmental"]
    }
    
    TEMPORAL_PATTERNS = {
        "fiscal_year": [
            r"(?:FY|F\.Y\.?|Fiscal\s*Year)[\s\-]*(\d{4})",
            r"(?:FY|F\.Y\.?|Fiscal)[\s\-]*(\d{2})(?:\s*/\s*(\d{2}))?",
            r"(?:FY|F\.Y\.?|Fiscal)[\s\-]*(\d{4})(?:\s*/\s*(\d{4}))?"
        ],
        "quarter": [
            r"(Q[1-4])[\s\-]*(?:FY)?(\d{4})?",
            r"(?:Q[1-4]|Quarter\s*[1-4])[\s\-]*(?:FY)?(\d{4})?",
            r"(?:Q[1-4])[\s\-]*(?:of\s*)?(?:FY)?(\d{4})?"
        ],
        "half_year": [
            r"(H[1-2]|H1|H2|Half)[\s\-]*(?:FY)?(\d{4})?",
            r"(?:First|Second)\s*half[\s\-]*(?:FY)?(\d{4})?"
        ],
        "comparison": [
            r"(?:vs\.?|versus|compared\s*to|from)\s*(?:FY|Q|H)[^\s,]+",
            r"(?:up|down)\s*from\s*(?:FY|Q|H)[^\s,]+",
            r"(?:increase|decrease)\s*of\s*[\d.]+%\s*(?:from|vs\.?)\s*([^\s,]+)",
            r"(?:YoY|Y-o-Y)[\s\-]*(?:growth|decline)?[\s\-]*(?:from)?\s*([^\s,]+)?"
        ]
    }
    
    METRIC_PATTERNS = {
        "revenue": [
            r"(?:revenue|sales|invoiced)[:\s]*([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|L|lakh|K|k|M|m|mn)?)",
            r"([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|L|lakh|K|k|M|m|mn)?)\s*(?:revenue|sales|invoiced)"
        ],
        "growth_rate": [
            r"(\d+(?:\.\d+)?)\s*%\s*(?:growth|YoY|increase|year)",
            r"(?:growth|YoY)[:\s]*(\d+(?:\.\d+)?)\s*%",
        ],
        "customers": [
            r"(\d+(?:,\d{3})*)\s*(?:customers|clients|users|partners|enterprises)",
            r"(?:customers|users)[:\s]*(\d+(?:,\d{3})*)"
        ],
        "valuation": [
            r"(?:valuation|pre-money|post-money)[:\s]*([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|M|m)?)",
            r"([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|M|m)?)\s*(?:valuation|pre-money)"
        ],
        "funding": [
            r"(?:raising|funding|investment|raise)[:\s]*([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|M|m)?)",
            r"([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|M|m)?)\s*(?:in funding|series)"
        ],
        "tam": [
            r"(?:TAM|market size)[:\s]*([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|B|b)?)",
            r"([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|B|b)?)\s*(?:TAM|market)"
        ]
    }


def extract_facts_from_text(text: str, page_num: int, section: str = "general") -> List[ExtractedFact]:
    facts = []
    patterns = FactExtractionPatterns()
    
    for metric_name, regexes in patterns.METRIC_PATTERNS.items():
        for regex in regexes:
            matches = re.finditer(regex, text, re.IGNORECASE)
            for match in matches:
                value = match.group(1).strip()
                if value and len(value) > 0:
                    fact = ExtractedFact(
                        name=metric_name,
                        value=value,
                        page=page_num,
                        source_type=FactSource.TEXT,
                        source_detail=f"regex match: {regex[:50]}",
                        section=section,
                        confidence=85
                    )
                    facts.append(fact)
    
    return facts


def normalize_currency(value: str) -> float:
    from app.rag.number_utils import parse_indian_number, safe_float
    result = parse_indian_number(value)
    if result != 0.0:
        return result
    # Try with USD→INR conversion
    lower = value.lower()
    if '$' in lower or 'usd' in lower:
        cleaned = value.replace(",", "").replace("$", "").replace("USD", "").replace(" ", "")
        m = re.search(r"[\d.]+", cleaned)
        if m:
            num = safe_float(m.group(), 0.0)
            if num:
                return num * 83.0
    return 0.0


def extract_temporal_info(text: str) -> Dict[str, Any]:
    """Extract fiscal period and year from text"""
    patterns = FactExtractionPatterns()
    result = {
        "fiscal_period": "",
        "fiscal_year": 0,
        "comparison_period": "",
        "growth_percentage": 0.0
    }
    
    for pattern_key, regexes in patterns.TEMPORAL_PATTERNS.items():
        for regex in regexes:
            match = re.search(regex, text, re.IGNORECASE)
            if match:
                if pattern_key == "fiscal_year":
                    year_str = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                    if len(year_str) == 2:
                        year = int("20" + year_str) if int(year_str) < 50 else int("19" + year_str)
                    elif len(year_str) == 4:
                        year = int(year_str)
                    else:
                        year = 0
                    result["fiscal_year"] = year
                    result["fiscal_period"] = "FY"
                elif pattern_key == "quarter":
                    result["fiscal_period"] = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                    if match.lastindex and match.lastindex >= 2 and match.group(2):
                        try:
                            result["fiscal_year"] = int(match.group(2))
                        except:
                            pass
                elif pattern_key == "half_year":
                    result["fiscal_period"] = match.group(1) if match.lastindex and match.lastindex >= 1 else "H1" if "H1" in match.group(0) else "H2"
                    if match.lastindex and match.lastindex >= 2 and match.group(2):
                        try:
                            result["fiscal_year"] = int(match.group(2))
                        except:
                            pass
                elif pattern_key == "comparison":
                    result["comparison_period"] = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
    
    growth_match = re.search(r"(?:up|increase|decline|growth)\s*(?:by)?\s*(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
    if growth_match:
        result["growth_percentage"] = float(growth_match.group(1))
    
    return result


def calculate_yoy_growth(current_value: float, previous_value: float) -> float:
    """Calculate Year-over-Year growth percentage"""
    if previous_value == 0:
        return 0.0
    return ((current_value - previous_value) / previous_value) * 100


def extract_unit(value: str) -> str:
    """Extract currency/unit from value string"""
    value_lower = value.lower()
    if "₹" in value or "rs" in value_lower:
        if "cr" in value_lower:
            return "Cr"
        elif "lakh" in value_lower or "l" in value_lower:
            return "Lakhs"
        elif "m" in value_lower or "mn" in value_lower:
            return "Mn"
        elif "k" in value_lower:
            return "K"
    elif "$" in value:
        if "b" in value_lower or "bn" in value_lower:
            return "Bn"
        elif "m" in value_lower or "mn" in value_lower:
            return "Mn"
        elif "k" in value_lower:
            return "K"
    return ""


def build_temporal_narrative(facts: List[ExtractedFact], metric_name: str) -> str:
    """Build investor-grade narrative with temporal context"""
    metric_facts = [f for f in facts if f.name == metric_name]
    if not metric_facts:
        return ""
    
    sorted_facts = sorted(metric_facts, key=lambda f: f.fiscal_year if f.fiscal_year > 0 else 0, reverse=True)
    
    if not sorted_facts:
        return ""
    
    latest = sorted_facts[0]
    if not latest.value:
        return ""
    
    narrative_parts = []
    
    if latest.fiscal_year > 0:
        period_str = f"FY{latest.fiscal_year}"
        if latest.fiscal_period and latest.fiscal_period != "FY":
            period_str = f"{latest.fiscal_period} FY{latest.fiscal_year}"
        narrative_parts.append(f"in {period_str}")
    elif latest.fiscal_period:
        narrative_parts.append(f"in {latest.fiscal_period}")
    
    if latest.comparison_period:
        if latest.growth_percentage != 0:
            direction = "up" if latest.growth_percentage > 0 else "down"
            narrative_parts.append(f"{direction} from {latest.comparison_period}")
    
    if latest.growth_percentage != 0:
        direction = "increase" if latest.growth_percentage > 0 else "decrease"
        narrative_parts.append(f"representing approximately {abs(latest.growth_percentage):.0f}% {direction}")
    
    return " ".join(narrative_parts)