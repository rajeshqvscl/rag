import re
import json
import hashlib
import concurrent.futures
from typing import Any, Dict, List, Optional
from app.core.llm_client import get_safe_client

def safe_client():
    return get_safe_client()
from app.utils.text_utils import safe_lower, validate_section, ensure_string
from app.rag.extract_utils import normalize_nulls, safe_get, ensure_list, ensure_dict
from app.rag.financial_validator import validate_financials, calculate_field_confidence
from app.rag.number_utils import extract_numbers_from_text, detect_unit
from app.rag.semantic_narrative import generate_confidence_summary, generate_rich_company_brief, _detect_sector, _SECTOR_PROFILES, improve_warning
from app.rag.canonical_registry import build_canonical_registry
from app.rag.company_resolver import CompanyIdentityResolver
from app.rag.validation_engine import validate_all
from app.rag.chart_exporter import export_chart_data_from_canonical

MAX_CONTEXT_TOKENS = 8000
MAX_CONTEXT_CHARS = 6000

MAX_OUTPUT_TOKENS = 2048

_LLM_CACHE = {}
_LLM_CACHE_MAX = 100


def safe_join(parts, sep=" "):
    """Join non-empty string parts with separator. Filters empty/falsy values."""
    return sep.join(p for p in parts if p and p.strip())


def _filter_empty_clause_parts(clauses):
    """Remove clauses that contain only empty template slots (e.g. 'with USP of ')."""
    filtered = []
    for c in clauses:
        stripped = c.strip().rstrip(",").strip()
        if not stripped:
            continue
        # Reject clauses that end with ' of ', ' by ', ' with ' (empty trailing slots)
        if re.search(r'\b(of|by|with|from|using)\s*$', stripped, re.IGNORECASE):
            continue
        # Reject clauses that are just a single word (likely orphaned label)
        if len(stripped.split()) <= 1:
            continue
        filtered.append(stripped)
    return filtered

# P1: Banned filler phrases that make the system sound generic/untrustworthy
_BANNED_FILLERS = [
    "technology-enabled platform",
    "scalable operations",
    "early commercial traction",
    "substantial growth runway",
    "strong operational metrics",
    "technology-driven platform",
    "cutting-edge technology",
    "state-of-the-art",
    "industry-leading platform",
    "best-in-class solution",
    "game-changing approach",
    "disruptive innovation",
    "revolutionary technology",
    "world-class team",
    "proven track record",
    "strategic partnerships",
    "robust pipeline",
    "significant traction",
    "high-growth market",
    "innovative solution",
    "unique value proposition",
    "leverage our platform",
    "synergistic approach",
    "bleeding-edge",
]


def _filter_generic_phrases(text: str) -> str:
    """Remove banned generic filler phrases from generated text."""
    if not text:
        return text
    result = text
    for phrase in _BANNED_FILLERS:
        # Case-insensitive replacement with context-aware substitute
        idx = result.lower().find(phrase.lower())
        while idx != -1:
            # Extract a short context window around the phrase
            start = max(0, idx - 20)
            end = min(len(result), idx + len(phrase) + 20)
            context = result[start:end]
            # Replace the phrase with empty string (it was filler)
            before = result[:idx]
            after = result[idx + len(phrase):]
            # Clean up double spaces
            result = (before + after).replace("  ", " ").replace("  ", " ")
            idx = result.lower().find(phrase.lower())
    return result.strip()


SECTION_QUERIES = {
    "company_brief":      ["company overview", "about us", "who we are", "introduction"],
    "business_overview":  ["business model", "how it works", "revenue model", "go to market"],
    "industry_overview":  ["market size", "TAM SAM SOM", "industry overview", "market opportunity"],
    "problem":            ["problem statement", "pain points", "challenges", "the problem"],
    "solution":           ["solution", "product", "platform", "how we solve", "our approach"],
    "traction":           ["traction", "milestones", "customers", "orders", "revenue", "growth"],
    "funding":            ["funding", "investment", "raising", "use of funds", "cap table", "previous round"],
    "pipeline":           ["pipeline", "LOI", "upcoming", "prospects", "deals in progress"],
    "revenue_details":    ["financials", "revenue", "unit economics", "projections", "EBITDA", "margin"],
    "recognition":        ["awards", "recognition", "certifications", "media", "grants", "accelerators"]
}


def build_section_context(retriever_fn, max_chars_per_section=800):
    """Query the vector store separately for each section."""
    if not retriever_fn:
        return None
    
    section_texts = {}
    
    for section, queries in SECTION_QUERIES.items():
        section_chunks = []
        seen = set()
        
        for query in queries:
            try:
                results = retriever_fn(query)
                for chunk in results:
                    chunk_str = chunk if isinstance(chunk, str) else str(chunk)
                    chunk_key = chunk_str[:80]
                    if chunk_key not in seen:
                        seen.add(chunk_key)
                        section_chunks.append(chunk_str)
            except Exception as e:
                print(f"[RETRIEVAL] Section '{section}' query failed: {e}")
        
        section_text = ""
        total = 0
        for chunk in section_chunks:
            if total + len(chunk) > max_chars_per_section:
                break
            section_text += chunk + "\n"
            total += len(chunk)
        
        if section_text.strip():
            section_texts[section] = section_text.strip()
    
    merged = ""
    for section, text in section_texts.items():
        merged += f"\n\n[SECTION: {section.upper()}]\n{text}"
    
    return merged


def _is_valid_revenue_stream(stream: str) -> bool:
    """Filter out chart axis labels and malformed values masquerading as revenue streams"""
    if not stream or len(str(stream).strip()) < 3:
        return False
    stream_str = str(stream).strip()
    # Reject bare currency amounts: $2.00 Mn, ₹2.00 Lakhs, 2.5Cr, etc.
    if re.match(r'^[\$₹]?\s*[\d.]+\s*(Mn|Cr|L|K|Lakhs|Million|Bn?|Thousand)?$', stream_str, re.IGNORECASE):
        return False
    # Reject anything that's just a number with optional currency and unit
    if re.match(r'^[\$₹]?\s*[\d.]+$', stream_str):
        return False
    # Reject very short currency-like strings
    if len(stream_str) < 5 and re.match(r'^[\$₹]?[\d.]+$', stream_str):
        return False
    # Reject duplicate-looking values
    if len(stream_str) > 6 and stream_str.count(stream_str[:6]) > 1:
        return False
    return True


def normalize_extraction_output(raw_output):
    """Normalize LLM JSON output to prevent None crashes"""
    if isinstance(raw_output, str):
        try:
            raw_output = json.loads(raw_output)
        except:
            return raw_output
    return normalize_nulls(raw_output)


def format_indian_currency(value):
    """Format Indian currency values properly"""
    if not value:
        return value
    
    value_str = str(value).lower()
    
    if any(x in value_str for x in ["₹", "rs", "inr"]):
        return value
    
    match = re.search(r'([\d.]+)', str(value))
    if not match:
        return value
    
    num = float(match.group(1))
    
    if num >= 10000000:
        return f"₹{num / 10000000:.2f} Cr"
    elif num >= 100000:
        return f"₹{num / 100000:.2f} Lakhs"
    elif num >= 1000:
        return f"₹{num / 1000:.2f} K"
    else:
        return f"₹{num:.2f}"


def format_currency_value(value):
    """Format any currency value to proper format"""
    if not value:
        return ""
    
    value_str = str(value)
    
    if "cr" in value_str.lower():
        match = re.search(r'([\d.]+)', value_str)
        if match:
            return f"₹{float(match.group(1)):.1f} Cr"
    
    if re.search(r'\bl(?:akh)?s?\b', value_str.lower()):
        match = re.search(r'([\d.]+)', value_str)
        if match:
            return f"₹{float(match.group(1)):.1f} Lakhs"
    
    if "$" in value_str or "usd" in value_str.lower():
        match = re.search(r'([\d.]+)', value_str)
        if match:
            return f"${float(match.group(1)):.1f} Mn"
    
    return value_str


class FactRegistry:
    """Store all extracted facts with source and confidence before generating output"""
    
    def __init__(self):
        self.facts = {}
    
    def add(self, key, value, source_page=None, context="", confidence=50):
        validated = validate_fact_value(key, value)
        if validated:
            self.facts[key] = {
                "value": validated,
                "source_page": source_page,
                "context": context[:200] if context else "",
                "confidence": confidence
            }
    
    def get(self, key, default=None):
        fact = self.facts.get(key, {})
        return fact.get("value", default)
    
    def get_all(self):
        return self.facts
    
    def get_confidence(self, key):
        return self.facts.get(key, {}).get("confidence", 0)
    
    def has_fact(self, key):
        return key in self.facts
    
    def missing_keys(self, required_keys):
        return [k for k in required_keys if k not in self.facts]

def validate_fact_value(key, value):
    """Validate extracted values - reject unrealistic metrics"""
    if not value or value in ["null", "None", "none", "N/A", "n/a", "not provided", "unknown", ""]:
        return None
    
    value_str = str(value).lower()
    
    if "revenue" in key or key == "revenue":
        if re.search(r'^\d{1,3}$', value_str):
            return None
        if not any(x in value_str for x in ["₹", "cr", "lakh", "$", "inr", "million", "billion"]):
            return None
    
    if "order" in key or key == "orders":
        if re.search(r'^\d{1,3}$', value_str) and len(value_str) <= 3:
            return None
    
    if "stage" in key:
        valid_stages = ["seed", "pre-seed", "series a", "series b", "series c", "growth", "pre-series", "angel", "bridge"]
        if not any(s in value_str for s in valid_stages):
            return None
    
    return value

def normalize_numbers(text):
    """Clean OCR artifacts and normalize number formats"""
    if not text:
        return text
    
    replacements = [
        (r'(\d+)\.(\d+)\.(\d+)', r'\1\2\3'),
        (r'(\d+(?:\.\d+)?)\s*[Ll]akh[s]?\s*INR', r'₹\1 Lakhs'),
        (r'(\d+(?:\.\d+)?)\s*[Ll]akh[s]?', r'₹\1 Lakhs'),
        (r'(\d+(?:\.\d+)?)\s*[Cc]r\.?\s*INR', r'₹\1 Cr'),
        (r'(\d+(?:\.\d+)?)\s*[Cc]r\.?', r'₹\1 Cr'),
        (r'(\d+)\s*[Cc]r\s*/\s*USD', r'₹\1 Cr'),
        (r'(\d+)\s*[Mm]n\s*USD', r'$\1 Mn'),
        (r'(\d+(?:\.\d+)?)\s*[Mm]illion', r'₹\1 Mn'),
        (r'(\d+)\+', r'\1+'),
        (r'INR\s*(\d+\.?\d*)\s*Cr\s*/\s*USD', r'INR \1 Cr'),
        (r'₹\s*(\d+\.?\d*)\s*Cr\s*/\s*USD', r'₹\1 Cr'),
    ]
    
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text

def normalize_extracted_value(key, value):
    """Clean up extracted metric values - remove malformed labels"""
    if not value:
        return value
    
    value = re.sub(r'\s*/\s*USD$', '', value)
    value = re.sub(r'\s*/\s*INR$', '', value)
    value = re.sub(r'\s+USD\s*$', '', value)
    value = re.sub(r'\s+INR\s*$', '', value)
    
    return value.strip()

