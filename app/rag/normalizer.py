"""
Comprehensive Normalization Layer
Handles currency formatting, unit conversions, and data standardization
"""
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class NormalizedValue:
    original: str
    normalized: str
    format_type: str
    confidence: float
    source_info: str


class CurrencyNormalizer:
    """
    Normalizes various currency formats to standard representation
    Supports INR (₹, Rs), USD ($), and other major currencies
    """

    INR_MULTIPLIERS = {
        "cr": 1e7,
        "crore": 1e7,
        "crores": 1e7,
        "l": 1e5,
        "lakh": 1e5,
        "lakhs": 1e5,
        "k": 1e3,
        "thousand": 1e3,
        "m": 1e6,
        "million": 1e6,
        "mn": 1e6,
        "b": 1e9,
        "bn": 1e9,
        "billion": 1e9
    }

    USD_MULTIPLIERS = {
        "k": 1e3,
        "thousand": 1e3,
        "m": 1e6,
        "mn": 1e6,
        "million": 1e6,
        "b": 1e9,
        "bn": 1e9,
        "billion": 1e9
    }

    @classmethod
    def normalize(cls, value: str, target_currency: str = "INR") -> Optional[NormalizedValue]:
        """
        Normalize a currency value to standard format

        Args:
            value: Currency string (e.g., "₹5.1 Cr", "$2 Mn", "200 Lakhs")
            target_currency: Target currency for normalization

        Returns:
            NormalizedValue with normalized representation
        """
        if not value or not isinstance(value, str):
            return None

        original = value.strip()
        value_lower = original.lower()

        inr_indicators = ["₹", "rs", "inr", "rupee"]
        usd_indicators = ["$", "usd", "dollar"]

        has_inr = any(ind in value_lower for ind in inr_indicators)
        has_usd = any(ind in value_lower for ind in usd_indicators)
        if has_inr and has_usd:
            has_inr = False
            original = original.replace("₹", "").replace("rs", "").replace("INR", "").strip()
            value_lower = original.lower()
        currency_type = "INR" if has_inr else "USD" if has_usd else "UNKNOWN"

        number_match = re.search(r'([\d,]+\.?\d*)', original.replace(",", ""))
        if not number_match:
            return NormalizedValue(original, original, "unknown", 0.0, "")

        number_str = number_match.group(1)
        try:
            number = float(number_str)
        except ValueError:
            return NormalizedValue(original, original, "invalid", 0.0, "")

        multipliers = cls.INR_MULTIPLIERS if currency_type == "INR" else cls.USD_MULTIPLIERS

        for suffix, multiplier in multipliers.items():
            if suffix in value_lower:
                if currency_type == "INR":
                    normalized = f"₹{number:.2f} Cr" if multiplier >= 1e7 else f"₹{number:.2f} Lakhs"
                else:
                    normalized = f"${number:.2f} Mn" if multiplier >= 1e6 else f"${number:.2f} K"

                return NormalizedValue(
                    original=original,
                    normalized=normalized,
                    format_type=currency_type,
                    confidence=0.95,
                    source_info=f"Extracted from {currency_type} format"
                )

        if currency_type == "INR":
            if number >= 1e7:
                normalized = f"₹{number / 1e7:.2f} Cr"
            elif number >= 1e5:
                normalized = f"₹{number / 1e5:.2f} Lakhs"
            elif number >= 1e3:
                normalized = f"₹{number / 1e3:.2f} K"
            else:
                normalized = f"₹{number:.2f}"
        elif currency_type == "USD":
            if number >= 1e9:
                normalized = f"${number / 1e9:.2f} Bn"
            elif number >= 1e6:
                normalized = f"${number / 1e6:.2f} Mn"
            elif number >= 1e3:
                normalized = f"${number / 1e3:.2f} K"
            else:
                normalized = f"${number:.2f}"
        else:
            normalized = original

        return NormalizedValue(
            original=original,
            normalized=normalized,
            format_type=currency_type,
            confidence=0.8,
            source_info="Inferred currency format"
        )

    @classmethod
    def format_for_display(cls, value: str, style: str = "compact") -> str:
        """
        Format currency value for display

        Args:
            value: Currency string
            style: "compact" (₹5.1 Cr) or "full" (₹5,100,000)
        """
        normalized = cls.normalize(value)
        if not normalized:
            return value

        return normalized.normalized


