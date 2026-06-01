"""
Validation Engine - Rule-based fact validation
Validates extracted facts against business rules before storage
"""
from typing import Dict, List, Any, Optional, Tuple
import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of fact validation"""
    valid: bool
    confidence_adjustment: float
    reason: str
    suggested_value: Optional[Any] = None


class ValidationEngine:
    """
    Validates extracted facts against business rules
    Prevents storing invalid/contradictory data
    """
    
    # Funding stage thresholds
    STAGE_THRESHOLDS = {
        "pre_seed": {"min_revenue": 0, "max_revenue": 100000, "currency": "INR"},
        "seed": {"min_revenue": 0, "max_revenue": 500000, "currency": "INR"},
        "series_a": {"min_revenue": 500000, "max_revenue": 10000000, "currency": "INR"},
        "series_b": {"min_revenue": 5000000, "max_revenue": 100000000, "currency": "INR"},
    }
    
    def validate_fact(self, fact: Dict, context: Dict = None) -> ValidationResult:
        """
        Validate a fact against rules
        
        Args:
            fact: {"key": str, "value": Any, "category": str}
            context: Additional context like funding_stage, sector
        
        Returns:
            ValidationResult
        """
        key = fact.get("key", "")
        value = fact.get("value")
        category = fact.get("category", "general")
        
        context = context or {}
        stage = context.get("funding_stage", "seed")
        
        # Rule 1: Check for percentage in revenue (likely axis label, not real data)
        if key == "revenue" and isinstance(value, str):
            if "%" in str(value):
                return ValidationResult(
                    valid=False,
                    confidence_adjustment=-0.3,
                    reason="Revenue contains '%' - likely chart axis, not actual value"
                )
        
        # Rule 2: Validate revenue ranges for funding stage
        if key == "revenue":
            result = self._validate_revenue_scale(value, stage)
            if not result.valid:
                return result
        
        # Rule 3: Very small revenue with large claims
        if key == "revenue" and isinstance(value, (int, float)):
            if value < 10000 and context.get("valuation") and context["valuation"] > 10000000:
                return ValidationResult(
                    valid=False,
                    confidence_adjustment=-0.2,
                    reason="Revenue/Valuation mismatch suggests unrealistic metrics"
                )
        
        # Rule 4: Growth rate validation
        if key == "growth_rate" and isinstance(value, (int, float)):
            if value > 500:
                return ValidationResult(
                    valid=False,
                    confidence_adjustment=-0.4,
                    reason="Growth rate >500% is likely erroneous"
                )
        
        # Rule 5: Team size validation
        if key == "team_size":
            if isinstance(value, (int, float)):
                if value > 1000:
                    return ValidationResult(
                        valid=False,
                        confidence_adjustment=-0.3,
                        reason="Team size >1000 unrealistic for early stage"
                    )
        
        return ValidationResult(
            valid=True,
            confidence_adjustment=0.0,
            reason="Validated"
        )
    
    def _validate_revenue_scale(self, value: Any, stage: str) -> ValidationResult:
        """Validate revenue is reasonable for funding stage"""
        if isinstance(value, str):
            num_match = re.search(r'(\d+(?:\.\d+)?)', value.replace(",", ""))
            if num_match:
                value = float(num_match.group(1))
            else:
                return ValidationResult(valid=True, confidence_adjustment=0, reason="Cannot parse revenue")
        
        if not isinstance(value, (int, float)):
            return ValidationResult(valid=True, confidence_adjustment=0, reason="Non-numeric revenue")
        
        threshold = self.STAGE_THRESHOLDS.get(stage, self.STAGE_THRESHOLDS["seed"])
        
        if value < threshold["min_revenue"]:
            return ValidationResult(
                valid=False,
                confidence_adjustment=-0.2,
                reason=f"Revenue below expected range for {stage}"
            )
        
        if value > threshold["max_revenue"] * 10:
            return ValidationResult(
                valid=False,
                confidence_adjustment=-0.3,
                reason=f"Revenue exceeds reasonable range for {stage}"
            )
        
        return ValidationResult(valid=True, confidence_adjustment=0, reason="Revenue scale OK")
    
    def cross_validate(self, facts: List[Dict]) -> List[Dict]:
        """
        Cross-validate multiple facts for consistency
        
        Returns:
            List of facts with added cross_validation_notes
        """
        validated = []
        
        # Collect all revenue claims
        revenue_facts = [f for f in facts if f.get("key") == "revenue"]
        
        # Collect all growth claims
        growth_facts = [f for f in facts if f.get("key") == "growth_rate"]
        
        for fact in facts:
            notes = []
            
            # Check revenue consistency
            if fact.get("key") == "revenue":
                for other_rev in revenue_facts:
                    if other_rev != fact and abs(float(str(other_rev.get("value", 0)).replace(",", "")) - 
                                                 float(str(fact.get("value", 0)).replace(",", ""))) > 0.1:
                        notes.append(f"Conflicting revenue: {other_rev.get('value')} on page {other_rev.get('page')}")
            
            # Check growth/revenue consistency
            if fact.get("key") == "growth_rate":
                if revenue_facts:
                    if float(str(fact.get("value", 0))) > 100 and not revenue_facts:
                        notes.append("High growth without confirmed revenue - lower confidence")
            
            fact["cross_validation_notes"] = notes
            validated.append(fact)
        
        return validated
    
    def get_confidence_score(self, fact: Dict, context: Dict = None) -> float:
        """
        Calculate confidence score for a fact
        
        Returns:
            0.0 to 1.0 confidence
        """
        base_confidence = fact.get("confidence", 0.8)
        
        # Source type adjustment
        source_type = fact.get("source_type", "text")
        source_multipliers = {
            "table": 1.0,
            "chart": 0.7,
            "text": 0.85,
            "image": 0.6
        }
        
        adjustment = source_multipliers.get(source_type, 0.8)
        
        # Validation result adjustment
        validation = self.validate_fact(fact, context)
        adjustment *= (1 + validation.confidence_adjustment)
        
        return max(0.0, min(1.0, base_confidence * adjustment))


class FactDeduplicator:
    """
    Deduplicates facts from multiple sources
    """
    
    def deduplicate(self, facts: List[Dict]) -> List[Dict]:
        """Remove duplicate facts, keeping highest confidence"""
        seen = {}
        
        def safe_confidence(value):
            if isinstance(value, str):
                try:
                    return int(value)
                except:
                    return 0
            return value if isinstance(value, (int, float)) else 0
        
        for fact in facts:
            key = f"{fact.get('key')}_{fact.get('value')}"
            
            if key not in seen:
                seen[key] = fact
            else:
                # Keep higher confidence
                fact_conf = safe_confidence(fact.get("confidence"))
                seen_conf = safe_confidence(seen[key].get("confidence"))
                if fact_conf > seen_conf:
                    seen[key] = fact
        
        return list(seen.values())
    
    def merge_contradictions(self, facts: List[Dict]) -> Dict[str, Any]:
        """
        Merge contradictory facts with conflict notes
        
        Returns:
            Merged fact with contradiction annotations
        """
        by_key = {}
        
        for fact in facts:
            key = fact.get("key")
            if key not in by_key:
                by_key[key] = []
            by_key[key].append(fact)
        
        merged = {}
        
        for key, fact_list in by_key.items():
            if len(fact_list) == 1:
                merged[key] = fact_list[0]
            else:
                # Multiple values - flag as conflict
                merged[key] = {
                    "value": fact_list[0].get("value"),
                    "conflict": True,
                    "alternatives": [f.get("value") for f in fact_list],
                    "sources": [f"page {f.get('page')}" for f in fact_list],
                    "confidence": max(f.get("confidence", 0) for f in fact_list) * 0.7
                }
        
        return merged