"""
Enhanced Multi-Document Comparison - Compare pitch decks with type-specific dimensions
"""

from typing import List, Dict, Any, Optional
from .retriever import retrieve_with_sources, get_all_namespaces
from .generator import limit_context
from .analysis_config import AnalysisConfig, DeckType
from app.core.llm_client import get_safe_client
from app.db.session import SessionLocal
from app.db.models import PitchDeck


DEFAULT_DIMENSIONS = [
    "revenue",
    "growth rate", 
    "traction",
    "technology",
    "team",
    "market opportunity",
    "funding stage",
    "business model",
    "competitive advantage"
]


def get_available_documents() -> List[Dict]:
    """Get all documents from database for selection"""
    db = SessionLocal()
    try:
        documents = []
        
        decks = db.query(PitchDeck).all()
        for d in decks:
            documents.append({
                "id": f"deck_{d.id}",
                "type": "pitch_deck",
                "company": d.company,
                "score": d.score,
                "verdict": d.verdict,
                "deck_type": getattr(d, 'deck_type', None),
                "timestamp": d.timestamp.isoformat() if d.timestamp else None
            })
        
        insights = db.query(PitchDeck).filter(
            PitchDeck.status == "completed"
        ).all()
        
        for ins in insights:
            if ins.company:
                documents.append({
                    "id": f"insight_{ins.id}",
                    "type": "intelligence",
                    "company": ins.company,
                    "score": ins.insights.get("score", 0) if ins.insights else 0,
                    "verdict": ins.insights.get("verdict", "N/A") if ins.insights else "N/A",
                    "deck_type": ins.insights.get("deck_type", None) if ins.insights else None,
                    "timestamp": ins.timestamp.isoformat() if ins.timestamp else None
                })
        
        return documents
    finally:
        db.close()


def compare_documents(
    doc_ids: List[str], 
    dimensions: List[str] = None, 
    companies: List[str] = None,
    comparison_type: str = "detailed",
    deck_type: str = "seed",
    namespaces: List[str] = None
) -> Dict[str, Any]:
    """
    Compare multiple documents across specified dimensions.
    
    Args:
        doc_ids: List of document IDs to compare
        dimensions: List of comparison dimensions (overrides type-based)
        companies: Optional list of company names
        comparison_type: "quick" (4 dims), "detailed" (6 dims), "comprehensive" (all dims)
        deck_type: Type of pitch deck - "seed", "series_a", "series_b", "growth"
        namespaces: Optional list of namespaces (one per doc_id)
    
    Returns:
        {
            "comparison": {...},
            "table": [...],
            "insights": [...],
            "documents": [...],
            "dimensions": [...],
            "deck_type_config": {...}
        }
    """
    analysis_config = AnalysisConfig.get_config_by_name(deck_type)
    
    if dimensions is None:
        dimensions = AnalysisConfig.get_dimensions(DeckType(deck_type), comparison_type)
    
    if companies is None:
        companies = get_company_names(doc_ids)
        if not companies:
            companies = [f"Company {i+1}" for i in range(len(doc_ids))]
    
    dimension_data = {}
    
    for dim in dimensions:
        dimension_data[dim] = []
        
        for idx, doc_id in enumerate(doc_ids):
            actual_doc_id = doc_id.replace("deck_", "").replace("insight_", "")
            company_namespace = namespaces[idx] if namespaces and idx < len(namespaces) else (companies[idx].lower().replace(" ", "_") if companies[idx] else None)
            
            try:
                results = retrieve_with_sources(
                    f"{dim} {companies[idx]}",
                    namespace=company_namespace,
                    doc_id=actual_doc_id,
                    top_k=3
                )
                
                dimension_data[dim].append({
                    "company": companies[idx],
                    "doc_id": doc_id,
                    "chunks": results["chunks"],
                    "sources": results["sources"],
                    "has_data": len(results["chunks"]) > 0
                })
            except Exception as e:
                dimension_data[dim].append({
                    "company": companies[idx],
                    "doc_id": doc_id,
                    "chunks": [],
                    "sources": [],
                    "has_data": False,
                    "error": str(e)
                })
    
    comparison_prompt = build_comparison_prompt(
        dimension_data, dimensions, companies, analysis_config
    )
    
    client = get_safe_client()
    try:
        comparison_response = client.chat_completion(
            messages=[{"role": "user", "content": comparison_prompt}],
            temperature=0.1,
            max_tokens=2500
        )
    except Exception as e:
        comparison_response = f"Comparison failed: {str(e)}"
    
    structured = parse_comparison_response(comparison_response, dimensions, companies)
    
    winner = calculate_winner(structured.get("table", []))
    
    return {
        "comparison": structured["comparison"],
        "table": structured["table"],
        "insights": structured["insights"],
        "documents": [
            {"doc_id": doc_ids[i], "company": companies[i]} 
            for i in range(len(doc_ids))
        ],
        "dimensions": dimensions,
        "comparison_type": comparison_type,
        "overall_winner": winner,
        "deck_type_config": {
            "name": analysis_config.name,
            "tagline": analysis_config.tagline,
            "focus_areas": analysis_config.focus_areas,
            "critical_metrics": analysis_config.critical_metrics,
            "red_flags": analysis_config.red_flags,
            "weighted_dimensions": [
                {"name": d.name, "weight": d.weight} 
                for d in analysis_config.dimensions
            ]
        }
    }