class NumberNormalizer:
    """
    Normalizes various number formats including percentages, growth rates, etc.
    """

    @staticmethod
    def normalize_percentage(value: str) -> Optional[NormalizedValue]:
        """Normalize percentage values"""
        if not value:
            return None

        match = re.search(r'([\d.]+)\s*%', str(value))
        if match:
            num = float(match.group(1))
            if num > 1000:
                return NormalizedValue(value, f"{num}%", "percentage", 0.3, "Suspiciously high percentage")
            return NormalizedValue(value, f"{num:.1f}%", "percentage", 0.95, "")
        return None

    @staticmethod
    def normalize_growth_rate(value: str) -> Optional[NormalizedValue]:
        """Normalize growth rate values"""
        if not value:
            return None

        value_lower = str(value).lower()

        patterns = [
            (r'(\d+(?:\.\d+)?)\s*%', "percentage"),
            (r'(\d+)x', "multiple"),
            (r'growth[:\s]+(\d+(?:\.\d+)?)', "percentage"),
            (r'yoy[:\s]+(\d+(?:\.\d+)?)', "percentage")
        ]

        for pattern, format_type in patterns:
            match = re.search(pattern, value_lower)
            if match:
                num = float(match.group(1))
                if format_type == "multiple":
                    normalized = f"{int(num)}x"
                else:
                    normalized = f"{num:.1f}%"

                confidence = 0.9 if num < 500 else 0.5
                return NormalizedValue(
                    original=str(value),
                    normalized=normalized,
                    format_type=format_type,
                    confidence=confidence,
                    source_info=""
                )

        return None

    @staticmethod
    def normalize_ordinal(value: str) -> Optional[NormalizedValue]:
        """Normalize ordinal numbers (1st, 2nd, etc.)"""
        if not value:
            return None

        match = re.search(r'(\d+)(st|nd|rd|th)', str(value))
        if match:
            num = int(match.group(1))
            return NormalizedValue(
                original=str(value),
                normalized=str(num),
                format_type="ordinal",
                confidence=0.95,
                source_info=""
            )

        return None


class StageNormalizer:
    """
    Normalizes funding stage labels
    """

    STAGE_MAPPINGS = {
        "pre-seed": ["pre seed", "preseed", "preseries", "pre-series a", "angel"],
        "seed": ["seed", "seed round", "seed stage"],
        "series a": ["series a", "seriesa", "series-a", "seriesa"],
        "series b": ["series b", "seriesb", "series-b", "seriesb"],
        "series c": ["series c", "seriesc", "series-c"],
        "growth": ["growth", "growth stage", "late stage"],
        "series unknown": ["series", "round", "funding round"]
    }

    @classmethod
    def normalize(cls, value: str) -> Optional[NormalizedValue]:
        """Normalize funding stage"""
        if not value:
            return None

        value_lower = str(value).lower().strip()

        for standard_stage, variants in cls.STAGE_MAPPINGS.items():
            if value_lower in variants or value_lower == standard_stage:
                return NormalizedValue(
                    original=str(value),
                    normalized=standard_stage.upper(),
                    format_type="stage",
                    confidence=0.95,
                    source_info=""
                )

        return None


class CompanyNormalizer:
    """
    Normalizes company names and handles duplicates
    """

    COMMON_SUFFIXES = [
        "Pvt Ltd", "Private Limited", "Ltd", "Inc", "LLC", "Corp",
        "LLP", "Limited", "Private", "Public", "Technologies",
        "Solutions", "Services", "Systems", "Labs", "Ventures"
    ]

    @classmethod
    def normalize(cls, name: str) -> str:
        """Normalize company name"""
        if not name:
            return ""

        normalized = name.strip()

        for suffix in cls.COMMON_SUFFIXES:
            if suffix.lower() in normalized.lower():
                normalized = re.sub(rf',?\s*{re.escape(suffix)}\s*$', '', normalized, flags=re.IGNORECASE)

        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = normalized.strip()

        return normalized

    @classmethod
    def is_similar(cls, name1: str, name2: str) -> bool:
        """Check if two company names are similar"""
        n1 = cls.normalize(name1).lower()
        n2 = cls.normalize(name2).lower()

        if n1 == n2:
            return True

        common_words = set(n1.split()).intersection(set(n2.split()))
        if len(common_words) >= 2:
            return True

        return False