def normalize_to_metric_object(val: Any, metric_type: str) -> dict:
    if isinstance(val, dict):
        # Ensure all keys exist
        default = {"value": "", "source_slide": None, "evidence_text": "", "metric_type": metric_type, "confidence_tier": "", "confidence": 0.0}
        res = {}
        for k, v in default.items():
            res[k] = val.get(k, v)
        if res["value"] is None:
            res["value"] = ""
        if not res["confidence_tier"] and res["value"]:
            res["confidence_tier"] = "explicit"
            res["confidence"] = 0.95
        return res
    # Raw string or similar
    val_str = str(val) if val is not None else ""
    if val_str in ("null", "None", "none", "N/A", "n/a", "not provided", "unknown"):
        val_str = ""
    return {
        "value": val_str,
        "source_slide": None,
        "evidence_text": "",
        "metric_type": metric_type,
        "confidence_tier": "explicit" if val_str else "",
        "confidence": 0.95 if val_str else 0.0
    }

def normalize_value(value):
    """Normalize a single extracted value"""
    if not value or value in ["null", "None", "none", "N/A", "n/a", "not provided", "unknown"]:
        return None
    
    if isinstance(value, str):
        value = value.strip()
        value = re.sub(r'(\d+)\.(\d+)\.(\d+)', r'\1\2\3', value)
        value = re.sub(r'(\d+)\.0+(\s*Cr)', r'\1\2', value)
    
    return value if value else None

def generate_narrative_email(company_name, structured_data, intent, canonical_registry=None):
    """Generate personalized email with sector context — no fabricated stats, just relevant framing."""
    sector = ""
    brief = structured_data.get("company_brief", {})
    if isinstance(brief, dict):
        sector = brief.get("sector", "")
    if not sector:
        from app.rag.semantic_narrative import _detect_sector
        detected = _detect_sector(str(structured_data.get("company_brief", {})))
        if detected and detected != "general":
            sector = detected

    traction = structured_data.get("traction", {}) or {}
    rev = ""
    if isinstance(traction, dict):
        rev = traction.get("revenue", "")

    sector_openers = {
        "healthcare": "Your healthcare infrastructure platform approach is an interesting model in the diagnostics ecosystem.",
        "defence": "Your indigenous defence technology positioning is relevant to current procurement priorities.",
        "defense": "Your indigenous defense technology positioning is relevant to current procurement priorities.",
        "fintech": "Your fintech approach operating at the intersection of technology and financial services is compelling.",
        "climate": "Your climate technology focus aligned with sustainability priorities is noteworthy.",
        "agritech": "Your agritech platform addressing agricultural supply chain challenges is timely.",
        "saas": "Your enterprise SaaS model with clear revenue traction is well-aligned with our investment focus.",
        "deeptech": "Your deep technology moat and IP-driven approach is particularly interesting.",
        "ai": "Your AI-native approach to solving enterprise challenges is well-timed given market trends.",
    }

    opener = sector_openers.get(sector.lower(), "Thanks for sharing your pitch deck.")
    body = f"Hope you're doing well.\n\n{opener}"
    if rev:
        body += f" Would love to understand the growth trajectory and roadmap better."
    body += f"\n\nCould you please share 2-3 time slots that work for you over the next few days so we can coordinate and schedule the call accordingly?"
    return body

def _has_positioning_language(text: str) -> bool:
    """Detect if text is a positioning statement rather than competitor name."""
    if not text:
        return False
    t = text.lower().strip()
    if re.search(r'^(the|a|an)\s+.+of\s+the\s', t):
        return True
    if re.search(r'^(amazon|uber|google|netflix|airbnb|tesla|stripe|facebook)\s+of\b', t):
        return True
    if re.search(r'^(leading|largest|biggest|top|premier|foremost)\s', t):
        return True
    if re.search(r'\b(platform|ecosystem|marketplace|network)\b', t):
        return True
    return False


def clean_llm_json(raw: str) -> str:
    raw = raw.replace('"""', '"')
    raw = re.sub(r'\*\*(.*?)\*\*', r'\1', raw)
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE)
    return raw.strip()


