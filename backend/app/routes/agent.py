"""
Agentic RAG API routes.

POST /agent/process-email   → full agentic email pipeline
POST /agent/query           → agentic query/search
GET  /agent/status          → health + tool availability
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from app.services.security_service import get_api_key

router = APIRouter()


# ── Request / Response Models ──────────────────────────

class EmailProcessRequest(BaseModel):
    email_text: str = Field(..., description="Full email body text")
    company: str = Field("", description="Company name (optional — agent will try to extract)")
    store_result: bool = Field(True, description="Persist result to DB")


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    company: str = Field("", description="Optional company/symbol filter")
    k: int = Field(5, description="Number of chunks to retrieve", ge=1, le=20)


# ── Endpoints ──────────────────────────────────────────

@router.post("/agent/process-email")
def process_email(
    request: EmailProcessRequest,
    api_key: str = Depends(get_api_key)
):
    """
    Full agentic flow:
    classify → retrieve (BM25) → analyze → generate reply → schedule follow-up → store
    """
    try:
        from app.services.agent_service import process_email_agent
        result = process_email_agent(
            email_text=request.email_text,
            company=request.company,
            store_result=request.store_result,
        )
        return result
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")


@router.post("/agent/query")
def agent_query(
    request: QueryRequest,
    api_key: str = Depends(get_api_key)
):
    """
    Agentic query flow:
    Agent decides → BM25 retrieve → analyze → structured answer
    (Replaces naive Query → Claude → Answer)
    """
    try:
        from app.services.agent_service import process_query_agent
        result = process_query_agent(
            query=request.query,
            company=request.company,
            k=request.k,
        )
        return result
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")


@router.get("/agent/status")
def agent_status(api_key: str = Depends(get_api_key)):
    """Tool availability and system status."""
    import os

    tools_status = {}
    # Check BM25
    try:
        import rank_bm25
        tools_status["bm25_retriever"] = "✓ available"
    except ImportError:
        tools_status["bm25_retriever"] = "⚠ rank_bm25 not installed — TF-IDF fallback active"

    # Check Claude
    tools_status["claude_api"] = (
        "✓ configured" if os.getenv("ANTHROPIC_API_KEY") else "✗ ANTHROPIC_API_KEY not set"
    )

    # Check FAISS index
    meta_path = "app/data/faiss_index/meta.pkl"
    if os.path.exists(meta_path):
        import pickle
        try:
            with open(meta_path, "rb") as f:
                docs = pickle.load(f)
            tools_status["knowledge_base"] = f"✓ {len(docs)} documents indexed"
        except Exception:
            tools_status["knowledge_base"] = "⚠ index exists but could not be read"
    else:
        tools_status["knowledge_base"] = "⚠ no documents indexed yet — upload pitch decks first"

    return {
        "status": "healthy",
        "agent": "FinRAG Agentic Controller v1.0",
        "flow": "Email → classify → BM25 retrieve → analyze → reply → schedule → store",
        "tools": {
            "1_retrieve_chunks": tools_status["bm25_retriever"],
            "2_analyze_pitch": tools_status["claude_api"],
            "3_classify_email": tools_status["claude_api"],
            "4_generate_reply": tools_status["claude_api"],
            "5_schedule_followup": "✓ always available (rule-based)",
        },
        "knowledge_base": tools_status["knowledge_base"],
    }


# Keep legacy endpoint working
@router.post("/agent/execute")
def execute_agent_task(
    request: dict,
    api_key: str = Depends(get_api_key)
):
    """Legacy endpoint — redirects to /agent/query."""
    try:
        task = request.get("task", "")
        from app.services.agent_service import process_query_agent
        result = process_query_agent(query=task)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
