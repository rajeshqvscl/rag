"""
Autonomous Report Generation - AI-generated investment reports
"""

from typing import List, Dict, Any, Optional
from .retriever import retrieve_with_sources, get_all_namespaces
from .generator import generate_all, format_summary
from app.core.llm_client import get_safe_client
from app.db.models import PitchDeck
from datetime import datetime


REPORT_TEMPLATES = {
    "executive": {
        "sections": ["Executive Summary", "Investment Highlights", "Key Risks", "Recommendation"],
        "length": "concise"
    },
    "detailed": {
        "sections": ["Executive Summary", "Company Overview", "Financial Analysis", "Market Analysis", 
                    "Technology Assessment", "Team Analysis", "Competitive Landscape", 
                    "Investment Terms", "Risk Factors", "Recommendation"],
        "length": "detailed"
    },
    "pitchdeck_summary": {
        "sections": ["Company Snapshot", "Problem & Solution", "Traction", "Market Opportunity", 
                    "Business Model", "Team", "Ask"],
        "length": "medium"
    }
}


def generate_report(doc_ids: List[str] = None, template: str = "detailed", 
                   company_name: str = None, namespace: str = None) -> Dict[str, Any]:
    """
    Generate an investment report
    
    Args:
        doc_ids: List of document IDs to include in report
        template: Report template (executive, detailed, pitchdeck_summary)
        company_name: Company name override
        namespace: Namespace for retrieval isolation
    
    Returns:
        {report: markdown, sections: [...], metadata: {...}}
    """
    client = get_safe_client()
    
    if template not in REPORT_TEMPLATES:
        template = "detailed"
    
    template_config = REPORT_TEMPLATES[template]
    
    print(f"\n[REPORT] Starting report generation")
    print(f"[REPORT] doc_ids: {doc_ids}")
    print(f"[REPORT] company_name: {company_name}")
    print(f"[REPORT] template: {template}")
    
    all_chunks = []
    all_sources = []
    
    if doc_ids:
        print(f"[REPORT] Using doc_ids filter for retrieval")
        
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            companies_to_search = []
            for doc_id in doc_ids:
                if doc_id.startswith("deck_"):
                    deck_num = doc_id.replace("deck_", "")
                    deck = db.query(PitchDeck).filter(PitchDeck.id == int(deck_num)).first()
                    if deck and deck.company:
                        companies_to_search.append((deck.company, doc_id))
                        print(f"[REPORT] deck_{deck_num} -> company: {deck.company}")
                elif doc_id.startswith("insight_"):
                    insight_num = doc_id.replace("insight_", "")
                    ins = db.query(PitchDeck).filter(PitchDeck.id == int(insight_num)).first()
                    if ins and ins.company:
                        companies_to_search.append((ins.company, doc_id))
                        print(f"[REPORT] insight_{insight_num} -> company: {ins.company}")
                else:
                    companies_to_search.append((None, doc_id))
            
            all_ns = get_all_namespaces()
            
            for company, doc_id in companies_to_search:
                if company:
                    sanitized_company = company.lower().replace(" ", "_").replace(".", "").replace(",", "").replace("-", "")
                    company_base = sanitized_company.split("_")[0][:8]
                    
                    matching_ns = []
                    for ns in all_ns:
                        ns_lower = ns.lower()
                        
                    if company_base in ns_lower and len(company_base) >= 8:
                        matching_ns.append(ns)
                        continue
                    
                    for part in sanitized_company.split("_"):
                        if len(part) >= 8 and (part in ns_lower or ns_lower.startswith(part[:8])):
                                matching_ns.append(ns)
                                break
                    
                    if not matching_ns and "labbuddy" in sanitized_company:
                        matching_ns = [ns for ns in all_ns if "labbuddy" in ns.lower()]
                    if not matching_ns and "qvscl" in sanitized_company:
                        matching_ns = [ns for ns in all_ns if "qvscl" in ns.lower()]
                    if not matching_ns and "gigin" in sanitized_company:
                        matching_ns = [ns for ns in all_ns if "gigin" in ns.lower()]
                    if not matching_ns and ("syncthread" in sanitized_company or "stc" in sanitized_company):
                        matching_ns = [ns for ns in all_ns if "stc_pitch" in ns.lower() or "syncthread" in ns.lower()]
                    
                    matching_ns = list(set(matching_ns))[:2]
                    
                    print(f"[REPORT] Company '{company}' -> '{sanitized_company}' matching namespaces: {matching_ns}")
                    
                    for ns in matching_ns:
                        result = retrieve_with_sources(
                            f"{company} investment analysis business model financials",
                            namespace=ns,
                            top_k=10
                        )
                        print(f"[REPORT] namespace '{ns}' returned {result['count']} chunks")
                        all_chunks.extend(result["chunks"])
                        all_sources.extend(result["sources"])
                else:
                    ns = namespace or (company_name.lower().replace(" ", "_") if company_name else None)
                    result = retrieve_with_sources(
                        f"investment analysis",
                        namespace=ns,
                        doc_id=doc_id,
                        top_k=10
                    )
                    all_chunks.extend(result["chunks"])
                    all_sources.extend(result["sources"])
        finally:
            db.close()
        
        print(f"[REPORT] Total chunks after doc_ids filter: {len(all_chunks)}")
    
    if not all_chunks and company_name:
        print(f"[REPORT] Falling back to company_name: {company_name}")
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            deck = db.query(PitchDeck).filter(
                PitchDeck.company.ilike(f"%{company_name}%")
            ).first()
            
            if deck:
                all_ns = get_all_namespaces()
                sanitized_variants = [
                    company_name.lower().replace(" ", "_"),
                    company_name.lower().replace(" ", ""),
                    company_name.lower().replace(" ", "-"),
                    company_name.lower()[:10],
                ]
                
                matching_ns = []
                for ns in all_ns:
                    for variant in sanitized_variants:
                        if variant in ns.lower() or ns.lower().startswith(variant[:8]):
                            matching_ns.append(ns)
                            break
                
                matching_ns = list(set(matching_ns))
                
                if matching_ns:
                    for ns in matching_ns:
                        result = retrieve_with_sources(
                            f"{company_name} investment analysis business model financials",
                            namespace=ns,
                            top_k=10
                        )
                        all_chunks.extend(result["chunks"])
                        all_sources.extend(result["sources"])
                    print(f"[REPORT] Found {len(all_chunks)} chunks in namespaces: {matching_ns}")
                else:
                    ns = namespace or (company_name.lower().replace(" ", "_") if company_name else None)
                    result = retrieve_with_sources(
                        f"{company_name} company analysis investment pitch",
                        namespace=ns,
                        top_k=15
                    )
                    all_chunks = result["chunks"]
                    all_sources = result["sources"]
            else:
                ns = namespace or (company_name.lower().replace(" ", "_") if company_name else None)
                result = retrieve_with_sources(
                    f"{company_name} investment analysis pitch deck",
                    namespace=ns,
                    top_k=15
                )
                all_chunks = result["chunks"]
                all_sources = result["sources"]
        finally:
            db.close()
    
    if not all_chunks:
        ns = namespace or (company_name.lower().replace(" ", "_") if company_name else None)
        result = retrieve_with_sources("investment analysis pitch deck summary", namespace=ns, top_k=10)
        all_chunks = result["chunks"]
        all_sources = result["sources"]
    
    print(f"[REPORT] Final chunk count: {len(all_chunks)}")
    
    context = "\n\n".join(all_chunks[:10]) if all_chunks else "No document content found."
    sources = all_sources
    
    # Build the report
    report_sections = []
    if company_name:
        full_report = f"# Investment Report: {company_name}\n"
    else:
        full_report = f"# Investment Report\n"
    full_report += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    
    for section_name in template_config["sections"]:
        section_content = generate_section(section_name, context, client)
        report_sections.append({
            "name": section_name,
            "content": section_content
        })
        
        full_report += f"## {section_name}\n\n{section_content}\n\n"
    
    # Extract metadata
    metadata = {
        "template": template,
        "sections_count": len(report_sections),
        "documents_used": len(doc_ids) if doc_ids else 0,
        "sources_count": len(sources),
        "generated_at": datetime.now().isoformat()
    }
    
    if company_name:
        metadata["company"] = company_name
    
    return {
        "report": full_report,
        "sections": report_sections,
        "metadata": metadata,
        "sources": sources[:5]  # Top 5 sources
    }


