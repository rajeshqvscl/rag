"""
Hierarchical Domain Classifier for Pitch Deck Analysis
=======================================================
Classifies text segments into financial domains with multi-level reasoning.
Uses hierarchical taxonomy for accurate metric identification.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class DomainLevel(Enum):
    """Hierarchical domain levels"""
    HIGH_LEVEL = "high_level"  # Revenue, Growth, Market, etc.
    SUB_DOMAIN = "sub_domain"  # ARR, MRR, YoY, etc.
    SPECIFIC = "specific"      # ARR Q1 2024, YoY Growth, etc.


@dataclass
class DomainMatch:
    """A single domain match with confidence"""
    level: DomainLevel
    domain: str
    sub_domain: str
    confidence: float
    evidence: str
    keywords: List[str] = field(default_factory=list)
    
    def __repr__(self):
        return f"DomainMatch({self.domain}.{self.sub_domain} @ {self.confidence:.2f})"


class HierarchicalDomainClassifier:
    """
    Multi-level domain classifier for pitch deck text.
    Uses keyword matching + contextual reasoning for domain classification.
    """
    
    # High-level domains with their sub-domains
    DOMAIN_TAXONOMY = {
        "revenue": {
            "arr": ["arr", "annual recurring revenue", "annual recurring"],
            "mrr": ["mrr", "monthly recurring revenue", "monthly recurring"],
            "revenue_total": ["revenue", "sales", "total revenue", "total sales", "income"],
            "bookings": ["bookings", "order value", "order volume"],
            "run_rate": ["run rate", "annualized"],
        },
        "growth": {
            "growth_rate": ["growth", "growth rate", "increase", "growth%"],
            "yoy": ["yoy", "year over year", "year-on-year"],
            "mom": ["mom", "month over month", "month-on-month"],
            "qoq": ["qoq", "quarter over quarter"],
        },
        "customer": {
            "customers_total": ["customers", "clients", "users", "patients", "merchants"],
            "customers_new": ["new customers", "new users", "acquisition"],
            "customers_retention": ["retention", "churn", "repeat"],
            "ltv": ["ltv", "lifetime value", "customer lifetime value"],
            "cac": ["cac", "customer acquisition cost", "acquisition cost"],
            "ltv_cac": ["ltv:cac", "ltv/cac", "lifetime value to cac"],
        },
        "market": {
            "tam": ["tam", "total addressable market", "total market"],
            "sam": ["sam", "serviceable available market", "addressable market"],
            "som": ["som", "serviceable obtainable market", "obtainable market"],
            "market_share": ["market share", "share of market", "market penetration"],
        },
        "financial_health": {
            "margin": ["margin", "gross margin", "net margin", "ebitda margin"],
            "burn_rate": ["burn", "burn rate", "cash burn", "monthly burn"],
            "runway": ["runway", "months of runway", "cash runway"],
            "profit": ["profit", "profitability", "net profit", "profit margin"],
            "ebitda": ["ebitda", "operating profit"],
            "cash": ["cash", "cash position", "bank balance", "cash in hand"],
        },
        "fundraising": {
            "raise_amount": ["raise", "funding", "investment", "seed", "series", "round"],
            "valuation": ["valuation", "valued at", "pre-money", "post-money"],
            "lead_investor": ["lead investor", "investor", "backed by", "venture"],
        },
        "operations": {
            "employees": ["employees", "team size", "headcount", "staff"],
            "partners": ["partners", "partnerships", "alliances"],
            "locations": ["locations", "cities", "presence", "markets"],
            "orders": ["orders", "transactions", "volume"],
        },
        "projection": {
            "projected_revenue": ["projected revenue", "forecast revenue", "revenue target"],
            "projected_arr": ["projected arr", "arr target", "arr forecast"],
            "projected_customers": ["projected customers", "customer target"],
        },
    }
    
    # Pattern-based extractors for specific formats
    PATTERN_CLASSIFIERS = {
        "arr": [
            (r'\barr\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "arr"),
            (r'\bannual\s+recurring\s+revenue\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "arr"),
            (r'([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)\s*arr\b', "arr"),
        ],
        "mrr": [
            (r'\bmrr\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "mrr"),
            (r'\bmonthly\s+recurring\s+revenue\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "mrr"),
        ],
        "valuation": [
            (r'\bvaluation\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "valuation"),
            (r'\bvalued\s+at\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "valuation"),
            (r'([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)\s*valuation\b', "valuation"),
            (r'pre[-\s]money[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "valuation"),
        ],
        "raise": [
            (r'\braise\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "raise_amount"),
            (r'\bfunding\b[:\s]*([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)', "raise_amount"),
            (r'([\d,.\s]+(?:Cr|Mn|Bn|Lakh)?)\s*funding\s*round\b', "raise_amount"),
        ],
    }
    
    # Temporal indicators
    TEMPORAL_PATTERNS = {
        "current": [r'\bcurrent\b', r'\btoday\b', r'\bas\s+of\b', r'\bnow\b'],
        "historical": [r'\bfy\d{2}\b', r'\bfy\s*\d{4}\b', r'\b20\d{2}\b', r'\bprevious\s+year\b', r'\b(last|previous)\s+year\b'],
        "projection": [r'\bproject(?:ed|ion)?\b', r'\bforecast\b', r'\btarget\b', r'\bexpect(?:ed|ation)?\b', r'\baim(?:ing|ed)?\b'],
        "pipeline": [r'\bpipeline\b', r'\bloi\b', r'\bpo\b', r'\bcommitted\b'],
    }
    
    def classify(self, text: str, context: str = "") -> List[DomainMatch]:
        """
        Classify text into hierarchical domains.
        
        Args:
            text: The text segment to classify
            context: Surrounding context for additional signals
            
        Returns:
            List of domain matches sorted by confidence
        """
        if not text:
            return []
        
        combined_text = f"{context} {text}".lower()
        matches = []
        
        # 1. High-level domain matching
        for domain, sub_domains in self.DOMAIN_TAXONOMY.items():
            for sub_domain, keywords in sub_domains.items():
                confidence, evidence, matched_keywords = self._match_keywords(
                    combined_text, keywords
                )
                if confidence > 0:
                    matches.append(DomainMatch(
                        level=DomainLevel.SUB_DOMAIN,
                        domain=domain,
                        sub_domain=sub_domain,
                        confidence=confidence,
                        evidence=evidence,
                        keywords=matched_keywords
                    ))
        
        # 2. Pattern-based classification
        for key, patterns in self.PATTERN_CLASSIFIERS.items():
            for pattern, sub_domain in patterns:
                match = re.search(pattern, combined_text)
                if match:
                    # Find parent domain for this sub_domain
                    parent_domain = self._get_parent_domain(sub_domain)
                    if parent_domain:
                        # Check if we already have this match with higher confidence
                        existing = next(
                            (m for m in matches 
                             if m.sub_domain == sub_domain and m.confidence > 0.8),
                            None
                        )
                        if not existing:
                            matches.append(DomainMatch(
                                level=DomainLevel.SPECIFIC,
                                domain=parent_domain,
                                sub_domain=sub_domain,
                                confidence=0.85,
                                evidence=match.group(0),
                                keywords=[sub_domain]
                            ))
        
        # 3. Sort by confidence and deduplicate
        matches = self._deduplicate_and_sort(matches)
        
        return matches
    
    def classify_with_temporal(self, text: str, context: str = "") -> Tuple[List[DomainMatch], str]:
        """
        Classify text and also determine temporal type.
        
        Returns:
            Tuple of (domain matches, temporal type)
        """
        matches = self.classify(text, context)
        temporal = self._classify_temporal(f"{context} {text}")
        
        return matches, temporal
    
    def _match_keywords(self, text: str, keywords: List[str]) -> Tuple[float, str, List[str]]:
        """Match keywords and return confidence, evidence, and matched keywords"""
        matched = []
        evidence = ""
        
        for keyword in keywords:
            if keyword in text:
                matched.append(keyword)
                # Find surrounding context for evidence
                idx = text.find(keyword)
                start = max(0, idx - 30)
                end = min(len(text), idx + len(keyword) + 30)
                evidence = text[start:end]
        
        if not matched:
            return 0.0, "", []
        
        # Calculate confidence based on keyword density
        confidence = min(0.9, 0.3 + (len(matched) * 0.2))
        
        return confidence, evidence, matched
    
    def _get_parent_domain(self, sub_domain: str) -> Optional[str]:
        """Find the parent domain for a sub-domain"""
        for domain, sub_domains in self.DOMAIN_TAXONOMY.items():
            if sub_domain in sub_domains:
                return domain
        return None
    
    def _classify_temporal(self, text: str) -> str:
        """Determine temporal type from text"""
        text_lower = text.lower()
        
        for temporal_type, patterns in self.TEMPORAL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return temporal_type
        
        return "unknown"
    
    def _deduplicate_and_sort(self, matches: List[DomainMatch]) -> List[DomainMatch]:
        """Remove duplicates and sort by confidence"""
        seen = set()
        unique_matches = []
        
        for match in matches:
            key = (match.domain, match.sub_domain)
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)
        
        return sorted(unique_matches, key=lambda m: m.confidence, reverse=True)
    
    def get_primary_domain(self, text: str, context: str = "") -> Optional[DomainMatch]:
        """Get only the primary (highest confidence) domain"""
        matches = self.classify(text, context)
        return matches[0] if matches else None


# Singleton instance
_classifier = HierarchicalDomainClassifier()


def classify_text(text: str, context: str = "") -> List[DomainMatch]:
    """Convenience function to classify text"""
    return _classifier.classify(text, context)


def classify_with_temporal(text: str, context: str = "") -> Tuple[List[DomainMatch], str]:
    """Convenience function to classify with temporal type"""
    return _classifier.classify_with_temporal(text, context)


def get_primary_domain(text: str, context: str = "") -> Optional[DomainMatch]:
    """Convenience function to get primary domain"""
    return _classifier.get_primary_domain(text, context)