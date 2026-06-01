"""
Unified numeric interpretation engine.
Single source of truth for all Indian-currency and financial number parsing.
"""
import re
from enum import Enum
from typing import List, Tuple, Optional


class UnitType(Enum):
    CURRENCY = "currency"
    JOBS = "jobs"
    PERCENTAGE = "percentage"
    COUNT = "count"
    RATIO = "ratio"
    UNKNOWN = "unknown"


UNIT_TYPE_KEYWORDS = {
    "jobs": UnitType.JOBS,
    "job": UnitType.JOBS,
    "employees": UnitType.COUNT,
    "people": UnitType.COUNT,
    "customers": UnitType.COUNT,
    "users": UnitType.COUNT,
    "members": UnitType.COUNT,
    "companies": UnitType.COUNT,
    "clients": UnitType.COUNT,
    "candidates": UnitType.COUNT,
    "students": UnitType.COUNT,
    "units": UnitType.COUNT,
    "sets": UnitType.COUNT,
    "orders": UnitType.COUNT,
    "diagnostics": UnitType.COUNT,
    "tests": UnitType.COUNT,
}


def classify_unit_type(val_str: str, context: str = "") -> UnitType:
    """
    Classify the unit type of a value string.
    Distinguishes currency, jobs, percentage, count, ratio, unknown.
    """
    if not val_str:
        return UnitType.UNKNOWN
    lower = str(val_str).lower()
    ctx_lower = context.lower() if context else ""

    # Percentage
    if '%' in lower or 'percent' in lower:
        return UnitType.PERCENTAGE
    # Ratio
    if 'x' in lower and re.search(r'\d+x', lower):
        return UnitType.RATIO

    # Currency indicators
    if any(s in lower for s in ['₹', '$', 'rs.', 'inr', 'usd', 'eur', 'gbp']):
        return UnitType.CURRENCY
    if any(s in lower for s in ['cr', 'crore', 'lakh', 'lac', 'mn', 'million', 'bn', 'billion']):
        return UnitType.CURRENCY

    # Check context for non-currency keywords
    for kw, ut in UNIT_TYPE_KEYWORDS.items():
        if kw in ctx_lower:
            return ut

    # Check value string itself for unit keywords
    for kw, ut in UNIT_TYPE_KEYWORDS.items():
        if kw in lower:
            return ut

    return UnitType.UNKNOWN


# ---------------------------------------------------------------------------
# 0. SAFE FLOAT — prevent crashes on edge cases
# ---------------------------------------------------------------------------

def safe_float(value, default: float = 0.0) -> float:
    """
    Safely convert string to float, handling edge cases.
    Never crashes - always returns default on failure.
    """
    if value is None:
        return default
    
    s = str(value).strip()
    
    # Guard against empty/invalid strings
    if s in ("", ".", "-", "--", "NA", "N/A", "n/a", "null", "None", "none"):
        return default
    
    # Remove common noise but preserve valid numbers
    s = s.replace(',', '').replace(' ', '')
    
    # Check for orphan decimals after regex cleanup
    if s in (".", "-.", "+."):
        return default
    
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def safe_parse_number(val_str, default: float = 0.0) -> float:
    """
    Safely parse any number string to float.
    Handles edge cases: "60.0+ cr.", "42.0 Lakh Crores", etc.
    """
    if not val_str:
        return default
    
    raw = str(val_str).strip()
    if not raw:
        return default
    
    # Check for invalid patterns early
    if raw in (".", "-", "+", ".."):
        return default
    
    # Remove currency symbols but keep the number
    s = raw.replace('₹', '').replace('$', '').replace('£', '').replace('€', '')
    
    # Handle "+" suffix (e.g., "60.0+") - treat as ~10% increase
    has_plus = '+' in s
    s = s.replace('+', '')
    
    # Now extract the numeric part - require at least one digit
    # This prevents matching just "." from "60.0+ cr."
    m = re.search(r'(\d+(?:,\d+)*(?:\.\d+)?)', s)
    if not m:
        return default
    
    num_str = m.group(1).replace(',', '')
    num = safe_float(num_str, default)
    
    if num == default:
        return default
    
    # Apply plus modifier
    if has_plus:
        num = num * 1.1
    
    return num


# ---------------------------------------------------------------------------
# 1. PARSING — string → float with Indian scale support
# ---------------------------------------------------------------------------

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