def generate_section(section_name: str, context: str, client) -> str:
    """Generate content for a specific report section"""
    
    section_prompts = {
        "Executive Summary": f"""Based on the following document context, provide a 3-4 sentence executive summary:

{context}

Summary:""",
        
        "Investment Highlights": f"""From the document context, extract the top 3-5 investment highlights with specific metrics:

{context}

Highlights:""",
        
        "Key Risks": f"""Identify the top 3-5 key risks mentioned in the documents:

{context}

Risks:""",
        
        "Recommendation": f"""Based on all the information provided, give a clear investment recommendation with reasoning:

{context}

Recommendation:""",
        
        "Financial Analysis": f"""Extract and analyze the financial information from the documents:

{context}

Financial Analysis:""",
        
        "Market Analysis": f"""Analyze the market opportunity and size from the documents:

{context}

Market Analysis:""",
        
        "Technology Assessment": f"""Assess the technology and product from the documents:

{context}

Technology:""",
        
        "Team Analysis": f"""Analyze the team and leadership from the documents:

{context}

Team:"""
    }
    
    prompt = section_prompts.get(section_name, f"Summarize the following for the {section_name} section:\n\n{context}")
    
    try:
        response = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=500
        )
        return response
    except Exception as e:
        return f"Unable to generate section: {str(e)}"


def generate_quick_summary(doc_id: str = None, namespace: str = None) -> Dict[str, Any]:
    """Generate a quick summary of available data"""
    client = get_safe_client()
    
    if doc_id:
        result = retrieve_with_sources("summary overview", namespace=namespace, doc_id=doc_id, top_k=3)
    else:
        result = retrieve_with_sources("summary overview", namespace=namespace, top_k=5)
    
    context = "\n\n".join(result["chunks"])
    
    prompt = f"""Provide a concise summary of the following documents in 3-5 bullet points:

{context}

Summary:"""
    
    try:
        summary = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300
        )
        
        return {
            "summary": summary,
            "sources": result["sources"],
            "documents": [doc_id] if doc_id else []
        }
    except Exception as e:
        return {
            "summary": f"Error generating summary: {str(e)}",
            "sources": [],
            "documents": []
        }


def export_report(report_data: Dict, format: str = "markdown") -> str:
    """Export report in different formats"""
    
    if format == "markdown":
        return report_data["report"]
    elif format == "text":
        # Strip markdown formatting
        import re
        text = report_data["report"]
        text = re.sub(r'#+ ', '', text)  # Remove headers
        return text
    else:
        return report_data["report"]