def get_company_names(doc_ids: List[str]) -> List[str]:
    """Get company names from document IDs"""
    db = SessionLocal()
    try:
        companies = []
        for doc_id in doc_ids:
            if doc_id.startswith("deck_"):
                deck_id = int(doc_id.replace("deck_", ""))
                deck = db.query(PitchDeck).filter(PitchDeck.id == deck_id).first()
                companies.append(deck.company if deck else f"Document {deck_id}")
            elif doc_id.startswith("insight_"):
                insight_id = int(doc_id.replace("insight_", ""))
                insight = db.query(PitchDeck).filter(PitchDeck.id == insight_id).first()
                companies.append(insight.company if insight else f"Insight {insight_id}")
            else:
                companies.append(doc_id)
        return companies
    finally:
        db.close()


def build_comparison_prompt(
    dimension_data: Dict, 
    dimensions: List[str], 
    companies: List[str],
    analysis_config
) -> str:
    """Build prompt for LLM to compare documents with type-specific context"""
    
    type_context = AnalysisConfig.build_comparison_prompt_context(
        DeckType(analysis_config.name.lower().replace(" ", "_"))
    )
    
    prompt = f"""You are a senior investment analyst specializing in {analysis_config.name} analysis.

{type_context}

## COMPANIES BEING COMPARED:
{', '.join(companies)}

"""
    
    for dim in dimensions:
        dim_config = next(
            (d for d in analysis_config.dimensions if d.name == dim), 
            None
        )
        weight_note = f"[Weight: {dim_config.weight}x]" if dim_config else ""
        
        prompt += f"\n## {dim.upper()} {weight_note}\n"
        for data in dimension_data.get(dim, []):
            if data.get("has_data"):
                context = limit_context(data["chunks"], max_chars=300)
                prompt += f"\n{data['company']}: {context}\n"
            else:
                prompt += f"\n{data['company']}: No data available\n"
    
    prompt += """
Based on the above information, provide:
1. A structured comparison for each dimension
2. A summary table with winner for each dimension (consider weighted dimensions)
3. Key insights and recommendations
4. Red flag alerts if any are detected

Format your response as JSON with this structure:
{
    "comparison": {
        "dimension_name": {"company_name": "analysis", ...}
    },
    "table": [
        {"dimension": "...", "winner": "...", "details": "..."}
    ],
    "insights": ["insight1", "insight2", ...],
    "red_flags": ["flag1", "flag2", ...] (if any detected)
}
"""
    return prompt


def parse_comparison_response(response: str, dimensions: List[str], companies: List[str]) -> Dict[str, Any]:
    """Parse LLM response into structured format"""
    import json
    import re
    
    json_match = re.search(r'\{[\s\S]*\}', response)
    
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    
    return {
        "comparison": {dim: {co: "Data available" for co in companies} for dim in dimensions},
        "table": [{"dimension": dim, "winner": "N/A", "details": "See analysis"} for dim in dimensions],
        "insights": ["Comparison generated. Review details above."]
    }


def calculate_winner(table: List[Dict]) -> str:
    """Calculate overall winner based on dimension wins"""
    if not table:
        return "N/A"
    
    wins = {}
    for row in table:
        winner = row.get("winner", "N/A")
        if winner and winner != "N/A":
            wins[winner] = wins.get(winner, 0) + 1
    
    if not wins:
        return "N/A"
    
    return max(wins, key=wins.get)


def quick_compare(doc_id1: str, doc_id2: str, company1: str = "Company A", company2: str = "Company B", namespaces: List[str] = None) -> Dict[str, Any]:
    """Quick comparison between two documents"""
    return compare_documents(
        doc_ids=[doc_id1, doc_id2],
        dimensions=["traction", "unit_economics", "market_position", "solution"],
        companies=[company1, company2],
        comparison_type="quick",
        deck_type="seed",
        namespaces=namespaces
    )
