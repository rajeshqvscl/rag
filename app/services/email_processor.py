"""
Pipeline entry point — delegates to PipelineOrchestrator for stage-isolated execution.

Maintains backward compatibility: process_email() signature is unchanged.
The orchestrator provides:
  - Stage isolation (failures don't cascade)
  - Deck complexity scoring (resource budgeting per document)
  - Degraded-state tracking (infrastructure confidence)
  - Per-document caching (expensive ops persist between runs)
"""

import hashlib
import re
from app.utils.text_utils import safe_lower


def detect_domain(text):
    text = safe_lower(text)
    if any(k in text for k in ["lab", "diagnostic", "health", "clinical", "patient", "medical"]):
        return "health"
    if any(k in text for k in ["agri", "farm", "rural", "crop"]):
        return "agri"
    if any(k in text for k in ["rf", "antenna", "military", "tactical", "defense"]):
        return "defense"
    if any(k in text for k in ["software", "subscription", "cloud", "platform", "saas"]):
        return "saas"
    return "General"


def process_email(file, file_name="unknown"):
    """
    Unified Pipeline — delegates to PipelineOrchestrator for stage-isolated execution.

    Backward compatible: same signature, same return format (with additional
    _pipeline_stages, _infra_confidence, _degraded_stages, _complexity keys).
    """
    print("")
    print("=" * 50)
    safe_file_name = file_name.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    print("PIPELINE START: " + safe_file_name)
    print("=" * 50)

    from app.rag.pipeline_orchestrator import run_pipeline

    if hasattr(file, "read"):
        file_content = file.read()
    elif isinstance(file, bytes):
        file_content = file
    else:
        file_content = file

    result = run_pipeline(file_content, safe_file_name)
    return result