import re

def clean_text(text):
    """
    Standardizes text for RAG: removes extra whitespace,
    normalizes symbols, and handles basic encoding issues.
    """
    if not text:
        return ""

    text = text.replace("\n", " ")
    text = text.replace("•", ". ")

    text = re.sub(r'\s+', ' ', text)

    return text.strip()

def ensure_string(x):
    """Safely convert any value to string"""
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (int, float, bool)):
        return str(x)
    if isinstance(x, dict):
        return str(x)
    return ""

def safe_lower(x):
    """Safely convert to lowercase, returns empty string for None"""
    if x is None:
        return ""
    if not isinstance(x, str):
        try:
            x = str(x)
        except Exception:
            return ""
    return x.lower()

def safe_strip(x):
    """Safely strip whitespace"""
    if x is None:
        return ""
    if not isinstance(x, str):
        try:
            x = str(x)
        except Exception:
            return ""
    return x.strip()

def validate_section(section_name, content):
    """Validate section content"""
    if content is None:
        content = ""
    if not isinstance(content, str):
        content = str(content)

    content_lower = safe_lower(content)

    if section_name == "ACTUALS" and "platform" in content_lower:
        return "No verified financial data available"

    return content

def truncate_text(text, max_length=200):
    """Safely truncate text"""
    if text is None:
        return ""
    text_str = ensure_string(text)
    return text_str[:max_length] if len(text_str) > max_length else text_str

def normalize_whitespace(text):
    """Normalize whitespace in text"""
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def remove_noise(text):
    """Remove common noise patterns from text"""
    if text is None:
        return ""
    text = str(text)
    text = re.sub(r'\b[A-Z\s]{10,}\b', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()