def parse_indian_number(val_str) -> float:
    """
    Parse Indian/US currency strings to raw float.
    Handles: Cr, Crore, Lakh, Lac, K, Mn, Million, Bn, Billion.
    Special handling for "Lakh Crores" (e.g., 42.0 Lakh Crores).
    """
    if not val_str:
        return 0.0
    
    raw = str(val_str).strip()
    if not raw:
        return 0.0
    
    # Get base number safely
    num = safe_parse_number(raw, 0.0)
    if num == 0.0:
        return 0.0
    
    lower = raw.lower()
    
    # Check for compound scales (e.g., "Lakh Crores")
    if 'lakh' in lower or 'lac' in lower:
        if 'crore' in lower or 'cr' in lower:
            # "42.0 Lakh Crores" = 42 * 100000 * 10000000 = 420000000000
            return num * 100_000 * 10_000_000
        return num * 100_000
    
    if 'crore' in lower or 'cr' in lower:
        return num * 10_000_000
    
    if 'bn' in lower or 'billion' in lower or re.search(r'\bbn?\b', lower):
        return num * 1_000_000_000
    
    if 'mn' in lower or 'million' in lower:
        return num * 1_000_000
    
    if 'k' in lower or 'thousand' in lower:
        return num * 1_000
    
    return num


def parse_any_number(val_str) -> float:
    """Parse any number string — tries Indian first, falls back to safe float."""
    result = parse_indian_number(val_str)
    if result != 0.0:
        return result
    # Raw float fallback with safe conversion
    s = str(val_str).replace(',', '')
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    return safe_float(m.group(1), 0.0) if m else 0.0


# ---------------------------------------------------------------------------
# 2. DETECTION — identify unit from string
# ---------------------------------------------------------------------------

_UNIT_MAP = [
    (r'\bcr\b|\bcrore\b', 'Cr'),
    (r'\blakh?\b|\blac\b', 'Lakhs'),
    (r'\bbn\b|\bbillion\b', 'Bn'),
    (r'\bmn\b|\bmillion\b', 'Mn'),
    (r'\bk\b|\bthousand\b', 'K'),
]


def detect_unit(val_str) -> Optional[str]:
    """Return the unit (Cr, Lakhs, Mn, Bn, K) found in value string, or None."""
    if not val_str:
        return None
    lower = str(val_str).lower()
    for pattern, unit in _UNIT_MAP:
        if re.search(pattern, lower):
            return unit
    return None


# ---------------------------------------------------------------------------
# 3. COMPARISON — safe cross-unit comparison
# ---------------------------------------------------------------------------

def compare_numeric(a, b) -> int:
    """
    Safe comparison of two financial strings.
    Returns: -1 if a < b, 0 if equal, 1 if a > b.
    Handles cross-unit comparison (e.g., ₹5 Cr vs ₹50 Lakhs).
    """
    val_a = parse_indian_number(a)
    val_b = parse_indian_number(b)
    if val_a < val_b:
        return -1
    if val_a > val_b:
        return 1
    return 0


# ---------------------------------------------------------------------------
# 4. EXTRACTION — find ALL numbers in text
# ---------------------------------------------------------------------------

def extract_numbers_from_text(text: str) -> List[dict]:
    """
    Extract all financial number+unit patterns from text with context.
    Returns list of {value_raw, value_num, unit, context, position}.
    Uses safe parsing to prevent crashes on edge cases.
    """
    if not text:
        return []

    results = []
    # Match patterns like: ₹5.1 Cr, ₹30 Mn, $55 Mn, 300 customers, etc.
    # Enhanced to handle: 60.0+ cr., 42.0 Lakh Crores, etc.
    pattern = re.compile(
        r'(?:₹|\$)?\s*(\d+(?:,\d+)*(?:\.\d+)?\+?)\s*'
        r'(Cr(?:ores?)?|L(?:akh)?s?|Mn?|Bn?|Million|Billion|Thousand|K)?',
        re.IGNORECASE
    )
    seen = set()

    for m in pattern.finditer(text):
        raw = m.group(0).strip()
        if raw in seen:
            continue
        seen.add(raw)

        # Skip if raw is just punctuation/dots
        if not re.search(r'\d', raw):
            continue

        unit_str = (m.group(2) or '').strip()
        
        # Use safe parsing to prevent crashes
        val_num = parse_indian_number(raw)
        
        if val_num == 0.0 and re.search(r'\d', raw):
            # Try extracting just the numeric part if parse failed
            num_match = re.search(r'(\d+(?:,\d+)*(?:\.\d+)?)', raw.replace(',', ''))
            if num_match:
                val_num = safe_float(num_match.group(1), 0.0)

        # Get surrounding context (30 chars each side)
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        ctx = text[start:end].strip()

        results.append({
            'value_raw': raw,
            'value_num': val_num,
            'unit': detect_unit(raw) or '',
            'unit_type': classify_unit_type(raw, ctx).value,
            'context': ctx,
            'position': m.start(),
        })

    return results


# ---------------------------------------------------------------------------
# 5. FORMATTING
# ---------------------------------------------------------------------------

def normalize_percentage(val_str) -> str:
    """Remove redundant '.0' from percentage values."""
    if not val_str:
        return val_str or ''
    return re.sub(r'(\d+)\.0\s*%', r'\1%', str(val_str))
