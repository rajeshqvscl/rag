"""
Unit tests to verify safe metric unpacking in deterministic renderers,
preventing raw Python dictionary string/JSON leakage in investment summaries.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.renderer.utils import render_full_report


def test_renderer_unpacking_unpacks_dictionaries():
    """Verify that nested metric dictionaries are cleanly formatted into flat values in narratives."""
    structured_data = {
        "company_brief": {
            "name": "LabBuddy",
            "sector": "Healthcare"
        },
        "industry_overview": {
            "tam": {
                "value": "₹9,100 Crore annually (FY25-26)",
                "source_slide": 4,
                "evidence_text": "Total Diagnostics Market – Delhi NCR ₹9,100 Crore",
                "metric_type": "tam",
                "confidence_tier": "explicit",
                "confidence": 1.0
            },
            "sam": {
                "value": "₹3,185 Crore (FY25-26)",
                "source_slide": 4,
                "metric_type": "sam"
            },
            "som": {
                "value": "₹1,000 Crore",
                "metric_type": "som"
            },
            "market_context": "Delhi NCR diagnostics"
        },
        "traction": {
            "revenue": {
                "value": "₹89L+",
                "source_slide": 7,
                "evidence_text": "₹89L+ Total Revenue Generated",
                "metric_type": "revenue",
                "confidence_tier": "explicit",
                "confidence": 1.0
            }
        }
    }

    report = render_full_report(structured_data, field_confidence={})

    # Assert that no raw dictionary string format leaked into the narrative
    assert "{'value':" not in report, "Raw dictionary string leaked in the narrative summary"
    assert "dict" not in report.lower(), "Raw dict type leakage in the narrative summary"

    # Assert that the correct values were cleanly extracted and formatted
    assert "TAM of ₹9,100 Crore annually (FY25-26)" in report
    assert "SAM of ₹3,185 Crore (FY25-26)" in report
    assert "SOM of ₹1,000 Crore" in report
    assert "revenue of ₹89L+" in report


if __name__ == "__main__":
    test_renderer_unpacking_unpacks_dictionaries()
    print("OK: test_renderer_unpacking_unpacks_dictionaries")