def recover_json(raw: str) -> Optional[Dict]:
    """Attempt to recover valid JSON from malformed LLM output."""
    if not raw.strip():
        return None

    # Strategy 1: Try strict parse after basic cleanup
    cleaned = clean_llm_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Find the outermost { ... } block and try parsing just that
    brace_start = cleaned.find("{")
    brace_end = cleaned.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        json_candidate = cleaned[brace_start:brace_end+1]
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass
        # Strategy 3: Fix common issues within the JSON block
        fixed = json_candidate
        # Replace single quotes with double quotes (but not within strings)
        fixed = re.sub(r"(?<!\\)'", '"', fixed)
        # Remove trailing commas before closing braces/brackets
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)
        # Remove control characters
        fixed = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', fixed)
        # Fix unquoted keys (keys not in quotes)
        fixed = re.sub(r'(?<!")(\b[a-zA-Z_][a-zA-Z0-9_]*\b)(?=\s*:)', r'"\1"', fixed)
        # Remove trailing comma before closing
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        # Strategy 4: Try to fix truncated JSON by closing unclosed braces
        open_braces = fixed.count("{") - fixed.count("}")
        open_brackets = fixed.count("[") - fixed.count("]")
        if open_braces > 0:
            fixed += "}" * open_braces
        if open_brackets > 0:
            fixed += "]" * open_brackets
        # Remove any trailing content after the final JSON closing
        fixed = re.sub(r'\}([^}]*)$', r'}', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # Strategy 5: Try extracting each top-level key-value pair individually
        try:
            result = {}
            for m in re.finditer(r'"([^"]+)"\s*:\s*(\{[^{}]*\}|\[[^\[\]]*\]|"[^"]*"|null|true|false|\d+\.?\d*)', fixed):
                key, val_str = m.group(1), m.group(2)
                try:
                    result[key] = json.loads(val_str)
                except:
                    result[key] = val_str.strip('"')
            if result:
                return result
        except:
            pass

    return None


def _try_extract_value(text: str, key: str) -> str:
    """Extract a value for a given key from loosely structured text."""
    patterns = [
        re.compile(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL),
        re.compile(rf'"{key}"\s*:\s*(\d+\.?\d*)'),
        re.compile(rf'"{key}"\s*:\s*(true|false|null)'),
        re.compile(rf'{key}\s*[:\-]\s*(.+?)(?=\n\s*\w+\s*[:\-]|\Z)', re.DOTALL),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return ""


def fallback_section_extraction(raw: str) -> Dict:
    """Extract structured data from malformed output using regex when JSON parsing fails."""
    data = {
        "company_brief": {"name": "", "tagline": "", "one_liner": ""},
        "traction": {"revenue": {"value": ""}, "key_milestones": []},
        "funding": {"current_raise": ""},
        "business_overview": {"business_model": "", "key_differentiator": ""},
        "industry_overview": {"tam": "", "market_context": ""},
        "insights": {"key_signal": "", "strengths": [], "weaknesses": []}
    }

    # Try to extract key fields from any remaining JSON-like fragments
    key_map = {
        "company_brief": ["company_brief", "company"],
        "name": ["name", "company_name", "company"],
        "tagline": ["tagline", "one_liner"],
        "revenue": ["revenue", "current_raise"],
        "tam": ["tam", "market_size"],
    }

    json_fragments = re.findall(r'\{[^{}]*\}', raw)
    for fragment in json_fragments:
        try:
            parsed = json.loads(fragment)
            if isinstance(parsed, dict):
                _deep_merge(data, parsed)
        except json.JSONDecodeError:
            pass

    # Extract section-labeled content
    section_labels = [
        (r'COMPANY[:_]\s*(.+?)(?=\n\s*(?:TRACTION|MARKET|TEAM|FUNDING|COMPETITION|\Z))', "company_brief", "one_liner"),
        (r'TRACTION[:_]\s*(.+?)(?=\n\s*(?:COMPANY|MARKET|TEAM|FUNDING|\Z))', "traction", "key_milestones"),
        (r'MARKET[:_]\s*(.+?)(?=\n\s*(?:COMPANY|TRACTION|TEAM|FUNDING|\Z))', "industry_overview", "market_context"),
        (r'FUNDING[:_]\s*(.+?)(?=\n\s*(?:COMPANY|TRACTION|MARKET|TEAM|\Z))', "funding", "current_raise"),
        (r'SIGNAL[:_]\s*(.+?)(?=\n)', "insights", "key_signal"),
    ]
    for pattern, section, field in section_labels:
        m = re.search(pattern, raw, re.DOTALL | re.IGNORECASE)
        if m:
            val = m.group(1).strip()[:500]
            if section == "insights" and field == "key_signal":
                data["insights"]["key_signal"] = val
            elif isinstance(data.get(section, {}).get(field), list):
                data[section][field] = [val]
            else:
                if isinstance(data.get(section), dict):
                    data[section][field] = val

    return data


def _deep_merge(base: Dict, override: Dict) -> None:
    """Deep merge override dict into base dict."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        elif val and val not in (None, "", [], {}, "null", "None"):
            base[key] = val


def final_validator(output):
    """Validate and clean final output"""
    if not isinstance(output, str):
        output = str(output)

    if "YoY" in output and "growth" not in output:
        output = output.replace("YoY", "")

    if "No verified financial" in output and "Strong traction" in output:
        output = output.replace("Strong traction", "Early-stage visibility")

    return output


def normalize_llm_output(data: dict) -> dict:
    """Normalize LLM output to handle nested dicts in arrays, None values, etc."""
    normalized = normalize_nulls(data)

    if "use_of_funds" in normalized and normalized["use_of_funds"]:
        use_of_funds = normalized["use_of_funds"]
        if isinstance(use_of_funds, list) and len(use_of_funds) > 0:
            if isinstance(use_of_funds[0], dict):
                normalized["use_of_funds"] = [
                    f.get("purpose", "") if isinstance(f, dict) else str(f)
                    for f in use_of_funds
                ]

    if "founders" in normalized and normalized["founders"]:
        founders = normalized["founders"]
        if isinstance(founders, list) and len(founders) > 0:
            if isinstance(founders[0], dict):
                normalized["founders"] = [
                    f.get("name", "") if isinstance(f, dict) else str(f)
                    for f in founders
                ]

    return normalized


def limit_context(chunks, max_chars=MAX_CONTEXT_CHARS):
    """Limit context to prevent token overflow"""
    context = ""
    total_len = 0
    
    for chunk in chunks:
        chunk_str = chunk if isinstance(chunk, str) else str(chunk)
        if total_len + len(chunk_str) + 1 > max_chars:
            break
        context += chunk_str + "\n"
        total_len += len(chunk_str) + 1
    
    return context


def count_tokens(text: str) -> int:
    """Rough token count (chars / 4 is approximate for English)"""
    return len(text) // 4


def apply_comprehensive_normalization(data: dict) -> dict:
    """
    Apply comprehensive normalization to extraction data
    Includes currency, stage, and format normalization
    """
    from app.rag.normalizer import ComprehensiveNormalizer
    
    normalizer = ComprehensiveNormalizer()
    normalized = normalizer.normalize_extraction(data)
    
    return normalized.get("normalized_data", data)


def add_source_attribution(data: dict, chunks: list, metadata: dict) -> dict:
    """
    Add source attribution to extracted data
    """
    from app.rag.source_tracker import SourceTracker, SourceAttribution, create_attribution
    
    tracker = create_attribution(chunks, metadata, data)
    
    result = data.copy()
    result["_source_info"] = tracker.to_citation_format()
    
    return result


def format_section(title, data):
    if not data:
        return f"### {title}\nNo data available\n\n"

    if isinstance(data, str):
        if not data.strip() or str(data).lower() in ["n/a", "no data provided"]:
            return f"### {title}\nNo data available\n\n"
        return f"### {title}\n{data}\n\n"

    formatted = f"### {title}\n"
    if isinstance(data, dict):
        for key, value in data.items():
            key_clean = str(key).replace("_", " ").capitalize()
            formatted += f"- **{key_clean}**: {value}\n"
    elif isinstance(data, list):
        for item in data:
            formatted += f"- {item}\n"
    
    return formatted + "\n"

def format_summary(summary_dict):
    if not isinstance(summary_dict, dict):
        return ensure_string(summary_dict)
    
    order = [
        "ACTUALS", 
        "UNIT_ECONOMICS", 
        "MARKET_SIZE", 
        "COMPETITION", 
        "TEAM", 
        "TRACTION", 
        "FUNDING",
        "RISK_FACTORS",
        "SWOT_ANALYSIS",
        "OUTLOOK", 
        "INVESTOR_FIT", 
        "MISSING_DATA"
    ]
    final_output = ""
    for key in order:
        if key in summary_dict:
            title = key.replace("_", " ").upper()
            final_output += format_section(title, summary_dict[key])
    return final_output.strip()

def validate_metric_confidence(value, metric_type):
    """Validate metrics and adjust confidence based on realism"""
    if not value:
        return value, "high"
    
    value_str = str(value).lower()
    
    unrealistic = {
        "margin": [">95", "100%", "99%", "98%"],
        "growth": ["500%", "1000%", "10000%"],
    }
    
    if metric_type in unrealistic:
        for bad_val in unrealistic[metric_type]:
            if bad_val in value_str:
                return value + " (verify from source)", "low"
    
    return value, "high"


def _join_clauses(clauses):
    """'A', 'B', 'C' → 'A, B, and C'"""
    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) == 2:
        return f"{clauses[0]} and {clauses[1]}"
    return f"{', '.join(clauses[:-1])}, and {clauses[-1]}"


def _has_data(section, *keys):
    """Check if any key has non-empty value in section"""
    return any(section.get(k) for k in keys)


def _parse_indian_number(val_str: str) -> float:
    from app.rag.number_utils import parse_indian_number
    return parse_indian_number(val_str)


def _migrate_to_flat_schema(d):
    """Normalize both old nested and new flat schema to flat fields."""
    d = normalize_nulls(d)
    # Traction: old had {"revenue":{"value":"","period":""}} -> flat "revenue":""
    for sec, flat_fields in [
        ("traction", ["revenue", "orders", "customers", "key_milestones"]),
        ("funding", ["current_raise", "valuation", "previous_rounds", "investors", "use_of_funds"]),
        ("pipeline", ["pipeline_value", "lois", "prospects"]),
        ("recognition", ["awards", "certifications", "media_coverage"]),
    ]:
        section = d.get(sec, {})
        if isinstance(section, dict):
            for f in flat_fields:
                val = section.get(f)
                if isinstance(val, dict) and "value" in val:
                    section[f] = val["value"]
    # Revenue details
    rd = d.get("revenue_details", {})
    if isinstance(rd, dict):
        for old_key, new_key in [("current", "current_revenue")]:
            val = rd.get(old_key)
            if isinstance(val, dict) and "value" in val:
                rd[new_key] = val["value"]
        ue = rd.get("unit_economics", {})
        if isinstance(ue, dict):
            for k in ["ticket_size", "cac", "ltv"]:
                if ue.get(k) and not rd.get(k):
                    rd[k] = ue[k]
    # Business overview: old "business_model" -> new "model"
    biz = d.get("business_overview", {})
    if isinstance(biz, dict):
        if biz.get("business_model") and not biz.get("model"):
            biz["model"] = biz["business_model"]
        if biz.get("key_differentiator") and not biz.get("differentiator"):
            biz["differentiator"] = biz["key_differentiator"]
        if biz.get("go_to_market") and not biz.get("gtm"):
            biz["gtm"] = biz["go_to_market"]
    return d


def format_structured_summary(structured_data, include_sources: bool = False, field_confidence: dict = None):
    """Convert structured JSON to 1-2 sentence narratives per section.
    Uses confidence-aware SemanticNarrativeEngine when field_confidence is available."""
    # Delegate to the confidence-aware engine if field_confidence is provided
    if field_confidence is not None:
        return generate_confidence_summary(structured_data, field_confidence, include_sources)

    # Legacy fallback for backward compatibility
    output = []
    structured_data = _migrate_to_flat_schema(structured_data)

    def _g(section, key):
        v = section.get(key, "")
        return str(v).strip() if v else ""

    # 1. COMPANY BRIEF
    brief = structured_data.get("company_brief", {})
    output.append("### COMPANY BRIEF")
    c_parts = []
    name = _g(brief, "name")
    if name:
        line = name
        stage = _g(brief, "stage")
        if stage:
            s = stage.lower()
            series_match = re.search(r'series\s*([a-z])', s)
            if series_match:
                line += f" | Series {series_match.group(1).upper()}"
            elif "seed" in s:
                line += " | Seed"
            elif "growth" in s:
                line += " | Growth Stage"
            else:
                line += f" | {stage.title()}"
        sector = _g(brief, "sector")
        if sector:
            line += f" | {sector.title()}"
        founded = _g(brief, "founded_year")
        if founded:
            line += f" | Est. {founded}"
        c_parts.append(line)
    tagline = _g(brief, "tagline")
    if tagline:
        c_parts.append(tagline)
    one_liner = _g(brief, "one_liner")
    if one_liner and one_liner not in tagline:
        c_parts.append(one_liner)
    output.append(f"  {_join_clauses(c_parts)}." if c_parts else "  Company information not available.")
    output.append("")

    # 2. BUSINESS OVERVIEW
    biz = structured_data.get("business_overview", {})
    output.append("### BUSINESS OVERVIEW")
    b_clauses = []
    if _g(biz, "model"):
        b_clauses.append(f"{biz['model']}")
    if _g(biz, "revenue_model"):
        b_clauses.append(f"revenue through {biz['revenue_model']}")
    if _g(biz, "target_customers"):
        b_clauses.append(f"serving {biz['target_customers']}")
    if _g(biz, "gtm"):
        b_clauses.append(f"via {biz['gtm']}")
    if _g(biz, "differentiator"):
        b_clauses.append(f"differentiated by {biz['differentiator']}")
    output.append(f"  {_join_clauses(b_clauses)}." if b_clauses else "  Business model and operations not explicitly stated in the deck.")
    output.append("")

    # 3. INDUSTRY OVERVIEW
    ind = structured_data.get("industry_overview", {})
    output.append("### INDUSTRY OVERVIEW")
    m_clauses = []
    if _g(ind, "tam"):
        m_clauses.append(f"TAM of {ind['tam']}")
    if _g(ind, "sam"):
        m_clauses.append(f"SAM of {ind['sam']}")
    if _g(ind, "som"):
        m_clauses.append(f"SOM of {ind['som']}")
    if _g(ind, "market_context"):
        m_clauses.append(f"in {ind['market_context']}")
    trends = ind.get("key_trends", [])
    if trends:
        m_clauses.append(f"with trends including {', '.join(trends[:2])}")
    output.append(f"  {_join_clauses(m_clauses)}." if m_clauses else "  Market sizing (TAM/SAM/SOM) not explicitly defined in the deck.")
    output.append("")

    # 4. PROBLEM
    prob = structured_data.get("problem", {})
    output.append("### PROBLEM STATEMENT")
    p_clauses = []
    if _g(prob, "statement"):
        p_clauses.append(prob["statement"])
    pain = prob.get("pain_points", [])
    if pain:
        p_clauses.append(f"pain points include {', '.join(pain[:3])}")
    output.append(f"  {_join_clauses(p_clauses)}." if p_clauses else "  Problem context being inferred from available data.")
    output.append("")

    # 5. SOLUTION
    output.append("### SOLUTION")
    sol = structured_data.get("solution", {}) or {}

    s_clauses = []
    if _g(sol, "description"):
        s_clauses.append(sol["description"])
    features = sol.get("key_features", [])
    if features:
        s_clauses.append(f"key features include {safe_join(features[:4], ', ')}")
    if _g(sol, "technology"):
        s_clauses.append(f"powered by {sol['technology']}")
    if _g(sol, "usp"):
        s_clauses.append(f"with USP of {sol['usp']}")
    s_clauses = _filter_empty_clause_parts(s_clauses)
    output.append(f"  {_join_clauses(s_clauses)}." if s_clauses else "  Solution being inferred from available data.")
    output.append("")

    # 6. TRACTION & VALIDATION
    tr = structured_data.get("traction", {})
    output.append("### TRACTION & VALIDATION")
    t_clauses = []
    if _g(tr, "revenue"):
        t_clauses.append(f"revenue of {tr['revenue']}")
    if _g(tr, "orders"):
        t_clauses.append(f"with {tr['orders']} orders")
    if _g(tr, "customers"):
        t_clauses.append(f"across {tr['customers']}")
    milestones = tr.get("key_milestones", [])
    milestone_text = ""
    if milestones:
        milestone_text = f" Milestones include {', '.join(milestones[:2])}."
    output.append(f"  {_join_clauses(t_clauses)}.{milestone_text}" if t_clauses else "  Traction data not explicitly stated in the deck.")
    output.append("")

    # 7. FUNDING & INVESTMENT HISTORY
    fund = structured_data.get("funding", {})
    output.append("### FUNDING & INVESTMENT HISTORY")
    f_clauses = []
    if _g(fund, "current_raise"):
        f_clauses.append(f"raising {fund['current_raise']}")
    if _g(fund, "valuation"):
        f_clauses.append(f"at {fund['valuation']} valuation")
    prev = fund.get("previous_rounds", [])
    if prev:
        prev_strs = []
        for r in prev[:3]:
            if isinstance(r, dict):
                amt = r.get("amount", "")
                dt = r.get("date", r.get("year", ""))
                prev_strs.append(f"{amt} ({dt})" if dt else amt)
            else:
                prev_strs.append(str(r))
        if prev_strs:
            f_clauses.append(f"with prior rounds: {' | '.join(prev_strs)}")
    investors = fund.get("investors", [])
    if investors:
        f_clauses.append(f"backed by {', '.join(investors[:3])}")
    uof = fund.get("use_of_funds", [])
    if uof:
        if isinstance(uof, str) and uof.strip():
            f_clauses.append(f"for {uof[:200]}")
        elif isinstance(uof, list):
            f_clauses.append(f"for {', '.join(str(f).strip() for f in uof[:2] if str(f).strip())}")
    output.append(f"  {_join_clauses(f_clauses)}." if f_clauses else "  Funding details not explicitly stated in the deck.")
    output.append("")

    # 8. PIPELINE
    pipe = structured_data.get("pipeline", {})
    output.append("### PIPELINE")
    pl_clauses = []
    if _g(pipe, "pipeline_value"):
        pl_clauses.append(f"pipeline value of {pipe['pipeline_value']}")
    if _g(pipe, "lois"):
        pl_clauses.append(f"with {pipe['lois']} LOIs")
    if _g(pipe, "expected_close"):
        pl_clauses.append(f"expected close by {pipe['expected_close']}")
    prospects = pipe.get("prospects", [])
    if isinstance(prospects, list) and prospects:
        pl_clauses.append(f"prospects include {', '.join(str(p) for p in prospects[:3])}")
    elif isinstance(prospects, str) and prospects.strip():
        pl_clauses.append(f"prospects: {prospects[:100]}")
    output.append(f"  {_join_clauses(pl_clauses)}." if pl_clauses else "  Pipeline information not explicitly stated in the deck.")
    output.append("")

    # 9. REVENUE DETAILS
    rev_det = structured_data.get("revenue_details", {})
    output.append("### REVENUE DETAILS")
    r_clauses = []
    current = _g(rev_det, "current_revenue")
    if current:
        r_clauses.append(f"current revenue of {current}")
    projs = rev_det.get("projections", [])
    if projs:
        p_strs = [f"{p.get('period','')} {p.get('value','')}".strip() for p in projs[:2] if isinstance(p, dict) and p.get('value')]
        if p_strs:
            r_clauses.append(f"projecting {' | '.join(p_strs)}")
    output.append(f"  {_join_clauses(r_clauses)}." if r_clauses else "  Revenue details not explicitly stated in the deck.")
    output.append("")

    # 10. COMPETITIVE LANDSCAPE
    comp = structured_data.get("competition", {})
    output.append("### COMPETITIVE LANDSCAPE")
    cc_clauses = []
    competitors = comp.get("competitors", [])
    if isinstance(competitors, list) and competitors:
        # Filter pronouns and short fragments
        pronoun_pattern = re.compile(r'^(they|it|he|she|them|these|those|we|you|i)\W*$', re.IGNORECASE)
        valid_competitors = [str(c) for c in competitors[:5] if str(c).strip() and len(str(c).strip()) > 2 and not pronoun_pattern.match(str(c).strip())]
        if valid_competitors:
            cc_clauses.append(f"key players: {safe_join(valid_competitors, ', ')}")
    if _g(comp, "differentiation"):
        d = comp['differentiation'].strip().rstrip(",")
        if d and len(d) > 2:
            cc_clauses.append(f"differentiated by {d}")
    if _g(comp, "moat"):
        m = comp['moat'].strip().rstrip(",")
        if m and len(m) > 2:
            cc_clauses.append(f"moat: {m}")
    if _g(comp, "market_position"):
        mp = comp['market_position'].strip().rstrip(",")
        if mp and len(mp) > 2:
            cc_clauses.append(f"position: {mp}")
    cc_clauses = _filter_empty_clause_parts(cc_clauses)
    output.append(f"  {_join_clauses(cc_clauses)}." if cc_clauses else "  No explicit competitors identified in the deck.")
    output.append("")

    # 11. AWARDS & RECOGNITION
    rec = structured_data.get("recognition", {})
    output.append("### AWARDS & RECOGNITION")
    a_clauses = []
    awards = rec.get("awards", [])
    if isinstance(awards, list) and awards:
        a_clauses.append(f"awards: {', '.join(str(a) for a in awards[:3])}")
    elif isinstance(awards, str) and awards.strip():
        a_clauses.append(f"awards: {awards[:100]}")
    certs = rec.get("certifications", [])
    if isinstance(certs, list) and certs:
        a_clauses.append(f"certifications: {', '.join(str(c) for c in certs[:3])}")
    elif isinstance(certs, str) and certs.strip():
        a_clauses.append(f"certifications: {certs[:100]}")
    media = rec.get("media_coverage", [])
    if isinstance(media, list) and media:
        a_clauses.append(f"featured in {', '.join(str(m) for m in media[:2])}")
    elif isinstance(media, str) and media.strip():
        a_clauses.append(f"media: {media[:100]}")
    accel = rec.get("accelerators", [])
    if isinstance(accel, list) and accel:
        a_clauses.append(f"accelerated by {', '.join(str(a) for a in accel[:2])}")
    rec_notes = rec.get("notes", "")
    if rec_notes:
        a_clauses.append(f"recognition: {rec_notes[:200]}")
    output.append(f"  {_join_clauses(a_clauses)}." if a_clauses else "  Recognition details not explicitly stated in the deck.")
    output.append("")

    # VALIDATION NOTES
    warnings = structured_data.get("_validation_warnings", [])
    if warnings:
        output.append("### DATA QUALITY NOTES")
        for w in warnings:
            output.append(f"  \u26a0\ufe0f {w}")
        output.append("")

    return "\n".join(output)

def safe_int(value, default=0):
    """Safely convert value to int - handles strings like '105% YoY', '90 confidence'"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        match = re.search(r'\d+', value.strip())
        if match:
            try:
                return int(match.group())
            except:
                pass
    return default


def _fy_range(fy_year: str) -> str:
    """Convert 'FY2026' → 'FY25-26'. Given a year number string."""
    yr = int(fy_year[-2:]) if fy_year else 0
    if yr == 0:
        return ""
    prev = (yr - 1) % 100
    return f"FY{prev:02d}-{yr:02d}"


def format_period_short(period: str) -> str:
    """Convert period string to compact display format.
    'FY2026' -> 'FY25-26' | 'Q3 FY2026' -> 'Q3 FY25-26' | '2026' -> 'FY25-26'
    """
    if not period:
        return ""
    period = period.strip()
    q_match = re.search(r'(Q[1-4])[\s\-]*(?:FY[\s\-]*)?(\d{2,4})', period, re.IGNORECASE)
    if q_match:
        yr = q_match.group(2)
        yr = f"20{yr}" if len(yr) == 2 else yr
        return f"{q_match.group(1).upper()} {_fy_range(yr)}"
    fy_match = re.search(r'FY[\s\-]*(\d{2,4})', period, re.IGNORECASE)
    if fy_match:
        yr = fy_match.group(1)
        yr = f"20{yr}" if len(yr) == 2 else yr
        return _fy_range(yr)
    yr_match = re.search(r'\b(20\d{2})\b', period)
    if yr_match:
        return _fy_range(yr_match.group(1))
    return period


def extract_metrics_from_structured(structured_data, canonical_dict=None):
    """Extract boolean metrics from structured data or canonical registry for scoring.
    When canonical_dict is provided, uses ontology-correct classifications."""
    metrics = {}

    if canonical_dict:
        try:
            c = canonical_dict
            metrics["revenue"] = bool(c.get("invoiced_amount", {}).get("value") or
                                       c.get("purchase_order_value", {}).get("value") or
                                       c.get("total_revenue", {}).get("value") or
                                       c.get("current_period_revenue", {}).get("value"))
            metrics["orders"] = bool(c.get("orders", {}).get("value") or
                                      c.get("expected_units", {}).get("value"))
            metrics["customers"] = bool(c.get("customers", {}).get("value"))
            metrics["market"] = bool(c.get("tam", {}).get("value"))
            metrics["funding"] = bool(c.get("funding_raise", {}).get("value"))
            metrics["pipeline"] = bool(c.get("pipeline_value", {}).get("value"))
            metrics["margin"] = bool(c.get("current_period_revenue", {}).get("value") or
                                      c.get("invoiced_amount", {}).get("value"))
            metrics["revenue_detailed"] = bool(c.get("current_period_revenue", {}).get("value") or
                                                c.get("total_revenue", {}).get("value"))
            metrics["team"] = bool(structured_data.get("company_brief", {}).get("name"))
            rec = structured_data.get("recognition", {}) or {}
            metrics["recognition"] = bool(rec.get("awards") or rec.get("certifications"))
            missing = structured_data.get("insights", {}).get("missing_data", [])
            metrics["missing_sustainability"] = isinstance(missing, list) and len(missing) >= 2
            return metrics
        except Exception:
            pass

    # Fallback: read from raw structured_data
    if not structured_data:
        return {}
    try:
        tr = structured_data.get("traction", {})
        rev = tr.get("revenue", "")
        if isinstance(rev, dict):
            rev = rev.get("value", "")
        if rev:
            metrics["revenue"] = True
        orders = tr.get("orders", "")
        if isinstance(orders, dict):
            orders = orders.get("value", "")
        if orders:
            metrics["orders"] = True
        cust = tr.get("customers", "")
        if isinstance(cust, dict):
            cust = cust.get("value", "")
        if cust:
            metrics["customers"] = True
    except Exception as e:
        print(f"[WARNING] Traction metrics error: {e}")

    try:
        rd = structured_data.get("revenue_details", {})
        if rd.get("current_revenue"):
            metrics["margin"] = True
            metrics["revenue_detailed"] = True
    except:
        pass
    try:
        ind = structured_data.get("industry_overview", {})
        if ind.get("tam"):
            metrics["market"] = True
    except:
        pass
    try:
        brief = structured_data.get("company_brief", {})
        if brief.get("name"):
            metrics["team"] = True
    except:
        pass
    try:
        fund = structured_data.get("funding", {})
        if fund.get("current_raise"):
            metrics["funding"] = True
    except:
        pass
    try:
        pipe = structured_data.get("pipeline", {})
        if pipe.get("pipeline_value") or pipe.get("lois"):
            metrics["pipeline"] = True
    except:
        pass
    try:
        rec = structured_data.get("recognition", {})
        if rec.get("awards") or rec.get("certifications"):
            metrics["recognition"] = True
    except:
        pass
    try:
        missing = structured_data.get("insights", {}).get("missing_data", [])
        if isinstance(missing, list) and len(missing) >= 2:
            metrics["missing_sustainability"] = True
    except:
        pass

    return metrics


def _extract_first_num(s):
    if not s:
        return 0
    if isinstance(s, dict):
        s = s.get("value", "")
    s_str = str(s)
    m = re.search(r'[\d.]+', s_str.replace(',', ''))
    if not m:
        return 0
    return _parse_indian_number(s_str) or float(m.group())


def validate_metric_slots(structured_data):
    """Sanity-check metric assignments to prevent slot swapping."""
    ind = structured_data.get("industry_overview", {})
    tr = structured_data.get("traction", {})
    rev = structured_data.get("revenue_details", {})
    pipe = structured_data.get("pipeline", {})
    fund = structured_data.get("funding", {})

    warnings = []

    tam = _extract_first_num(ind.get("tam", ""))
    sam = _extract_first_num(ind.get("sam", ""))
    som = _extract_first_num(ind.get("som", ""))
    rev_num = _extract_first_num(tr.get("revenue", ""))

    if tam and sam and tam < sam:
        warnings.append("TAM < SAM — likely swapped")
    if sam and som and sam < som:
        warnings.append("SAM < SOM — likely swapped")
    if tam and rev_num and tam < rev_num:
        warnings.append("TAM < Revenue — TAM likely contains revenue value")

    pipe_num = _extract_first_num(pipe.get("pipeline_value", ""))
    if pipe_num and rev_num and abs(pipe_num - rev_num) / max(pipe_num, rev_num, 1) < 0.05:
        warnings.append("Pipeline ≈ Revenue — likely same value copied")

    val = _extract_first_num(fund.get("valuation", ""))
    raise_amt = _extract_first_num(fund.get("current_raise", ""))
    if val and raise_amt and val < raise_amt:
        warnings.append("Valuation < Raise amount — likely swapped")

    # 5. TAM/SAM ratio sanity
    if tam and sam and sam / tam < 0.05:
        warnings.append(f"SAM is only {sam/tam*100:.0f}% of TAM — market sizes may be incorrect")

    # 7. Stage check removed — too many false positives (stage stated in deck but not in funding fields)

    structured_data["_validation_warnings"] = warnings
    if warnings:
        print(f"[VALIDATION] {len(warnings)} warning(s): {'; '.join(warnings)}")
    return structured_data


def ensure_fy_on_metrics(structured_data, default_period="FY25-26"):
    """Append FY label to any financial metric missing it."""
    fy_pattern = re.compile(r'\(FY\d{2}-\d{2}\)')
    metric_fields = [
        ("industry_overview", ["tam", "sam", "som"]),
        ("traction", ["revenue"]),
        ("revenue_details", ["current_revenue"]),
        ("pipeline", ["pipeline_value"]),
        ("funding", ["current_raise", "valuation"]),
    ]
    for section_name, fields in metric_fields:
        section = structured_data.get(section_name, {})
        for field in fields:
            val = section.get(field, "")
            if val and isinstance(val, str) and not fy_pattern.search(val) and re.search(r'\d', val):
                section[field] = f"{val} ({default_period})"
    return structured_data


def generate_all(chunks_by_section, intent, company_name="Unknown Company", domain="General", retriever_fn=None):
    key_signal = "Insufficient data to determine a strong investment signal."
    summary = "Analysis failed"
    email = f"Hi [Name],\n\nThanks for your interest in {company_name}. Happy to schedule a call to discuss further."
    extracted_data = {}

    if not chunks_by_section or all(not v for v in chunks_by_section.values()):
        print("[WARNING] No chunks retrieved for generation.")
        return {
            "summary": "Analysis Failed - No relevant data could be retrieved from the document.",
            "email": "Unable to generate email - no context found.",
            "key_signal": "N/A",
            "rag_status": "empty_rag",
            "extracted_metrics": {}
        }

    # ── Company Identity Resolution (Layer 2–5) ─────────────────────────
    first_page_text = ""
    all_page_chunks = []
    for section, chunks in chunks_by_section.items():
        if chunks:
            all_page_chunks.extend(chunks)
            if not first_page_text and isinstance(chunks[0], str):
                first_page_text = chunks[0][:2000]
            elif not first_page_text and isinstance(chunks[0], dict):
                first_page_text = str(chunks[0].get("text", chunks[0].get("content", "")))[:2000]

    resolved_name = CompanyIdentityResolver.resolve(
        llm_name=company_name if company_name != "Unknown Company" else None,
        first_page_text=first_page_text,
        filename=intent.get("filename", "") if isinstance(intent, dict) else "",
        all_chunks_text=[str(c) if isinstance(c, str) else str(c.get("text", c.get("content", ""))) for c in all_page_chunks[:5]],
        domain_hint=domain if domain != "General" else None,
    )
    if resolved_name:
        company_name = resolved_name
        print(f"[RESOLVER] Company identity resolved: '{company_name}'")

    try:
        LOCAL_MAX_CONTEXT_CHARS = 8000

        def _truncate_context(text: str, max_chars: int) -> str:
            if len(text) <= max_chars:
                return text
            head = int(max_chars * 0.7)
            tail = max_chars - head
            result = text[:head] + "\n...[TRUNCATED]...\n" + text[-tail:]
            # Prevent splitting currency/number patterns in half
            result = re.sub(r'(₹?[\d,]+\.?[\d]*)\s*\.\.\.\[TRUNCATED\]\.\.\.\s*', r'\1... ', result)
            return result

        BUDGET = LOCAL_MAX_CONTEXT_CHARS
        fin_context_norm = ""
        mkt_context_norm = ""
        co_context = ""

        def _build_context(section_groups: List[List[str]], budget: int) -> str:
            """Build context from grouped sections. Each group's sections are merged together."""
            if not section_groups:
                return ""
            parts = []
            per_group_budget = budget // max(len(section_groups), 1)
            for group in section_groups:
                group_text = ""
                for section in group:
                    chunks = chunks_by_section.get(section, [])
                    if chunks:
                        section_text = limit_context(chunks, max_chars=per_group_budget)
                        if section_text.strip():
                            header = section.upper().replace("FINANCIALS", "FINANCIALS & METRICS")
                            group_text += f"[{header}]\n{section_text}\n\n"
                if group_text.strip():
                    parts.append(group_text.strip())
            return "\n\n".join(parts) if parts else ""

        def _call_agent(prompt_body: str, agent_name: str) -> dict:
            cache_key = hashlib.md5(prompt_body.encode()).hexdigest()
            if cache_key in _LLM_CACHE:
                print(f"[CACHE] {agent_name} cache HIT — reusing previous response")
                return _LLM_CACHE[cache_key]
            try:
                print(f"[DEBUG] {agent_name} prompt tokens (approx): {count_tokens(prompt_body)}")
                resp = safe_client().chat_completion(
                    messages=[{"role": "user", "content": prompt_body}],
                    temperature=0.1,
                    max_tokens=MAX_OUTPUT_TOKENS
                )
                print(f"\n========== {agent_name} RAW OUTPUT ==========\n")
                try:
                    print(str(resp)[:1500])
                except UnicodeEncodeError:
                    print(str(resp)[:1500].encode('ascii', errors='replace').decode('ascii'))
                print(f"\n==========================================\n")

                safe_name = "".join(c for c in company_name if c.isalnum() or c in " _-").strip().replace(" ", "_")[:40]
                debug_file = f"debug_{safe_name}.txt"
                with open(debug_file, "a", encoding="utf-8") as f:
                    f.write(f"[{agent_name}]\n=== RAW ===\n{str(resp)}\n\n=== CLEANED ===\n{clean_llm_json(resp)}\n\n---\n")

                cleaned = clean_llm_json(resp)
                parsed = recover_json(cleaned)
                if parsed and isinstance(parsed, dict):
                    print(f"[DEBUG] {agent_name} extracted {len(parsed)} top-level keys")
                    if len(_LLM_CACHE) < _LLM_CACHE_MAX:
                        _LLM_CACHE[cache_key] = parsed
                    return parsed
                print(f"[WARNING] {agent_name} returned unparseable JSON, trying fallback")
                fb = fallback_section_extraction(cleaned)
                if fb and isinstance(fb, dict):
                    if len(_LLM_CACHE) < _LLM_CACHE_MAX:
                        _LLM_CACHE[cache_key] = fb
                    return fb
                _LLM_CACHE[cache_key] = {}
                return {}
            except Exception as e:
                print(f"[WARNING] {agent_name} failed: {e}")
                _LLM_CACHE[cache_key] = {}
                return {}

        # Build contexts for all 3 agents (fast, string ops only)
        # Fix: The orchestrator provides these keys: 'financial', 'business', 'market', 'leadership', 'traction', 'competition'
        fin_context = _build_context([["financial", "traction"]], 4000)
        mkt_context = _build_context([["market"]], BUDGET // 5)
        co_context = _build_context([["leadership", "business", "competition"]], 2500)

        # Prepare agent tasks
        agent_tasks = []

        if fin_context:
            fin_context_norm = normalize_numbers(fin_context)
            fin_context_norm = _truncate_context(fin_context_norm, 4000)
            
            # Agent A: Traction & Revenue Agent
            agent_a_prompt = f"""Extract financial traction and revenue details from the pitch deck context below.

Every financial metric value MUST be extracted as a structured object binding it directly to its source slide and evidence text.

Each metric object MUST have this structure:
{{
  "value": "string or null", 
  "source_slide": integer or null, 
  "evidence_text": "verbatim sentence or phrase matching the metric or null", 
  "metric_type": "string (revenue, orders, customers)",
  "confidence_tier": "explicit" | "derived" | "inferred" | null,
  "confidence": float or null
}}

Fields to extract:

traction:
  - revenue: Actual EARNED revenue from operations/invoicing (as a structured metric object).
    * Invoiced amounts = revenue. PO values = pipeline. Grants = funding.
    * "₹90 Lakhs for 7 units" = contract/project value, NOT revenue.
    * "₹200+ Cr expected PO" = expected purchase order, NOT revenue.
  - revenue_time_type: "historical" | "projected" | "ARR" | "run-rate" | "target" | "pipeline" | "booked" | "contracted" | null
  - orders: Actual completed orders/bookings (as structured object). NOT expected/pipeline.
  - orders_time_type: same as revenue_time_type
  - customers: Actual paying customers/companies served (as structured object).
  - customers_time_type: same as revenue_time_type
  - key_milestones: list of milestone strings

revenue_details:
  - current_revenue: current period revenue value (as structured object, overlaps with traction.revenue).
  - current_revenue_time_type: temporal classification.
  - projections: list of {{period, value}} objects.

additional_metrics: array of {{key, value, context}} for other metrics (like govt_grants, unit_count).

INFERENCE GOVERNOR & ONTOLOGY RULES:
1. DO NOT guess, infer, or extrapolate to complete missing standard templates. If there is no explicit or derived evidence for a field, you MUST set its "value" to null.
2. Every extracted "value" string must include units and currency. Never bare numbers.

JSON SCHEMA ONLY:
{{
  "traction": {{
    "revenue": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"revenue","confidence_tier":null,"confidence":null}},
    "revenue_time_type": null,
    "orders": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"orders","confidence_tier":null,"confidence":null}},
    "orders_time_type": null,
    "customers": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"customers","confidence_tier":null,"confidence":null}},
    "customers_time_type": null,
    "key_milestones": []
  }},
  "revenue_details": {{
    "current_revenue": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"revenue","confidence_tier":null,"confidence":null}},
    "current_revenue_time_type": null,
    "projections": []
  }},
  "additional_metrics": []
}}

Financial context:
{fin_context_norm}"""
            agent_tasks.append((agent_a_prompt, "AgentA"))

            # Agent B: Funding & Valuation Agent
            agent_b_prompt = f"""Extract funding and pipeline details from the pitch deck context below.

Every financial metric value MUST be extracted as a structured object binding it directly to its source slide and evidence text.

Each metric object MUST have this structure:
{{
  "value": "string or null", 
  "source_slide": integer or null, 
  "evidence_text": "verbatim sentence or phrase matching the metric or null", 
  "metric_type": "string (current_raise, valuation, pipeline_value, lois)",
  "confidence_tier": "explicit" | "derived" | "inferred" | null,
  "confidence": float or null
}}

Fields to extract:

funding:
  - current_raise: Active funding round details (as structured object).
    * If a range is shown, extract the highest amount with context.
  - valuation: Company pre/post-money valuation (as structured object).
  - previous_rounds: list of previous round amounts.
  - investors: list of investor names.
  - use_of_funds: list of fund usage categories.

pipeline:
  - pipeline_value: Future deals, expected contracts, POs (as structured object).
  - lois: Letters of Intent value (as structured object).
  - prospects: list of prospect descriptions.

JSON SCHEMA ONLY:
{{
  "funding": {{
    "current_raise": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"current_raise","confidence_tier":null,"confidence":null}},
    "valuation": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"valuation","confidence_tier":null,"confidence":null}},
    "previous_rounds": [],
    "investors": [],
    "use_of_funds": []
  }},
  "pipeline": {{
    "pipeline_value": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"pipeline_value","confidence_tier":null,"confidence":null}},
    "lois": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"lois","confidence_tier":null,"confidence":null}},
    "prospects": []
  }}
}}

Financial context:
{fin_context_norm}"""
            agent_tasks.append((agent_b_prompt, "AgentB"))

        # Agent C: Market TAM-SAM-SOM Agent
        if mkt_context:
            mkt_context_norm = normalize_numbers(mkt_context)
            mkt_context_norm = _truncate_context(mkt_context_norm, 1500)
            agent_c_prompt = f"""Extract market intelligence from the pitch deck context below.

Every market metric (TAM, SAM, SOM) MUST be extracted as a structured object binding it directly to its source slide and evidence text.

Each metric object MUST have this structure:
{{
  "value": "string or null", 
  "source_slide": integer or null, 
  "evidence_text": "verbatim sentence or phrase matching the metric or null", 
  "metric_type": "string (tam, sam, som)",
  "confidence_tier": "explicit" | "derived" | "inferred" | null,
  "confidence": float or null
}}

Fields to extract ONLY:

industry_overview:
  - tam: Total Addressable Market — LARGEST market number (as structured object).
  - sam: Subset of TAM (as structured object). Smallest.
  - som: Share of Market (as structured object). Smallest.
  - market_context: 1-2 sentence description of market landscape.
  - key_trends: list of key trends (4-6).

INFERENCE GOVERNOR & ONTOLOGY RULES:
1. DO NOT promote general macroeconomic/productivity statistics to TAM/SAM/SOM.
2. If the deck does not explicitly define TAM, SAM, or SOM, you MUST leave the "value" of that metric object null. Do not guess, speculate, or invent numbers.
3. Preserve original units. Do NOT convert between currency and jobs/non-currency.

JSON SCHEMA ONLY:
{{
  "industry_overview": {{
    "tam": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"tam","confidence_tier":null,"confidence":null}},
    "sam": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"sam","confidence_tier":null,"confidence":null}},
    "som": {{"value":null,"source_slide":null,"evidence_text":null,"metric_type":"som","confidence_tier":null,"confidence":null}},
    "market_context": "",
    "key_trends": []
  }}
}}

Market context:
{mkt_context_norm}"""
            agent_tasks.append((agent_c_prompt, "AgentC"))

        if co_context:
            # Agent D: Founders/Management Agent
            agent_d_prompt = f"""Extract founders, leadership, and management team information from the pitch deck context below.

Each founder/team member MUST be extracted as an object inside the "founders" list.

JSON SCHEMA ONLY:
{{
  "founders": [
    {{
      "name": "founder/team member name",
      "role": "founder/team member role (e.g. CEO, CTO)",
      "background": "brief past experience, previous employers, or university",
      "experience_years": integer or null,
      "linkedin": "linkedin URL or null"
    }}
  ]
}}

Company context:
{co_context}"""
            agent_tasks.append((agent_d_prompt, "AgentD"))

            # Agent E: Competitive Moats/Differentiation Agent
            agent_e_prompt = f"""Extract competition, moat, differentiation, and recognition details from the pitch deck context below.

STRICT ENTITY ROLE CLASSIFICATION RULES:
- competition:
  * competitors: Extract ONLY actual direct/indirect competitors mentioned in the deck (e.g. other platforms or software).
  * CRITICAL: DO NOT extract founder background employers (e.g. "ex-Flipkart", "worked at Airtel").
  * CRITICAL: DO NOT extract case study entities, customers, or partners.
  * If no competitors are explicitly stated, return an empty array [].

JSON SCHEMA ONLY:
{{
  "competition": {{
    "competitors": [],
    "differentiation": "how the company differentiates itself",
    "moat": "barriers to entry or proprietary IP",
    "market_position": "current standing in market"
  }},
  "recognition": {{
    "awards": [],
    "certifications": [],
    "media_coverage": []
  }}
}}

Company context:
{co_context}"""
            agent_tasks.append((agent_e_prompt, "AgentE"))

            # Company Profile Agent
            co_prompt = f"""Extract general company profile details from the pitch deck context below.

JSON SCHEMA ONLY:
{{
  "company_brief": {{"name":"","tagline":"","one_liner":"","stage":"","sector":""}},
  "business_overview": {{"model":"","revenue_model":"","target_customers":"","gtm":"","differentiator":""}},
  "problem": {{"statement":"","pain_points":[]}},
  "solution": {{"description":"","key_features":[],"technology":"","usp":""}}
}}

Company context:
{co_context}"""
            agent_tasks.append((co_prompt, "CompanyAgent"))

        # Run all agents in parallel
        agent_a_result, agent_b_result, agent_c_result, agent_d_result, agent_e_result, co_result = {}, {}, {}, {}, {}, {}
        if agent_tasks:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(agent_tasks)) as executor:
                future_map = {executor.submit(_call_agent, prompt, name): name for prompt, name in agent_tasks}
                for future in concurrent.futures.as_completed(future_map):
                    name = future_map[future]
                    try:
                        result = future.result()
                        if name == "AgentA":
                            agent_a_result = result
                        elif name == "AgentB":
                            agent_b_result = result
                        elif name == "AgentC":
                            agent_c_result = result
                        elif name == "AgentD":
                            agent_d_result = result
                        elif name == "AgentE":
                            agent_e_result = result
                        elif name == "CompanyAgent":
                            co_result = result
                    except Exception as e:
                        print(f"[WARNING] {name} failed: {e}")

        # Merge results from all agents
        structured_data = {}
        for r in [co_result, agent_e_result, agent_d_result, agent_c_result, agent_b_result, agent_a_result]:
            if r:
                for k, v in r.items():
                    if v or k not in structured_data:
                        structured_data[k] = v

        # Ensure all expected keys exist (fill missing with defaults)
        defaults = {
            "company_brief": {"name": company_name, "tagline": "", "one_liner": "", "stage": "", "sector": ""},
            "business_overview": {"model": "", "revenue_model": "", "target_customers": "", "gtm": "", "differentiator": ""},
            "industry_overview": {"tam": "", "sam": "", "som": "", "market_context": "", "key_trends": []},
            "problem": {"statement": "", "pain_points": []},
            "solution": {"description": "", "key_features": [], "technology": "", "usp": ""},
            "traction": {"revenue": "", "revenue_time_type": "", "orders": "", "orders_time_type": "", "customers": "", "customers_time_type": "", "key_milestones": []},
            "funding": {"current_raise": "", "valuation": "", "previous_rounds": [], "investors": [], "use_of_funds": []},
            "pipeline": {"pipeline_value": "", "lois": "", "prospects": []},
            "revenue_details": {"current_revenue": "", "current_revenue_time_type": "", "projections": []},
            "recognition": {"awards": [], "certifications": [], "media_coverage": []},
            "competition": {"competitors": [], "differentiation": "", "moat": "", "market_position": ""},
            "founders": [],
            "additional_metrics": [],
        }
        for key, default in defaults.items():
            if key not in structured_data or not structured_data[key]:
                structured_data[key] = default
            elif isinstance(structured_data[key], str):
                # Agent returned string instead of dict — replace with default
                structured_data[key] = default
            elif isinstance(structured_data[key], dict) and isinstance(default, dict):
                for sub_key, sub_default in default.items():
                    if sub_key not in structured_data[key] or not structured_data[key][sub_key]:
                        structured_data[key][sub_key] = sub_default

        # Filter positioning statements from competitors (e.g., "Amazon of Renewables")
        comp_data = structured_data.get("competition", {}) or {}
        if not isinstance(comp_data, dict):
            comp_data = {}
        comp_list = comp_data.get("competitors", [])
        if isinstance(comp_list, list) and comp_list:
            filtered = []
            for c in comp_list:
                c_str = str(c) if isinstance(c, str) else (c.get("name", "") if isinstance(c, dict) else "")
                if _has_positioning_language(c_str):
                    print(f"[COMPETITOR] Filtered positioning statement: '{c_str}'")
                    continue
                filtered.append(c)
            comp_data["competitors"] = filtered
            structured_data["competition"] = comp_data

        # Standardize all metric fields to structured objects
        for field, m_type in [("revenue", "revenue"), ("orders", "orders"), ("customers", "customers")]:
            structured_data["traction"][field] = normalize_to_metric_object(structured_data["traction"].get(field), m_type)
        
        for field, m_type in [("current_raise", "current_raise"), ("valuation", "valuation")]:
            structured_data["funding"][field] = normalize_to_metric_object(structured_data["funding"].get(field), m_type)
            
        for field, m_type in [("pipeline_value", "pipeline_value"), ("lois", "lois")]:
            structured_data["pipeline"][field] = normalize_to_metric_object(structured_data["pipeline"].get(field), m_type)
            
        for field, m_type in [("tam", "tam"), ("sam", "sam"), ("som", "som")]:
            structured_data["industry_overview"][field] = normalize_to_metric_object(structured_data["industry_overview"].get(field), m_type)
            
        structured_data["revenue_details"]["current_revenue"] = normalize_to_metric_object(structured_data["revenue_details"].get("current_revenue"), "revenue")

        print(f"[DEBUG] Merged {len(structured_data)} sections from agents")

        # ── Semantic Fallback Intelligence (Phase 3) ──────────────────
        full_chunks_text = " ".join(
            str(c) if isinstance(c, str) else str(c.get("text", c.get("content", "")))
            for section_chunks in chunks_by_section.values()
            for c in (section_chunks or [])
        ) if chunks_by_section else ""
        if full_chunks_text:
            from app.rag.semantic_fallback import FallbackInferenceEngine
            fallback_updates = FallbackInferenceEngine.infer_all(full_chunks_text, structured_data)
            for section, updates in fallback_updates.items():
                if isinstance(updates, dict):
                    existing = structured_data.get(section, {})
                    if isinstance(existing, dict):
                        for k, v in updates.items():
                            if v and not existing.get(k):
                                existing[k] = v
                        structured_data[section] = existing
                    elif isinstance(existing, str) and not existing:
                        structured_data[section] = updates
                elif isinstance(updates, str) and updates:
                    if not structured_data.get(section):
                        structured_data[section] = updates
            print(f"[FALLBACK] Semantic inference applied")

        # ── Visual Intelligence (Phase 1) — extract chart metrics from context ──
        _visual_confidence = 0.0
        vis_json_match = re.search(r'\[VISUAL_GRAPH\]\s*(\{.*?\})\s*\[/VISUAL_GRAPH\]', full_chunks_text, re.DOTALL)
        if vis_json_match:
            try:
                import json as _json
                visual_graph = _json.loads(vis_json_match.group(1))
                from app.rag.visual_intelligence import merge_chart_metrics
                structured_data = merge_chart_metrics(structured_data, visual_graph)
                injected_count = len(visual_graph)
                print(f"[VISUAL] Injected {injected_count} chart-derived metric fields")
                _visual_confidence = min(1.0, 0.5 + injected_count * 0.1) if injected_count > 0 else 0.3
            except Exception as ve:
                print(f"[VISUAL] Failed to parse visual graph: {ve}")
                _visual_confidence = 0.0
        else:
            print("[VISUAL] No visual graph found in LLM output")
            _visual_confidence = 0.0
        
        # ── Layout-based fallback extraction ──────────────────────────
        # Even without LLM visual graph, extract KPIs from raw text layout
        if _visual_confidence < 0.5 and full_chunks_text:
            try:
                from app.rag.enhanced_layout_segmenter import segment_page, extract_kpis
                from app.rag.financial_value_parser import parse_financial_value
                
                # Segment the full text and extract KPI cards
                page_layout = segment_page(full_chunks_text, page_num=0)
                kpis = extract_kpis(page_layout)
                
                if kpis:
                    print(f"[VISUAL] Layout fallback: extracted {len(kpis)} KPI cards from text")
                    for kpi in kpis:
                        label = kpi.get("label", "").lower()
                        value = kpi.get("value", "")
                        # Try to map KPI to structured data fields
                        if "tam" in label or "total addressable" in label:
                            if not structured_data.get("industry_overview", {}).get("tam"):
                                structured_data.setdefault("industry_overview", {})["tam"] = value
                        elif "sam" in label or "serviceable" in label:
                            if not structured_data.get("industry_overview", {}).get("sam"):
                                structured_data.setdefault("industry_overview", {})["sam"] = value
                        elif "som" in label or "obtainable" in label:
                            if not structured_data.get("industry_overview", {}).get("som"):
                                structured_data.setdefault("industry_overview", {})["som"] = value
                        elif "revenue" in label:
                            if not structured_data.get("traction", {}).get("revenue"):
                                structured_data.setdefault("traction", {})["revenue"] = value
                        elif "customer" in label:
                            if not structured_data.get("traction", {}).get("customers"):
                                structured_data.setdefault("traction", {})["customers"] = value
                        elif "valuation" in label:
                            if not structured_data.get("funding", {}).get("valuation"):
                                structured_data.setdefault("funding", {})["valuation"] = value
                    
                    _visual_confidence = min(0.6, 0.3 + len(kpis) * 0.08)
                    print(f"[VISUAL] Layout fallback confidence: {_visual_confidence:.2f}")
            except Exception as le:
                print(f"[VISUAL] Layout fallback extraction failed: {le}")
                if _visual_confidence == 0.0:
                    _visual_confidence = 0.1

        # Run validation and normalization pipeline
        structured_data = normalize_llm_output(structured_data)
        structured_data = _migrate_to_flat_schema(structured_data)
        structured_data = apply_comprehensive_normalization(structured_data)
        structured_data = validate_metric_slots(structured_data)
        structured_data = ensure_fy_on_metrics(structured_data)
        # Use financial context for validation (or overall context as fallback)
        val_context = fin_context_norm if fin_context else co_context if co_context else ""
        structured_data = validate_financials(structured_data, val_context)

        field_confidence = calculate_field_confidence(structured_data, val_context)
        structured_data["_field_confidence"] = field_confidence

        # ── Visual / Text-based TAM/SAM/SOM fallback ────────────────
        ind = structured_data.get("industry_overview", {}) or {}
        if not ind.get("tam") or not ind.get("sam") or not ind.get("som"):
            full_text = val_context or " ".join(
                str(c) if isinstance(c, str) else str(c.get("text", c.get("content", "")))
                for section_chunks in chunks_by_section.values()
                for c in (section_chunks or [])
            )
            from app.rag.visual_parser import ConcentricCircleParser
            text_metrics = ConcentricCircleParser._fallback_text_parse(full_text)
            for tm in text_metrics:
                if tm.semantic_field == "tam" and not ind.get("tam"):
                    ind["tam"] = tm.value
                if tm.semantic_field == "sam" and not ind.get("sam"):
                    ind["sam"] = tm.value
                if tm.semantic_field == "som" and not ind.get("som"):
                    ind["som"] = tm.value
            structured_data["industry_overview"] = ind

        # ── Ontology Reject Layer (Phase 4) — reject invalid assignments ──
        from app.rag.ontology_constraints import OntologyRejectLayer
        structured_data, ontology_violations = OntologyRejectLayer.reject_invalid(structured_data)
        if ontology_violations:
            print(f"[ONTOLOGY REJECT] {len(ontology_violations)} violation(s) cleared")
        structured_data["_ontology_violations"] = [vars(v) for v in ontology_violations]

        # ── Financial Candidate Ranking (Phase 2) — score candidates per metric ──
        from app.rag.financial_candidate import FinancialCandidateRanker
        candidate_summary = FinancialCandidateRanker.get_scoring_summary(structured_data, val_context)
        if candidate_summary:
            structured_data["_candidate_scores"] = candidate_summary
            print(f"[CANDIDATES] Ranked {len(candidate_summary)} metric types")

        # ── Build Canonical Registry with Partial Failure Tolerance ──
        from app.rag.canonical_registry import CanonicalFactRegistry
        canonical_registry = CanonicalFactRegistry()
        try:
            canonical_registry = build_canonical_registry(structured_data)
            structured_data["_canonical"] = canonical_registry.to_dict()
        except Exception as canonical_error:
            print(f"[WARNING] Canonical registry build had issues: {canonical_error}")
            structured_data["_canonical"] = {}
            structured_data["_canonical_error"] = str(canonical_error)[:200]

        # ── Unified Validation Engine ────────────────────────────────
        structured_data, val_results = validate_all(structured_data)
        validation_flags_extended = [r.message for r in val_results if not r.passed]

        # ── Apply canonical overrides to structured_data ────────────
        overrides = structured_data.get("_canonical_overrides", {}) or {}
        if overrides:
            print(f"[CANONICAL] {len(overrides)} ontological overrides applied")
            pipe = structured_data.get("pipeline", {}) or {}
            addl = structured_data.get("additional_metrics", []) or []
            for k, v in overrides.items():
                if k.startswith("pipeline→") and "expected_po" in pipe:
                    structured_data["pipeline"] = pipe

        summary = format_structured_summary(structured_data, field_confidence=field_confidence)
        email = generate_narrative_email(company_name, structured_data, intent, canonical_registry)

        # P1: Filter generic LLM filler phrases from all generated text
        summary = _filter_generic_phrases(summary)
        email = _filter_generic_phrases(email)
        
        raw_signal = structured_data.get("insights", {}).get("key_signal", "")
        
        signal_parts = []
        _canon = structured_data.get("_canonical", {}) or {}
        
        def _canonical_value(*names):
            for name in names:
                entry = _canon.get(name)
                if entry and entry.get("value"):
                    return entry["value"]
            return None
        
        orders = _canonical_value("orders") or ""
        if orders and ("cr" in str(orders).lower() or "lakh" in str(orders).lower() or "advance" in str(orders).lower()):
            signal_parts.append(f"{orders} bookings")
        
        rev = _canonical_value("total_revenue", "current_period_revenue") or ""
        if rev and "₹" in str(rev):
            signal_parts.append(f"{rev} revenue")
        
        tam = _canonical_value("tam") or ""
        if tam:
            signal_parts.append(f"{tam} TAM")
        
        margin = _canonical_value("gross_margin") or ""
        if margin and "100" not in str(margin):
            signal_parts.append(f"{margin} margin")
        
        if signal_parts:
            key_signal = f"{signal_parts[0].title()}"
            if len(signal_parts) > 1:
                key_signal += f", {signal_parts[1]}"
        elif raw_signal and raw_signal != "N/A":
            key_signal = ensure_string(raw_signal)
        else:
            thesis = structured_data.get("insights", {}).get("investment_thesis", "")
            if thesis and len(thesis) > 30:
                key_signal = thesis[:100]
            else:
                sector_val = safe_get(structured_data, "company_info", "sector", default="technology")
                key_signal = f"Early commercial traction in {sector_val} sector with growth potential."
        
        extracted_data = extract_metrics_from_structured(structured_data, canonical_registry.to_dict())

        # Build crisp 2-line description
        brief = structured_data.get("company_brief", {})
        company = brief.get("name", company_name)
        tagline = brief.get("tagline", "")
        one_liner = brief.get("one_liner", "")
        sector = brief.get("sector", "")
        stage = brief.get("stage", "")
        tr = structured_data.get("traction", {}) or {}
        rev = tr.get("revenue", "") if isinstance(tr.get("revenue"), str) else (tr.get("revenue", {}) or {}).get("value", "")
        fund = structured_data.get("funding", {}).get("current_raise", "")

        line1_parts = [company]
        if stage:
            line1_parts.append(stage)
        if sector:
            line1_parts.append(sector)
        line1 = " | ".join(line1_parts)
        if tagline:
            line1 = f"{line1} — {tagline}"
        elif one_liner:
            line1 = f"{line1} — {one_liner}"

        line2_parts = []
        if rev:
            line2_parts.append(f"Revenue: {rev}")
        if fund:
            line2_parts.append(f"Raising: {fund}")
        if key_signal and len(key_signal) < 80:
            line2_parts.append(key_signal)
        line2 = " | ".join(line2_parts) if line2_parts else key_signal

        short_description = f"{line1}\n{line2}" if line2 else line1

        # Build financial_highlights from canonical registry + structured data
        tr = structured_data.get("traction", {})
        rd = structured_data.get("revenue_details", {})
        ind = structured_data.get("industry_overview", {})
        fund = structured_data.get("funding", {})
        pipe = structured_data.get("pipeline", {})

        # Use canonical registry for ontology-correct values
        _canon = structured_data.get("_canonical", {}) or {}
        _resolved = _canon.get("_resolved", _canon.get("resolved", {})) or _canon

        def _canonical_value(canon_name: str) -> str:
            """Get value from canonical registry by canonical_name."""
            if isinstance(_resolved, dict):
                for key, entry in _resolved.items():
                    if isinstance(entry, dict) and entry.get("canonical_name") == canon_name:
                        return entry.get("value_str", "")
                    if key == canon_name and isinstance(entry, dict):
                        return entry.get("value_str", "")
                    if key == canon_name and isinstance(entry, str):
                        return entry
            return ""

        canonical_revenue = _canonical_value("historical_revenue") or _canonical_value("total_revenue") or _canonical_value("invoiced_amount")
        canonical_tam = _canonical_value("tam") or ind.get("tam", "")
        canonical_sam = _canonical_value("sam") or ind.get("sam", "")
        canonical_som = _canonical_value("som") or ind.get("som", "")

        # Ontology-based metrics (from canonical registry or pipeline)
        expected_po = pipe.get("expected_po", "") or _canonical_value("purchase_order_value")
        government_grants = _canonical_value("government_grants") or ""
        pipeline_val = pipe.get("pipeline_value", "") or _canonical_value("pipeline_value")
        arr_run_rate = _canonical_value("arr_run_rate") or ""

        financial_highlights = {
            "current_revenue": canonical_revenue or tr.get("revenue", "") or rd.get("current_revenue", ""),
            "customers": tr.get("customers", ""),
            "orders": tr.get("orders", ""),
            "market_tam": canonical_tam,
            "market_sam": canonical_sam,
            "market_som": canonical_som,
            "funding_raise": fund.get("current_raise", ""),
            "funding_valuation": fund.get("valuation", ""),
            "pipeline_value": pipeline_val,
            "expected_po": expected_po,
            "government_grants": government_grants,
            "arr_run_rate": arr_run_rate,
            "projections": rd.get("projections", []) if isinstance(rd.get("projections"), list) else [],
        }

        # Phase 1E: Proper confidence scoring
        warnings = structured_data.get("_validation_warnings", [])
        confidence_by_section = {
            "revenue": "high" if field_confidence.get("revenue", 0) >= 0.7 else ("medium" if field_confidence.get("revenue", 0) >= 0.4 else "none"),
            "market": "high" if field_confidence.get("market", 0) >= 0.7 else ("medium" if field_confidence.get("market", 0) >= 0.4 else "none"),
            "funding": "high" if field_confidence.get("funding", 0) >= 0.7 else ("medium" if field_confidence.get("funding", 0) >= 0.4 else "none"),
            "traction": "high" if field_confidence.get("traction", 0) >= 0.7 else ("medium" if field_confidence.get("traction", 0) >= 0.4 else "none"),
            "team": "high" if field_confidence.get("company_brief.name", 0) >= 0.7 else "medium",
        }

        # P1: Cross-signal reasoning traces
        validation_flags = []
        reasoning_traces = []
        rev_val = tr.get("revenue", "") or rd.get("current_revenue", "")
        tam_val = ind.get("tam", "")
        sam_val = ind.get("sam", "")
        som_val = ind.get("som", "")
        try:
            from app.rag.number_utils import parse_indian_number
            rev_num = parse_indian_number(rev_val) if rev_val else None
            tam_num = parse_indian_number(tam_val) if tam_val else None
            sam_num = parse_indian_number(sam_val) if sam_val else None
            som_num = parse_indian_number(som_val) if som_val else None

            # TAM < SAM
            if tam_num and sam_num and tam_num < sam_num:
                validation_flags.append(f"TAM ({tam_val}) < SAM ({sam_val}) — values may be swapped")
                reasoning_traces.append(f"market_hierarchy: TAM={tam_val} < SAM={sam_val}, likely swapped (TAM should be ≥ SAM)")

            # SAM < SOM
            if sam_num and som_num and sam_num < som_num:
                validation_flags.append(f"SAM ({sam_val}) < SOM ({som_val}) — values may be swapped")
                reasoning_traces.append(f"market_hierarchy: SAM={sam_val} < SOM={som_val}, likely swapped (SAM should be ≥ SOM)")

            # Revenue > TAM
            if rev_num and tam_num and rev_num > tam_num:
                validation_flags.append(f"Revenue ({rev_val}) exceeds TAM ({tam_val}) — values may be misclassified")
                reasoning_traces.append(f"cross_signal: Revenue ({rev_val}) > TAM ({tam_val}), possible misclassification")

            # ARR vs Revenue cross-check
            if arr_run_rate and rev_val:
                arr_num = parse_indian_number(arr_run_rate)
                if arr_num and rev_num:
                    ratio = arr_num / rev_num if rev_num > 0 else 0
                    if ratio > 2:
                        reasoning_traces.append(f"cross_signal: ARR ({arr_run_rate}) is {ratio:.1f}x Revenue ({rev_val}), ARR may be annualized from a different period")
                    elif ratio < 0.5 and ratio > 0:
                        reasoning_traces.append(f"cross_signal: ARR ({arr_run_rate}) is {ratio:.1f}x of Revenue ({rev_val}), revenue may include non-recurring components")
                    else:
                        reasoning_traces.append(f"cross_signal: ARR ({arr_run_rate}) vs Revenue ({rev_val}) ratio={ratio:.2f}, consistent")

            # Orders vs Revenue (unit count vs currency)
            orders_val = tr.get("orders", "")
            if orders_val and rev_val:
                orders_num = parse_indian_number(orders_val)
                if orders_num and rev_num:
                    avg_order = rev_num / orders_num
                    reasoning_traces.append(f"cross_signal: Revenue ({rev_val}) / Orders ({orders_val}) ≈ ₹{avg_order:.0f}/order")

        except Exception:
            pass

        # Add reasoning traces to the return payload
        structured_data["_reasoning_traces"] = reasoning_traces

        # Build chart_data from canonical registry (P0: structured chart data)
        import traceback as _tb
        chart_data = {}
        try:
            chart_data = export_chart_data_from_canonical(_canon)
        except Exception as _ce:
            print(f"[CHART] chart_data build failed: {_ce}")
            _tb.print_exc()

        # ── Phase A: Central Metric Serializer sanitizes all output ─────────
        from app.rag.metric_serializer import (
            sanitize_financial_highlights, sanitize_chart_data,
            sanitize_canonical_metrics, sanitize_data_warnings,
        )
        _safe_financial = sanitize_financial_highlights(financial_highlights)
        _safe_chart = sanitize_chart_data(chart_data)
        _safe_canonical = sanitize_canonical_metrics(_canon)
        _safe_warnings = sanitize_data_warnings(warnings + validation_flags + validation_flags_extended)

        return {
            "summary": summary,
            "email": email,
            "key_signal": key_signal,
            "rag_status": "success",
            "extracted_metrics": extracted_data,
            "description": short_description,
            "financial_highlights": _safe_financial,
            "confidence_by_section": confidence_by_section,
            "field_confidence": field_confidence,
            "data_warnings": _safe_warnings,
            "canonical_metrics": _safe_canonical,
            "chart_data": _safe_chart,
            "reasoning_traces": reasoning_traces,
        }

    except Exception as e:
        import traceback
        error_detail = str(e)
        print(f"[CRITICAL GENERATOR ERROR] {error_detail}")
        traceback.print_exc()
        return {
            "summary": f"### Semantic Analysis Failed\nCould not parse structured data correctly.\n\n**Error:** {error_detail[:500]}",
            "email": f"Hi [Name],\n\nThanks for your interest in {company_name}. Happy to schedule a call to discuss further.\n\nBest,\n[Your Name]",
            "key_signal": "N/A",
            "rag_status": "error",
            "extracted_metrics": {},
            "chart_data": {},
            "_visual_confidence": 0.0,
            "_chart_confidence": 0.0,
        }


def generate_all_with_citations(financial_chunks: list, sources: list, intent: dict = None, company_name: str = "Unknown Company", domain: str = "General"):
    """
    Generate response with citation tracking
    """
    chunks_by_section = {"financials": financial_chunks or []}
    result = generate_all(chunks_by_section, intent, company_name, domain)
    
    citations = []
    for idx, src in enumerate(sources):
        citations.append({
            "id": idx + 1,
            "text": src.get("text", "")[:150] + "..." if len(src.get("text", "")) > 150 else src.get("text", ""),
            "full_text": src.get("text", ""),
            "score": src.get("score", 0),
            "doc_id": src.get("doc_id", "unknown"),
            "company": src.get("company", "Unknown"),
            "section": src.get("section", "unknown")
        })
    
    result["citations"] = citations
    return result


class TemporalNarrativeGenerator:
    """Generate investor-grade narratives with temporal context"""
    
    UNIT_MULTIPLIERS = {
        "cr": 1e7, "crore": 1e7, "l": 1e5, "lakh": 1e5, 
        "m": 1e6, "mn": 1e6, "k": 1e3
    }
    
    @staticmethod
    def parse_value(value_str: str) -> float:
        if not value_str:
            return 0.0
        value_str = str(value_str).lower().replace(",", "").replace("₹", "").replace("$", "")
        for unit, mult in TemporalNarrativeGenerator.UNIT_MULTIPLIERS.items():
            if unit in value_str:
                num_match = re.search(r"[\d.]+", value_str)
                if num_match:
                    return float(num_match.group()) * mult
        num_match = re.search(r"[\d.]+", value_str)
        return float(num_match.group()) if num_match else 0.0
    
    @staticmethod
    def format_value(value: float, original: str) -> str:
        if "₹" in str(original).lower() or "rs" in original.lower():
            if value >= 1e7:
                return f"₹{value / 1e7:.2f} Cr"
            elif value >= 1e5:
                return f"₹{value / 1e5:.2f} Lakhs"
        elif "$" in original:
            if value >= 1e6:
                return f"${value / 1e6:.2f} Mn"
        return f"₹{value:.2f}" if value < 1e5 else f"₹{value / 1e7:.2f} Cr"
    
    @staticmethod
    def extract_temporal_context(text: str) -> dict:
        patterns = {
            "fy": r"(?:FY|F\.Y\.?|Fiscal\s*Year)[\s\-]*(\d{4})",
            "quarter": r"(Q[1-4])[\s\-]*(?:FY)?(\d{4})?",
            "yoy": r"(?:yoy|y-o-y)[:\s]*(\d+(?:\.\d+)?)\s*%",
            "comparison": r"(?:up|down)\s*from\s*(FY\d{4})"
        }
        result = {"fiscal_year": 0, "quarter": "", "yoy_growth": 0.0, "comparison_period": ""}
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if key == "fy":
                    result["fiscal_year"] = int(match.group(1))
                elif key == "quarter":
                    result["quarter"] = match.group(1)
                elif key == "yoy":
                    result["yoy_growth"] = float(match.group(1))
                elif key == "comparison":
                    result["comparison_period"] = match.group(1)
        return result
    
    @classmethod
    def generate_revenue_narrative(cls, revenue_data: dict, comparison_data: dict = None) -> str:
        value = revenue_data.get("value", "")
        if not value:
            return ""
        
        temporal = cls.extract_temporal_context(revenue_data.get("period", ""))
        parsed_value = cls.parse_value(value)
        
        narrative = f"The company achieved {cls.format_value(parsed_value, value)}"
        
        if temporal.get("fiscal_year"):
            narrative += f" in FY{temporal['fiscal_year']}"
        elif temporal.get("quarter"):
            period_str = f"{temporal['quarter']}"
            if temporal.get("fiscal_year"):
                period_str += f" FY{temporal['fiscal_year']}"
            narrative += f" in {period_str}"
        
        if comparison_data and comparison_data.get("value"):
            comp_parsed = cls.parse_value(comparison_data.get("value", ""))
            if comp_parsed > 0 and parsed_value > comp_parsed:
                growth = ((parsed_value - comp_parsed) / comp_parsed) * 100
                narrative += f", up from {cls.format_value(comp_parsed, comparison_data.get('value', ''))}"
                if comparison_data.get("period"):
                    narrative += f" in {comparison_data['period']}"
                narrative += f", representing approximately {growth:.0f}% year-on-year growth."
            else:
                narrative += "."
        elif temporal.get("yoy_growth"):
            narrative += f", representing approximately {temporal['yoy_growth']:.0f}% year-on-year growth."
        else:
            narrative += "."
        
        return narrative
    
    @classmethod
    def generate_growth_narrative(cls, growth_data: dict) -> str:
        growth_value = growth_data.get("value", "")
        if not growth_value:
            return ""
        
        temporal = cls.extract_temporal_context(growth_data.get("period", ""))
        
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", growth_value)
        if not match:
            return f"The company demonstrated strong growth: {growth_value}."
        
        growth_pct = float(match.group(1))
        narrative = f"The company achieved {growth_pct:.0f}% growth"
        
        if temporal.get("fiscal_year"):
            narrative += f" in FY{temporal['fiscal_year']}"
        elif temporal.get("yoy_growth"):
            narrative += " year-on-year"
        
        if growth_pct > 50:
            narrative += ", indicating exceptional momentum."
        elif growth_pct > 25:
            narrative += ", demonstrating strong growth trajectory."
        else:
            narrative += ", showing steady progress."
        
        return narrative
    
    @classmethod
    def generate_customer_narrative(cls, customer_data: dict) -> str:
        value = customer_data.get("value", "")
        if not value:
            return ""
        
        value_clean = re.sub(r"[^\d,]", "", str(value))
        if not value_clean:
            return ""
        
        try:
            count = int(value_clean.replace(",", ""))
        except:
            return f"Customer base: {value}."
        
        temporal = cls.extract_temporal_context(customer_data.get("period", ""))
        
        if count >= 1000000:
            narrative = f"The company serves over {count / 1e6:.1f}M customers"
        elif count >= 1000:
            narrative = f"The company serves {count:,} customers"
        else:
            narrative = f"The company has {count} customers"
        
        if temporal.get("fiscal_year"):
            narrative += f" as of FY{temporal['fiscal_year']}"
        
        if count > 100000:
            narrative += ", representing significant market penetration."
        elif count > 10000:
            narrative += ", showing strong customer adoption."
        else:
            narrative += ", with early customer traction."
        
        return narrative
    



def build_metric_timeline(facts: List[Dict], metric_name: str) -> Dict:
    """Build structured timeline data for frontend chart rendering"""
    metric_facts = [f for f in facts if f.name == metric_name or metric_name in f.get("name", "")]
    
    timeline_data = []
    for fact in metric_facts:
        temporal = TemporalNarrativeGenerator.extract_temporal_context(fact.get("metadata", {}).get("period", ""))
        value = TemporalNarrativeGenerator.parse_value(fact.get("value", ""))
        
        timeline_data.append({
            "year": temporal.get("fiscal_year", 0),
            "period": temporal.get("quarter", temporal.get("fiscal_period", "")),
            "value": value,
            "formatted": fact.get("value", ""),
            "page": fact.get("page", 0),
            "confidence": fact.get("confidence", 0)
        })
    
    timeline_data.sort(key=lambda x: x["year"] if x["year"] > 0 else 0, reverse=True)
    
    if len(timeline_data) >= 2:
        current = timeline_data[0]["value"]
        previous = timeline_data[1]["value"]
        yoy_growth = ((current - previous) / previous * 100) if previous > 0 else 0
        
        timeline_data[0]["yoy_growth"] = round(yoy_growth, 1)
    
    if len(timeline_data) >= 3:
        values = [d["value"] for d in timeline_data if d["value"] > 0]
        if len(values) >= 3:
            cagr = ((values[0] / values[-1]) ** (1 / (len(values) - 1)) - 1) * 100
            timeline_data[0]["cagr"] = round(cagr, 1)
    
    return {
        "type": f"{metric_name}_trend",
        "data": timeline_data,
        "calculated": {
            "yoy_growth": [d.get("yoy_growth", 0) for d in timeline_data],
            "cagr": timeline_data[0].get("cagr", 0)
        }
    }