class TextNormalizer:
    """
    General text normalization utilities
    """

    @staticmethod
    def clean_ocr_artifacts(text: str) -> str:
        """Remove common OCR artifacts"""
        if not text:
            return ""

        text = re.sub(r'([a-z])\.([A-Z])', r'\1. \2', text)

        text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)

        text = re.sub(r'\.{2,}', '.', text)

        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize all whitespace to single spaces"""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def remove_duplicates(text: str, word_window: int = 3) -> str:
        """Remove duplicate words within a window"""
        if not text:
            return ""

        words = text.split()
        cleaned = []
        seen_recent = []

        for word in words:
            if word.lower() not in seen_recent:
                cleaned.append(word)
            seen_recent.append(word.lower())
            if len(seen_recent) > word_window:
                seen_recent.pop(0)

        return ' '.join(cleaned)


class ComprehensiveNormalizer:
    """
    Main entry point for all normalization needs
    Combines all normalizers into a unified interface
    """

    def __init__(self):
        self.currency = CurrencyNormalizer()
        self.number = NumberNormalizer()
        self.stage = StageNormalizer()
        self.company = CompanyNormalizer()
        self.text = TextNormalizer()

    def normalize_value(self, key: str, value: Any) -> Tuple[Any, float, str]:
        """
        Normalize a value based on its key

        Args:
            key: Field name (e.g., "revenue", "margin", "stage")
            value: Value to normalize

        Returns:
            Tuple of (normalized_value, confidence, format_type)
        """
        if not value:
            return value, 0.0, "empty"

        key_lower = str(key).lower()

        if any(x in key_lower for x in ["revenue", "sales", "orders", "amount", "funding", "valuation"]):
            result = self.currency.normalize(str(value))
            if result:
                return result.normalized, result.confidence, result.format_type

        if "margin" in key_lower or "growth" in key_lower:
            result = self.number.normalize_growth_rate(str(value))
            if result:
                return result.normalized, result.confidence, result.format_type

        if "stage" in key_lower:
            result = self.stage.normalize(str(value))
            if result:
                return result.normalized, result.confidence, result.format_type

        if "name" in key_lower and "company" in key_lower:
            return self.company.normalize(str(value)), 0.9, "company"

        if "percentage" in key_lower:
            result = self.number.normalize_percentage(str(value))
            if result:
                return result.normalized, result.confidence, result.format_type

        return str(value), 0.5, "string"

    def normalize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize all values in a dictionary"""
        normalized = {}

        for key, value in data.items():
            if isinstance(value, dict):
                normalized[key] = self.normalize_dict(value)
            elif isinstance(value, list):
                normalized[key] = [
                    self.normalize_value(key, item)[0] if isinstance(item, str) else item
                    for item in value
                ]
            else:
                norm_val, confidence, fmt_type = self.normalize_value(key, value)
                normalized[key] = norm_val

        return normalized

    def normalize_extraction(self, extraction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a complete extraction result with confidence scores

        Returns:
            Dict with normalized values and per-field confidence tracking
        """
        result = {
            "normalized_data": {},
            "confidence_scores": {},
            "format_types": {}
        }

        for key, value in extraction.items():
            if key.startswith("_"):
                result["normalized_data"][key] = value
                continue
            if isinstance(value, dict):
                result["normalized_data"][key] = self.normalize_dict(value)
                result["confidence_scores"][key] = self._calculate_dict_confidence(value)
                result["format_types"][key] = "structured"
            elif isinstance(value, list):
                result["normalized_data"][key] = [
                    self.normalize_value(key, item)[0] if isinstance(item, str) else item
                    for item in value
                ]
                result["confidence_scores"][key] = 0.7 if value else 0.0
                result["format_types"][key] = "list"
            else:
                norm_val, confidence, fmt_type = self.normalize_value(key, value)
                result["normalized_data"][key] = norm_val
                result["confidence_scores"][key] = confidence
                result["format_types"][key] = fmt_type

        return result

    def _calculate_dict_confidence(self, data: Dict) -> float:
        """Calculate confidence for a nested dict"""
        if not data:
            return 0.0

        values = []
        for v in data.values():
            if isinstance(v, dict):
                values.append(self._calculate_dict_confidence(v))
            elif v:
                values.append(0.8)

        return sum(values) / len(values) if values else 0.0


def normalize_extraction_output(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to normalize extraction output
    """
    normalizer = ComprehensiveNormalizer()
    return normalizer.normalize_extraction(data)


def format_currency_for_display(value: str) -> str:
    """
    Format currency value for display
    """
    return CurrencyNormalizer.format_for_display(value)


def get_normalization_stats(normalized_data: Dict) -> Dict:
    """
    Get statistics about normalization results
    """
    stats = {
        "total_fields": 0,
        "high_confidence": 0,
        "medium_confidence": 0,
        "low_confidence": 0,
        "format_types": {}
    }

    def traverse(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                stats["total_fields"] += 1
                if isinstance(v, (dict, list)):
                    traverse(v)
        elif isinstance(obj, list):
            for item in obj:
                traverse(item)

    traverse(normalized_data)

    return stats