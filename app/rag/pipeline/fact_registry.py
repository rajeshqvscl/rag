"""
Fact Registry - Central structured fact storage
Stores extracted facts with source, confidence, and validation status
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import re
from app.utils.text_utils import safe_lower


@dataclass
class Fact:
    """Single fact with full provenance"""
    category: str  # revenue, growth, team, etc.
    key: str       # metric name
    value: Any     # actual value
    page: int
    section: str
    source_type: str  # text, table, chart, image
    confidence: float = 0.9
    validated: bool = False
    raw_text: str = ""
    unit: str = ""
    
    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "page": self.page,
            "section": self.section,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "validated": self.validated,
            "unit": self.unit
        }


class FactRegistry:
    """
    Central fact store with validation and deduplication
    """
    def __init__(self):
        self.facts: List[Fact] = []
        self._by_category: Dict[str, List[Fact]] = {}
        self._by_key: Dict[str, List[Fact]] = {}
    
    def add(self, fact: Fact):
        """Add a validated fact"""
        self.facts.append(fact)
        
        if fact.category not in self._by_category:
            self._by_category[fact.category] = []
        self._by_category[fact.category].append(fact)
        
        if fact.key not in self._by_key:
            self._by_key[fact.key] = []
        self._by_key[fact.key].append(fact)
    
    def get_by_category(self, category: str) -> List[Fact]:
        return self._by_category.get(category, [])
    
    def get_by_key(self, key: str) -> Optional[Fact]:
        facts = self._by_key.get(key, [])
        if not facts:
            return None
        return max(facts, key=lambda f: f.confidence)
    
    def get_all(self, category: Optional[str] = None) -> List[Fact]:
        if category:
            return self._by_category.get(category, [])
        return self.facts
    
    def merge(self, other: 'FactRegistry'):
        """Merge another registry"""
        for fact in other.facts:
            self.add(fact)
    
    def to_structured_json(self) -> dict:
        """Export as structured JSON for downstream use"""
        structured = {
            "company": {},
            "market": {},
            "traction": {},
            "financials": {},
            "team": {},
            "funding": {},
            "competition": {},
            "awards": {},
            "impact_metrics": {},
            "risks": {},
            "insights": {}
        }
        
        for fact in self.facts:
            cat = fact.category
            if cat in structured:
                if cat not in ["risks", "insights"]:
                    structured[cat][fact.key] = {
                        "value": fact.value,
                        "unit": fact.unit,
                        "confidence": fact.confidence,
                        "page": fact.page,
                        "validated": fact.validated
                    }
                else:
                    if cat not in structured[cat]:
                        structured[cat] = []
                    structured[cat].append({
                        "key": fact.key,
                        "value": fact.value,
                        "page": fact.page
                    })
        
        return structured


# FACT EXTRACTION PROMPTS
FACT_EXTRACTION_PROMPTS = {
    "financials": """Extract ONLY revenue, margins, growth metrics from this text.
    Return JSON with: revenue, growth_rate, margin, burn_rate, runway
    If no data found, return null values. Do NOT guess or project.
    """,
    "team": """Extract founders, experience, key hires.
    Return JSON with: founders (list), key_experience, notable_hires
    """,
    "market": """Extract TAM/SAM/SOM and market positioning.
    Return JSON with: tam, sam, som, market_positioning
    """,
    "traction": """Extract customers, revenue, growth, milestones.
    Return JSON with: customers, revenue, growth_rate, key_milestones
    """
}


def extract_revenue_facts(text: str, page_num: int, section: str) -> List[Fact]:
    """Extract revenue-related facts from text"""
    facts = []
    
    # Revenue patterns
    patterns = [
        (r'₹?\s*(\d+(?:\.\d+)?)\s*(cr|lakh|million|billion)', 'revenue', 'currency'),
        (r'(\d+(?:\.\d+)?)\s*%', 'growth_rate', 'percent'),
        (r'(margin|profit)\s*:?\s*(\d+(?:\.\d+)?)\s*%', 'margin', 'percent'),
        (r'burn\s*(rate)?\s*:?\s*₹?\s*(\d+(?:\.\d+)?)', 'burn_rate', 'currency'),
        (r'runway\s*:?\s*(\d+)\s*(months|year)', 'runway', 'time'),
    ]
    
    for pattern, key, unit in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            value = match[0] if isinstance(match, tuple) else match
            fact = Fact(
                category="financials",
                key=key,
                value=value,
                page=page_num,
                section=section,
                source_type="text",
                confidence=0.85,
                raw_text=text[:200]
            )
            facts.append(fact)
    
    return facts


def normalize_currency(value: str) -> float:
    """Normalize currency values to a standard unit"""
    value = value.lower().strip()
    
    # Convert to numeric
    num_match = re.search(r'(\d+(?:\.\d+)?)', value)
    if not num_match:
        return 0.0
    
    num = float(num_match.group(1))
    
    if 'cr' in value or 'crore' in value:
        return num * 10000000  # 1 crore = 10 million
    elif 'lakh' in value:
        return num * 100000    # 1 lakh = 100,000
    elif 'billion' in value:
        return num * 1000000000
    elif 'million' in value:
        return num * 1000000
    
    return num