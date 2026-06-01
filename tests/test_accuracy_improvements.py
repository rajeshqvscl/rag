"""
Integration tests for accuracy improvements:
1. CompanyIdentityResolver (fixes Gigin "Unknown company")
2. TAM/SAM/SOM text fallback (fixes AgriVijay wrong values)
3. Ontological reclassifier (fixes STC PO vs Revenue confusion)
4. Canonical registry wiring
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.company_resolver import CompanyIdentityResolver
from app.rag.visual_parser import ConcentricCircleParser
from app.rag.financial_validator import ontological_reclassifier


# ── Company Identity Resolver Tests ─────────────────────────────────────

def test_resolver_passes_through_known_name():
    result = CompanyIdentityResolver.resolve(llm_name="Syncthreads Computing")
    assert result == "Syncthreads Computing"


def test_resolver_deck_title():
    result = CompanyIdentityResolver.resolve(
        llm_name="Unknown Company",
        first_page_text="STC Pitch Deck\nDefence AI Company"
    )
    assert result and result.lower().startswith("stc")


def test_resolver_domain():
    result = CompanyIdentityResolver.resolve(
        llm_name="Unknown",
        first_page_text="gigin.ai is an AI hiring platform"
    )
    assert result and "gigin" in result.lower()


def test_resolver_filename():
    result = CompanyIdentityResolver.resolve(
        llm_name="Unknown Company",
        first_page_text="",
        filename="LabBuddy_v3.pdf"
    )
    assert result and "lab" in result.lower()


def test_resolver_no_info():
    result = CompanyIdentityResolver.resolve(
        llm_name="Unknown",
        first_page_text="no company data here",
        filename=""
    )
    assert result is None


# ── TAM/SAM/SOM Text Fallback Tests ──────────────────────────────────────

def test_tam_sam_som_inr_prefix():
    metrics = ConcentricCircleParser._fallback_text_parse(
        "TAM: INR 45,000 Cr SAM: INR 8,000 Cr SOM: INR 250 Cr"
    )
    assert len(metrics) == 3
    tam = [m for m in metrics if m.semantic_field == "tam"]
    sam = [m for m in metrics if m.semantic_field == "sam"]
    som = [m for m in metrics if m.semantic_field == "som"]
    assert tam and "45,000" in tam[0].value
    assert sam and "8,000" in sam[0].value
    assert som and "250" in som[0].value


def test_tam_sam_som_no_prefix():
    metrics = ConcentricCircleParser._fallback_text_parse(
        "TAM: 45,000 Cr SAM: 8,000 Cr SOM: 250 Cr"
    )
    assert len(metrics) == 3


def test_tam_full_name():
    metrics = ConcentricCircleParser._fallback_text_parse(
        "Total Addressable Market is 150 Cr"
    )
    assert len(metrics) == 1
    assert metrics[0].semantic_field == "tam"


def test_sam_full_name():
    metrics = ConcentricCircleParser._fallback_text_parse(
        "Serviceable Addressable Market is 50 Cr"
    )
    assert len(metrics) == 1
    assert metrics[0].semantic_field == "sam"


def test_som_full_name():
    metrics = ConcentricCircleParser._fallback_text_parse(
        "Serviceable Obtainable Market is 10 Cr"
    )
    assert len(metrics) == 1
    assert metrics[0].semantic_field == "som"


def test_tam_sam_som_no_data():
    metrics = ConcentricCircleParser._fallback_text_parse(
        "No financial data here"
    )
    assert len(metrics) == 0


def test_tam_sam_som_pipe_separated():
    metrics = ConcentricCircleParser._fallback_text_parse(
        "TAM INR 45,000 Cr | SAM INR 8,000 Cr | SOM INR 250 Cr"
    )
    assert len(metrics) == 3


# ── Ontological Reclassifier Tests ──────────────────────────────────────

def test_po_reclassified_from_revenue():
    """STC case: ₹60 Cr expected PO should move from revenue to pipeline."""
    sd = {
        "traction": {"revenue": "60 Cr", "customers": "", "orders": ""},
        "revenue_details": {"current_revenue": "", "projections": []},
        "pipeline": {"pipeline_value": "", "lois": ""},
        "funding": {},
        "industry_overview": {},
        "additional_metrics": [],
        "_validation_warnings": [],
        "_canonical_overrides": {},
    }
    context = "FIRST PO expected worth INR 60+ cr. Revenue from 7 GBMRS units is INR 90 Lakhs."
    sd = ontological_reclassifier(sd, context)
    assert sd["traction"].get("revenue") == "", "Revenue should be cleared for PO-classified value"
    assert sd["pipeline"].get("expected_po", "") != "", "Expected PO should be set"
    assert len(sd.get("_canonical_overrides", {})) > 0, "Overrides should be recorded"


def test_revenue_preserved_when_no_po_context():
    """Revenue should stay when context doesn't indicate PO/grant."""
    sd = {
        "traction": {"revenue": "89 Lakhs", "customers": "", "orders": ""},
        "revenue_details": {"current_revenue": "", "projections": []},
        "pipeline": {},
        "funding": {},
        "industry_overview": {},
        "additional_metrics": [],
        "_validation_warnings": [],
        "_canonical_overrides": {},
    }
    context = "Revenue of INR 89 Lakhs from 300+ partner labs and 7,000+ orders."
    sd = ontological_reclassifier(sd, context)
    assert sd["traction"]["revenue"] == "89 Lakhs", "Revenue should be preserved when context is clean"


def test_grant_added_to_additional():
    """Grant values should move to additional_metrics."""
    sd = {
        "traction": {"revenue": "5.75 Cr", "customers": "", "orders": ""},
        "revenue_details": {"current_revenue": "", "projections": []},
        "pipeline": {},
        "funding": {},
        "industry_overview": {},
        "additional_metrics": [],
        "_validation_warnings": [],
        "_canonical_overrides": {},
    }
    context = "Government grant of INR 5.75 Cr received for R&D."
    sd = ontological_reclassifier(sd, context)
    addl = sd.get("additional_metrics", [])
    grants = [a for a in addl if "grant" in str(a.get("key", "")).lower()]
    assert len(grants) == 1, "Grant should appear in additional_metrics"


# ── Run all ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_resolver_passes_through_known_name()
    print("OK: test_resolver_passes_through_known_name")
    test_resolver_deck_title()
    print("OK: test_resolver_deck_title")
    test_resolver_domain()
    print("OK: test_resolver_domain")
    test_resolver_filename()
    print("OK: test_resolver_filename")
    test_resolver_no_info()
    print("OK: test_resolver_no_info")
    test_tam_sam_som_inr_prefix()
    print("OK: test_tam_sam_som_inr_prefix")
    test_tam_sam_som_no_prefix()
    print("OK: test_tam_sam_som_no_prefix")
    test_tam_full_name()
    print("OK: test_tam_full_name")
    test_sam_full_name()
    print("OK: test_sam_full_name")
    test_som_full_name()
    print("OK: test_som_full_name")
    test_tam_sam_som_no_data()
    print("OK: test_tam_sam_som_no_data")
    test_tam_sam_som_pipe_separated()
    print("OK: test_tam_sam_som_pipe_separated")
    test_po_reclassified_from_revenue()
    print("OK: test_po_reclassified_from_revenue")
    test_revenue_preserved_when_no_po_context()
    print("OK: test_revenue_preserved_when_no_po_context")
    test_grant_added_to_additional()
    print("OK: test_grant_added_to_additional")
    print("\nAll 15 accuracy improvement tests passed")
