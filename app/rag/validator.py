import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ValidationRule(Enum):
    REJECT = "reject"
    FLAG = "flag"
    WARN = "warn"
    ACCEPT = "accept"


@dataclass
class ValidationResult:
    passed: bool
    rule: str
    message: str
    severity: str
    suggested_value: Optional[Any] = None


class FactValidator:
    def __init__(self):
        self.rules = self._initialize_rules()
        self.stage_thresholds = {
            "pre-seed": {"min_revenue": 0, "max_revenue": 5e7},
            "seed": {"min_revenue": 0, "max_revenue": 1e8},
            "series_a": {"min_revenue": 1e5, "max_revenue": 1e9},
            "series_b": {"min_revenue": 1e7, "max_revenue": 1e10},
            "series_c": {"min_revenue": 1e8, "max_revenue": 1e12}
        }
    
    def _initialize_rules(self) -> Dict[str, Dict]:
        return {
            "percentage_format": {
                "check": lambda v: "%" not in str(v) or self._is_valid_percentage(v),
                "rule": ValidationRule.FLAG,
                "message": "Percentage values should be numeric (e.g., '25' not '25%')"
            },
            "currency_format": {
                "check": lambda v: True,
                "rule": ValidationRule.FLAG,
                "message": "Check currency format - mixed characters detected"
            },
            "positive_numbers": {
                "check": lambda v: self._is_positive_number(v),
                "rule": ValidationRule.FLAG,
                "message": "Expected positive number, got non-numeric value"
            },
            "no_axis_labels": {
                "check": lambda v: not self._looks_like_axis_label(v),
                "rule": ValidationRule.FLAG,
                "message": "Value may be an axis label rather than actual data"
            }
        }
    
    def _safe_parse_float(self, value: str) -> Optional[float]:
        """Safely parse a cleaned number string to float, guarding against orphan decimals."""
        if not value:
            return None
        s = re.sub(r"[^\d.]", "", value)
        if s in ("", ".", "-.", "+."):
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    def _is_valid_percentage(self, value: str) -> bool:
        num = self._safe_parse_float(value)
        return num is not None and 0 <= num <= 1000
    
    def _in_reasonable_range(self, value: str, min_val: float, max_val: float) -> bool:
        num = self._parse_number(value)
        if num is None:
            return True
        return min_val <= num <= max_val
    
    def _is_positive_number(self, value: str) -> bool:
        num = self._parse_number(value)
        return num is not None and num >= 0
    
    def _looks_like_axis_label(self, value: str) -> bool:
        axis_keywords = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
                        "q1", "q2", "q3", "q4", "year", "month", "week", "day",
                        "january", "february", "march", "april", "june", "july", "august",
                        "september", "october", "november", "december"]
        return value.lower() in axis_keywords
    
    def _parse_number(self, value: str) -> Optional[float]:
        try:
            from app.rag.number_utils import parse_indian_number
            result = parse_indian_number(value)
            if result != 0.0:
                return result
            # Raw float fallback with safe parsing
            cleaned = value.replace(",", "").replace("₹", "").replace("$", "").replace(" ", "")
            return self._safe_parse_float(cleaned)
        except:
            return None
    
    def validate_metric(self, name: str, value: Any, context: Dict = None) -> ValidationResult:
        if context is None:
            context = {}
        
        for rule_name, rule in self.rules.items():
            if not rule["check"](value):
                return ValidationResult(
                    passed=False,
                    rule=rule_name,
                    message=rule["message"],
                    severity=rule["rule"].value
                )
        
        if name == "revenue":
            result = self._validate_revenue(value, context)
            if result:
                return result
        
        if name == "growth_rate":
            result = self._validate_growth(value, context)
            if result:
                return result
        
        if name == "valuation":
            result = self._validate_valuation(value, context)
            if result:
                return result
        
        return ValidationResult(passed=True, rule="default", message="Metric validated", severity="accept")
    
    def _validate_revenue(self, value: str, context: Dict) -> Optional[ValidationResult]:
        num = self._parse_number(value)
        if num is None:
            return None
        
        if num < 10000:
            return ValidationResult(
                passed=False,
                rule="revenue_too_low",
                message=f"Revenue {value} seems too low for a pitch deck",
                severity="flag",
                suggested_value=None
            )
        
        if num > 1e12:
            return ValidationResult(
                passed=False,
                rule="revenue_too_high",
                message=f"Revenue {value} exceeds reasonable range",
                severity="flag"
            )
        
        stage = context.get("stage", "").lower()
        if stage in self.stage_thresholds:
            thresholds = self.stage_thresholds[stage]
            if num > thresholds["max_revenue"]:
                return ValidationResult(
                    passed=False,
                    rule="revenue_mismatch_stage",
                    message=f"Revenue inconsistent with {stage} stage",
                    severity="warn"
                )
        
        return None
    
    def _validate_growth(self, value: str, context: Dict) -> Optional[ValidationResult]:
        num = self._parse_number(value)
        if num is None:
            return None
        
        if num > 10000:
            return ValidationResult(
                passed=False,
                rule="growth_unrealistic",
                message=f"Growth rate {value}% seems unrealistic",
                severity="flag"
            )
        
        return None
    
    def _validate_valuation(self, value: str, context: Dict) -> Optional[ValidationResult]:
        num = self._parse_number(value)
        if num is None:
            return None
        
        if num < 1e6:
            return ValidationResult(
                passed=False,
                rule="valuation_too_low",
                message=f"Valuation {value} seems too low",
                severity="warn"
            )
        
        return None
    
    def validate_fact_registry(self, registry: Any) -> Dict[str, List[ValidationResult]]:
        results = {"passed": [], "failed": [], "warnings": []}
        
        try:
            facts = registry.get_all_facts() if hasattr(registry, 'get_all_facts') else []
        except:
            facts = []
        
        for fact in facts:
            result = self.validate_metric(fact.name, fact.value, {"stage": context.get("stage", "")})
            
            if result.passed:
                results["passed"].append(result)
            elif result.severity == "reject":
                results["failed"].append(result)
            else:
                results["warnings"].append(result)
        
        return results
    
    def normalize_value(self, value: str, metric_type: str) -> Tuple[Any, float]:
        """Normalize value and return (normalized, confidence)"""
        confidence = 1.0
        
        if metric_type == "revenue":
            num = self._parse_number(value)
            if num:
                normalized = f"Rs {num/1e7:.2f} Cr"
                if "cr" in value.lower() or "crore" in value.lower():
                    confidence = 0.95
                else:
                    confidence = 0.7
                return normalized, confidence
        
        if metric_type == "percentage":
            num = self._parse_number(value)
            if num:
                return f"{num}%", 0.95
        
        return value, 0.8


