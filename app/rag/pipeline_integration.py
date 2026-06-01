"""
Integration Example - Using the Document Intelligence Pipeline
Shows how to use the new pipeline for startup pitch deck analysis
"""
from app.rag.pipeline import (
    DocumentIntelligencePipeline,
    PipelineConfig,
    HybridRetriever,
    ValidationEngine
)

def analyze_pitch_deck(pdf_bytes: bytes, company_name: str = "Startup") -> dict:
    """
    Full analysis pipeline for pitch deck
    
    Returns structured analysis with facts, scores, and insights
    """
    config = PipelineConfig(
        extract_tables=True,
        analyze_charts=False,  # Enable if you have vision API
        detect_sections=True,
        extract_facts=True,
        validate_facts=True,
        hybrid_retrieval=True,
        min_confidence=0.6
    )
    
    pipeline = DocumentIntelligencePipeline(config)
    
    print(f"\n[ANALYSIS] Processing {company_name} pitch deck...")
    
    results = pipeline.process(pdf_bytes)
    
    facts = results["facts"]
    
    analysis = {
        "company": company_name,
        "sections_detected": list(results["sections"].keys()),
        "table_count": len(results["tables"]),
        "fact_count": len(facts.get("financials", {})) + len(facts.get("traction", {})),
        "financials": facts.get("financials", {}),
        "traction": facts.get("traction", {}),
        "team": facts.get("team", {}),
        "market": facts.get("market", {}),
        "raw_text_length": len(results["full_text"])
    }
    
    print(f"[ANALYSIS] Found {analysis['fact_count']} structured facts")
    print(f"[ANALYSIS] Sections: {analysis['sections_detected']}")
    
    return analysis


def query_facts(pipeline: DocumentIntelligencePipeline, query: str, section: str = None):
    """
    Query the pipeline for specific information
    
    Args:
        pipeline: DocumentIntelligencePipeline instance
        query: Natural language query
        section: Optional section filter (financials, team, etc.)
    
    Returns:
        Relevant chunks with scores
    """
    results = pipeline.query(query, section=section)
    
    print(f"\n[QUERY] '{query}' (section={section})")
    print(f"[QUERY] Found {results['count']} results")
    
    for i, result in enumerate(results.get("results", [])[:3]):
        print(f"\n  Result {i+1} (score: {result['score']})")
        print(f"  Section: {result['metadata'].get('section', 'unknown')}")
        print(f"  Page: {result['metadata'].get('page', '?')}")
        print(f"  Content: {result['text'][:150]}...")
    
    return results


def validate_revenue_facts(facts: dict, funding_stage: str = "seed") -> dict:
    """
    Validate extracted facts against business rules
    
    Args:
        facts: Structured facts from pipeline
        funding_stage: Pre-seed, seed, series-a, etc.
    
    Returns:
        Validated facts with confidence adjustments
    """
    engine = ValidationEngine()
    
    validated = {}
    
    for category, data in facts.items():
        if isinstance(data, dict):
            validated[category] = {}
            for key, value_data in data.items():
                if isinstance(value_data, dict):
                    result = engine.validate_fact(
                        {"key": key, "value": value_data.get("value"), "category": category},
                        {"funding_stage": funding_stage}
                    )
                    value_data["validation"] = {
                        "valid": result.valid,
                        "reason": result.reason,
                        "confidence_adjustment": result.confidence_adjustment
                    }
                    validated[category][key] = value_data
    
    return validated


def get_structured_output(pipeline: DocumentIntelligencePipeline) -> dict:
    """
    Get the final structured JSON for downstream use
    (scoring, email generation, dashboard)
    """
    return {
        "structured_analysis": pipeline.get_structured_analysis(),
        "facts_by_category": {
            "financials": [f.to_dict() for f in pipeline.fact_registry.get_by_category("financials")],
            "traction": [f.to_dict() for f in pipeline.fact_registry.get_by_category("traction")],
            "team": [f.to_dict() for f in pipeline.fact_registry.get_by_category("team")],
            "market": [f.to_dict() for f in pipeline.fact_registry.get_by_category("market")]
        }
    }


if __name__ == "__main__":
    print("Document Intelligence Pipeline - Integration Example")
    print("="*60)
    print("\nUsage:")
    print("""
    from app.rag.pipeline_integration import analyze_pitch_deck, query_facts, validate_revenue_facts
    
    # Full analysis
    results = analyze_pitch_deck(pdf_bytes, "Company Name")
    
    # Query for specific info
    pipeline = DocumentIntelligencePipeline(config)
    pipeline.process(pdf_bytes)
    revenue_info = query_facts(pipeline, "revenue growth", section="financials")
    
    # Validate facts
    validated = validate_revenue_facts(results["facts"])
    
    # Get structured output for scoring/email
    output = get_structured_output(pipeline)
    """)