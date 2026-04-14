from fastapi import APIRouter, Query
from app.services.rag_service import rag
from app.services.claude_service import client
from app.services.projection_service import projection_service
from app.services.chat_memory_service import chat_memory
import json
import os

router = APIRouter()


@router.get("/query")
def query_rag(
    q: str = Query(..., description="Query text"),
    symbol: str = Query(None, description="Optional stock symbol to filter"),
    session_id: str = Query("default", description="Session ID for chat memory")
):
    results = rag.query(q, k=10, symbol=symbol)
    if not results:
        return {"results": [], "message": f"No data found for {symbol if symbol else 'all symbols'}"}

    # Top results
    filtered = results[:5]

    # Context from top 5
    context = "\n\n".join(r["text"] for r in filtered[:5])

    # Fetch any known projections for this symbol
    projections = projection_service.get_projections(symbol) if symbol else []
    proj_context = ""
    scenarios = {}
    red_flags = []

    if projections:
        proj_context = "Known Financial Projections:\n" + "\n".join([
            f"- {p['metric']} for {p['period']}: {p['value']} (Source: {p.get('source_context', 'N/A')})"
            for p in projections
        ])
        scenarios = projection_service.analyze_scenarios(projections)
        red_flags = projection_service.detect_red_flags(projections)

    # Chat History
    history = chat_memory.get_history(session_id)
    history_context = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history])

    history_block = f"Previous Conversation History:\n{history_context}" if history else ""

    # Claude analysis
    prompt = f"""
    You are an AI financial analyst. Analyze this financial data context for the query: "{q}"

    {history_block}

    Context:
    {context}

    {proj_context}

    Provide a concise financial insight, key metrics, summary. Focus on revenue, growth, valuation if relevant.
    If projections are available, prioritize discussing them as they represent the future outlook.
    """
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        analysis = response.content[0].text
        # Save to memory
        chat_memory.add_message(session_id, "user", q)
        chat_memory.add_message(session_id, "assistant", analysis)
    except Exception as e:
        # Fallback analysis when Claude is unavailable
        if symbol:
            analysis = f"Based on available data for {symbol}, here are key insights:\n\n"
            if projections:
                analysis += "Financial Projections:\n"
                for proj in projections[:3]:
                    analysis += f"- {proj['metric']} ({proj['period']}): {proj['value']}\n"
                analysis += "\n"
            
            if filtered:
                analysis += "Key Findings:\n"
                for i, result in enumerate(filtered[:3]):
                    analysis += f"{i+1}. {result['text'][:150]}...\n"
            else:
                analysis += "No specific data found for this query. Try ingesting data first or check the symbol."
        else:
            analysis = f"Analysis temporarily unavailable due to API limitations. Found {len(filtered)} relevant documents. Query: {q}"
        
        # Still save to memory
        chat_memory.add_message(session_id, "user", q)
        chat_memory.add_message(session_id, "assistant", analysis)

    return {
        "results": filtered[:5],
        "analysis": analysis,
        "total": len(filtered),
        "projections": projections,
        "scenarios": scenarios,
        "red_flags": red_flags
    }

@router.get("/projections")
def get_projections(symbol: str = Query(..., description="Stock symbol")):
    projections = projection_service.get_projections(symbol)
    return {"symbol": symbol, "projections": projections}