def validate_table_data(tables: List[Dict]) -> List[Dict]:
    """Validate extracted table data"""
    validator = FactValidator()
    validated_tables = []
    
    for table in tables:
        table_text = " ".join(table.get("headers", [])) + " " + " ".join([" ".join(row) for row in table.get("rows", [])])
        
        validation = {
            "page": table.get("page"),
            "index": table.get("index"),
            "row_count": table.get("row_count", 0),
            "confidence": table.get("confidence", 0),
            "issues": [],
            "is_valid": True
        }
        
        if table.get("row_count", 0) < 2:
            validation["issues"].append("Too few rows")
            validation["is_valid"] = False
        
        if not table.get("headers"):
            validation["issues"].append("No headers detected")
            validation["is_valid"] = False
        
        if "%" in table_text:
            validation["issues"].append("Contains percentage symbols - may need normalization")
        
        validated_tables.append(validation)
    
    return validated_tables


def validate_page_data(page: Dict) -> Dict:
    """Validate page extraction results"""
    validation = {
        "page_num": page.get("page"),
        "text_length": len(page.get("text", "")),
        "tables_found": len(page.get("tables", [])),
        "sections_detected": page.get("sections", []),
        "issues": [],
        "score": 0
    }
    
    text = page.get("text", "")
    if len(text) < 50:
        validation["issues"].append("Very short text - may have extraction issues")
    
    if len(text) > 50000:
        validation["issues"].append("Very long text - may need chunking")
    
    if not page.get("sections"):
        validation["issues"].append("No sections detected")
    
    score = 100
    score -= len(validation["issues"]) * 15
    validation["score"] = max(score, 0)
    
    return validation