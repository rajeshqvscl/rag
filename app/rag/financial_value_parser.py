"""
Robust Financial Value Parser
==============================
Handles ALL financial number formats from Indian pitch decks including:
- Plus signs (60.0+ Cr)
- Complex Indian formats (42.0 Lakh Crores)
- Decimal suffixes
- Ranges (15-20 Cr)
- Approximations (~15 Cr)
- All Indian numbering (lakh, crore, etc.)
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum


class MetricType(Enum):
    """Semantic type of financial metric"""
    REVENUE = "revenue"
    ARR = "arr"
    MRR = "mrr"
    ORDERS = "orders"
    BOOKINGS = "bookings"
    PIPELINE = "pipeline"
    VALUATION = "valuation"
    RAISE = "raise_amount"
    TAM = "tam"
    SAM = "sam"
    SOM = "som"
    CUSTOMERS = "customers"
    GROWTH = "growth"
    MARGIN = "margin"
    BURN = "burn_rate"
    GRANT = "grant"
    PROJECTION = "projection"
    UNKNOWN = "unknown"


class TemporalType(Enum):
    """Temporal classification of metric"""
    HISTORICAL = "historical"
    CURRENT = "current"
    PROJECTION = "projection"
    PIPELINE = "pipeline"
    CONTRACT = "contract"
    GRANT = "grant"


@dataclass
class FinancialValue:
    """Canonical financial value object"""
    raw: str
    normalized: float
    currency: str
    scale: str  # Cr, Lakh, Mn, Bn, K, etc.
    metric_type: MetricType
    temporal_type: TemporalType
    confidence: float
    is_approximate: bool
    is_range: bool
    range_low: Optional[float] = None
    range_high: Optional[float] = None
    evidence_text: str = ""
    source_context: str = ""


class FinancialValueParser:
    """
    Robust parser for financial values from Indian pitch decks.
    """
    
    # Indian number multipliers
    INDIAN_SCALES = {
        'crore': 10_000_000,
        'cr': 10_000_000,
        'lakhs': 100_000,
        'lakh': 100_000,
        'lac': 100_000,
        'l': 100_000,
        'million': 1_000_000,
        'mn': 1_000_000,
        'm': 1_000_000,
        'billion': 1_000_000_000,
        'bn': 1_000_000_000,
        'b': 1_000_000_000,
        'thousand': 1_000,
        'k': 1_000,
    }
    
    # Currency symbols
    CURRENCY_SYMBOLS = {
        '₹': 'INR',
        '$': 'USD',
        'rs': 'INR',
        'inr': 'INR',
        'usd': 'USD',
    }
    
    # Metric type contextual keywords
    METRIC_CONTEXT = {
        'revenue': MetricType.REVENUE,
        'sales': MetricType.REVENUE,
        'income': MetricType.REVENUE,
        'arr': MetricType.ARR,
        'annual recurring': MetricType.ARR,
        'mrr': MetricType.MRR,
        'monthly recurring': MetricType.MRR,
        'orders': MetricType.ORDERS,
        'bookings': MetricType.BOOKINGS,
        'pipeline': MetricType.PIPELINE,
        'po': MetricType.PIPELINE,
        'loi': MetricType.PIPELINE,
        'valuation': MetricType.VALUATION,
        'valuation': MetricType.VALUATION,
        'raise': MetricType.RAISE,
        'funding': MetricType.RAISE,
        'tam': MetricType.TAM,
        'sam': MetricType.SAM,
        'som': MetricType.SOM,
        'customers': MetricType.CUSTOMERS,
        'users': MetricType.CUSTOMERS,
        'growth': MetricType.GROWTH,
        'margin': MetricType.MARGIN,
        'burn': MetricType.BURN,
        'grant': MetricType.GRANT,
        'subsidy': MetricType.GRANT,
    }
    
    # Temporal contextual keywords
    TEMPORAL_CONTEXT = {
        'historical': TemporalType.HISTORICAL,
        'audited': TemporalType.HISTORICAL,
        'fy21': TemporalType.HISTORICAL,
        'fy22': TemporalType.HISTORICAL,
        'fy23': TemporalType.HISTORICAL,
        'fy24': TemporalType.HISTORICAL,
        'current': TemporalType.CURRENT,
        'today': TemporalType.CURRENT,
        'run rate': TemporalType.CURRENT,
        'projection': TemporalType.PROJECTION,
        'forecast': TemporalType.PROJECTION,
        'target': TemporalType.PROJECTION,
        'expected': TemporalType.PROJECTION,
        'pipeline': TemporalType.PIPELINE,
        'loi': TemporalType.PIPELINE,
        'committed': TemporalType.PIPELINE,
        'contract': TemporalType.CONTRACT,
        'grant': TemporalType.GRANT,
    }
    
    def parse(self, value_str: str, context: str = "") -> FinancialValue:
        """
        Parse a financial value string into a canonical object.
        
        Args:
            value_str: Raw value string like "₹60.0+ Cr" or "150 Cr ARR"
            context: Surrounding text for semantic classification
            
        Returns:
            FinancialValue object with normalized value and metadata
        """
        if not value_str or not value_str.strip():
            return self._empty()
        
        raw = str(value_str).strip()
        
        # Check for ranges (e.g., "15-20 Cr")
        if '-' in raw and re.search(r'\d+\s*-\s*\d+', raw):
            return self._parse_range(raw, context)
        
        # Check for approximation (e.g., "~15 Cr", "about 15 Cr")
        is_approximate = any(marker in raw.lower() for marker in ['~', 'about', 'approximately', 'around', 'approx'])
        
        # Extract currency
        currency = 'INR'  # Default for Indian decks
        for sym, cur in self.CURRENCY_SYMBOLS.items():
            if sym in raw.lower():
                currency = cur
                break
        
        # Extract number and scale
        number, scale = self._extract_number_and_scale(raw)
        
        if number is None:
            return self._empty()
        
        # Normalize value
        multiplier = self.INDIAN_SCALES.get(scale.lower() if scale else '', 1.0)
        normalized = number * multiplier
        
        # Determine metric type from context
        metric_type = self._classify_metric(context)
        
        # Determine temporal type from context
        temporal_type = self._classify_temporal(context)
        
        # Calculate confidence
        confidence = self._calculate_confidence(raw, number, scale, context)
        
        return FinancialValue(
            raw=raw,
            normalized=normalized,
            currency=currency,
            scale=scale or 'units',
            metric_type=metric_type,
            temporal_type=temporal_type,
            confidence=confidence,
            is_approximate=is_approximate,
            is_range=False,
            source_context=context[:200] if context else ""
        )
    
    def _parse_range(self, value_str: str, context: str) -> FinancialValue:
        """Parse range values like '15-20 Cr'"""
        match = re.search(r'([\d.]+)\s*-\s*([\d.]+)\s*(\w+)', value_str.lower())
        if not match:
            return self._empty()
        
        low_num = float(match.group(1))
        high_num = float(match.group(2))
        scale = match.group(3)
        
        multiplier = self.INDIAN_SCALES.get(scale, 1.0)
        
        return FinancialValue(
            raw=value_str,
            normalized=(low_num + high_num) / 2 * multiplier,
            currency='INR',
            scale=scale,
            metric_type=self._classify_metric(context),
            temporal_type=self._classify_temporal(context),
            confidence=0.7,  # Lower confidence for ranges
            is_approximate=True,
            is_range=True,
            range_low=low_num * multiplier,
            range_high=high_num * multiplier,
            source_context=context[:200] if context else ""
        )
    
    def _extract_number_and_scale(self, value_str: str) -> tuple:
        """
        Extract numeric value and scale from string.
        Handles: "60.0+", "60 Cr", "42.0 Lakh", "5.5 Mn", etc.
        """
        # Clean the string - remove currency symbols for parsing
        cleaned = re.sub(r'[₹$£€]', '', value_str.strip())
        
        # Remove plus signs for parsing (but track them)
        has_plus = '+' in cleaned
        cleaned = cleaned.replace('+', '')
        
        # Extract number and unit
        # Pattern: number (optional decimal) followed by optional scale
        match = re.search(r'([\d,]+\.?\d*)\s*([a-zA-Z]*)$', cleaned.strip())
        
        if not match:
            # Try alternative pattern for just number
            num_match = re.search(r'([\d,]+\.?\d*)', cleaned)
            if num_match:
                num_str = num_match.group(1).replace(',', '')
                try:
                    number = float(num_str)
                    return (number, '')
                except:
                    return (None, None)
            return (None, None)
        
        num_str = match.group(1).replace(',', '')
        scale_str = match.group(2)
        
        try:
            number = float(num_str)
        except ValueError:
            return (None, None)
        
        # If has_plus, multiply by 1.1 as approximation
        if has_plus:
            number = number * 1.1
        
        return (number, scale_str)
    
    def _classify_metric(self, context: str) -> MetricType:
        """Classify the metric type based on context"""
        if not context:
            return MetricType.UNKNOWN
        
        context_lower = context.lower()
        
        # Check for specific metric indicators
        for keyword, metric in self.METRIC_CONTEXT.items():
            if keyword in context_lower:
                return metric
        
        # Check for ARR specifically (high confidence)
        if 'arr' in context_lower:
            return MetricType.ARR
        
        # Check for valuation vs raise
        if 'valuation' in context_lower or 'pre-money' in context_lower:
            return MetricType.VALUATION
        if 'raise' in context_lower or 'funding' in context_lower:
            return MetricType.RAISE
        
        # Check market sizes
        if 'tam' in context_lower:
            return MetricType.TAM
        if 'sam' in context_lower:
            return MetricType.SAM
        if 'som' in context_lower:
            return MetricType.SOM
        
        return MetricType.UNKNOWN
    
    def _classify_temporal(self, context: str) -> TemporalType:
        """Classify temporal type based on context"""
        if not context:
            return TemporalType.UNKNOWN
        
        context_lower = context.lower()
        
        for keyword, temporal in self.TEMPORAL_CONTEXT.items():
            if keyword in context_lower:
                return temporal
        
        return TemporalType.UNKNOWN
    
    def _calculate_confidence(self, raw: str, number: float, scale: str, context: str) -> float:
        """Calculate confidence score for the parsed value"""
        confidence = 0.5  # Base confidence
        
        # Higher confidence with explicit unit
        if scale and scale.lower() in ['cr', 'lakh', 'mn', 'bn']:
            confidence += 0.3
        
        # Higher confidence with currency symbol
        if any(s in raw for s in ['₹', '$']):
            confidence += 0.15
        
        # Lower confidence for approximations
        if any(marker in raw.lower() for marker in ['~', 'about', 'approximately']):
            confidence -= 0.2
        
        # Higher confidence with clear context
        if context and any(k in context.lower() for k in ['revenue', 'arr', 'customers', 'valuation']):
            confidence += 0.15
        
        # Lower confidence if number seems unrealistic
        if number and number > 0:
            # Very large or very small numbers need more context
            if number > 100000000000:  # > 10000 Cr
                confidence -= 0.1
            elif number < 100:  # Very small, probably needs unit
                confidence -= 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _empty(self) -> FinancialValue:
        """Return an empty financial value"""
        return FinancialValue(
            raw="",
            normalized=0.0,
            currency="",
            scale="",
            metric_type=MetricType.UNKNOWN,
            temporal_type=TemporalType.UNKNOWN,
            confidence=0.0,
            is_approximate=False,
            is_range=False
        )
    
    def parse_batch(self, values: List[str], contexts: List[str] = None) -> List[FinancialValue]:
        """Parse multiple values with optional contexts"""
        results = []
        for i, value in enumerate(values):
            ctx = contexts[i] if contexts and i < len(contexts) else ""
            results.append(self.parse(value, ctx))
        return results


# Singleton instance
_parser = FinancialValueParser()


def parse_financial_value(value_str: str, context: str = "") -> FinancialValue:
    """Convenience function to parse a financial value"""
    return _parser.parse(value_str, context)


def parse_financial_batch(values: List[str], contexts: List[str] = None) -> List[FinancialValue]:
    """Convenience function to parse multiple values"""
    return _parser.parse_batch(values, contexts)