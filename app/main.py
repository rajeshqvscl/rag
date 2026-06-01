import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import asyncio
import time
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, String, Text, or_
from collections import defaultdict

def remove_emoji(text):
    if not isinstance(text, str):
        return text
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF" u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0" u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

def clean_for_json(obj):
    if isinstance(obj, str):
        return remove_emoji(obj)
    elif isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(i) for i in obj]
    return obj

from app.db.session import engine, SessionLocal, Base, get_db
from app.db.models import PitchDeck, ClientRevert
from app.rag.response_schemas import (
    ProcessResponse, StatusResponse, ResultResponse, InsightsResponse
)
from app.services.email_processor import process_email
from app.services.email_sender import send_email
from app.services.email_listener import fetch_inbound_emails, process_inbound_reverts
from app.services.matcher import (
    get_matches_for_investor,
    get_matches_for_client,
    parse_cheque_size,
    detect_sector,
    trigger_client_analysis,
    process_investor_match,
    run_matching_pipeline
)
from app.services.follow_up import (
    process_investor_follow_ups,
    process_client_follow_ups,
    run_all_follow_ups,
    mark_responded,
    get_follow_up_status
)

# Import auth and monitoring
from app.middleware.auth import verify_api_key, optional_api_key, get_system_status, get_client_tier
from app.monitoring.metrics import get_metrics_summary, format_prometheus_metrics, get_system_health
from app.feedback.collector import submit_feedback, get_feedback_stats, get_feedback_analysis
from app.config.registry import get_system_config, get_prompt, update_prompt

app = FastAPI()

import logging


class StatusEndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("GET /status/") == -1


logging.getLogger("uvicorn.access").addFilter(StatusEndpointFilter())

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=200)

# Use raw exception handler to catch encoding issues
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    try:
        error_msg = str(exc).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    except:
        error_msg = "Unicode encoding error"
    return JSONResponse(
        status_code=500,
        content={"detail": error_msg[:200]}
    )

# Simple rate limiting (in-memory)
rate_limit_storage = defaultdict(list)
RATE_LIMIT_REQUESTS = 10  # per minute
RATE_LIMIT_WINDOW = 60  # seconds

def check_rate_limit(client_id: str = "default"):
    """Simple rate limiting check"""
    now = time.time()
    rate_limit_storage[client_id] = [
        ts for ts in rate_limit_storage[client_id] if now - ts < RATE_LIMIT_WINDOW
    ]
    if len(rate_limit_storage[client_id]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    rate_limit_storage[client_id].append(now)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add thread pool for CPU-heavy operations
process_executor = ThreadPoolExecutor(max_workers=2)

# Serve frontend static files
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=frontend_path), name="static")
app.mount("/pages", StaticFiles(directory=os.path.join(frontend_path, "pages")), name="pages")

# Create tables (gracefully handle DB connection failures)
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[DB] Table creation skipped: {e}")

@app.get("/test")
def test():
    return {"status": "ok", "message": "Server is running"}

@app.get("/debug/llm")
def debug_llm():
    """Test LLM connectivity and API key presence"""
    import os
    from app.core.llm_client import get_safe_client
    groq_key = os.getenv("GROQ_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    result = {
        "groq_key_set": bool(groq_key),
        "groq_key_prefix": groq_key[:8] + "..." if groq_key else "",
        "gemini_key_set": bool(gemini_key),
        "gemini_key_prefix": gemini_key[:8] + "..." if gemini_key else "",
    }
    try:
        client = get_safe_client()
        result["client_created"] = True
        resp = client.chat_completion(
            messages=[{"role": "user", "content": "Say hello in 3 words"}],
            temperature=0
        )
        result["llm_response"] = resp[:100]
        result["llm_ok"] = True
    except Exception as e:
        result["client_created"] = False
        result["llm_ok"] = False
        result["error"] = str(e)[:500]
    return result

@app.get("/")
@app.head("/")
def root():
    return {"message": "FinRAG API is running"}

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check - tests DB connection"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ============ METRICS & MONITORING ENDPOINTS ============

@app.get("/metrics")
def metrics():
    """Prometheus-compatible metrics endpoint"""
    return Response(content=format_prometheus_metrics(), media_type="text/plain")


@app.get("/monitoring/health")
def monitoring_health():
    """Detailed system health check"""
    return get_system_health()


@app.get("/monitoring/summary")
def monitoring_summary():
    """Get metrics summary"""
    return get_metrics_summary()


@app.get("/auth/status")
def auth_status():
    """Get authentication system status"""
    return get_system_status()


# ============ FEEDBACK ENDPOINTS ============

@app.post("/feedback")
def create_feedback(
    query: str,
    response: str,
    rating: int,
    feedback_type: str,
    corrections: str = None,
    api_key: str = Depends(optional_api_key)
):
    """Submit user feedback"""
    result = submit_feedback(query, response, rating, feedback_type, corrections)
    return result


@app.get("/feedback/stats")
def feedback_stats():
    """Get feedback statistics"""
    return get_feedback_stats()


@app.get("/feedback/analysis")
def feedback_analysis():
    """Get detailed feedback analysis"""
    return get_feedback_analysis()


# ============ CONFIG ENDPOINTS ============

@app.get("/config")
def config_info():
    """Get system configuration"""
    return get_system_config()


@app.get("/config/prompt/{category}")
def get_prompt_config(category: str, version: str = None):
    """Get prompt configuration"""
    prompt = get_prompt(category, version)
    if not prompt:
        return {"error": "Prompt not found"}
    return prompt


@app.put("/config/prompt/{category}/{version}")
def update_prompt_config(category: str, version: str, prompt_data: dict):
    """Update prompt configuration"""
    result = update_prompt(category, version, prompt_data)
    return result


def run_pipeline_background(file_content, file_name: str, insight_id: int, job_id: int = None, db_url: str = "", fast_mode: bool = False):
    """Background task that runs the full pipeline with connection-optimized short-lived sessions"""
    from app.db.session import SessionLocal
    from app.services.job_queue import JobQueueService
    from app.db.models import PitchDeck, ClientRevert
    from app.rag.pipeline_orchestrator import set_fast_mode
    import time
    import json
    
    set_fast_mode(fast_mode)
    safe_file_name = file_name.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    print(f"[PIPELINE] Starting for insight_id={insight_id}, job_id={job_id}, file={safe_file_name}, fast_mode={fast_mode}")
    
    STAGES = [
        ("initializing", 0),
        ("pdf_parsing", 10),
        ("text_chunking", 15),
        ("embedding", 25),
        ("retrieving", 40),
        ("generating", 60),
        ("scoring", 80),
        ("finalizing", 90),
        ("completed", 100),
    ]
    
    def update_stage(stage_name: str, result_data: dict = None, status: str = None):
        progress = next((p for s, p in STAGES if s == stage_name), 0)
        print(f"[PIPELINE] Stage: {stage_name} ({progress}%)")
        
        # Open fresh session, update immediately, and close to prevent connection timeouts
        db = SessionLocal()
        try:
            insight = db.query(PitchDeck).filter(PitchDeck.id == insight_id).first()
            if insight:
                if status:
                    insight.status = status
                if result_data is not None:
                    insight.insights = result_data
                else:
                    current_insights = dict(insight.insights or {})
                    current_insights["stage"] = stage_name
                    current_insights["progress"] = progress
                    insight.insights = current_insights
                db.commit()
        except Exception as e:
            db.rollback()
            print(f"[PIPELINE DB ERROR] Stage update failed: {e}")
        finally:
            db.close()
            
        if job_id:
            JobQueueService.transition_job(job_id, "processing",
                                            stage=stage_name, progress=progress)
    
    # Verify the record exists before starting heavy processing
    db = SessionLocal()
    insight_exists = db.query(PitchDeck).filter(PitchDeck.id == insight_id).first() is not None
    db.close()
    
    if not insight_exists:
        print(f"[PIPELINE] insight_id={insight_id} not found")
        if job_id:
            JobQueueService.transition_job(job_id, "failed",
                                            error="insight record not found")
        return
    
    start_time = time.time()
    current_stage = "initializing"
    try:
        from io import BytesIO
        
        # Stage 1: PDF Extraction
        current_stage = "pdf_parsing"
        update_stage("pdf_parsing")
        file_stream = BytesIO(file_content)
        print(f"[PIPELINE] File size: {len(file_content)} bytes")
        
        # Stage 2: Text Chunking
        current_stage = "text_chunking"
        update_stage("text_chunking")
        
        # Main RAG pipeline (slow, takes ~30-40 seconds)
        print(f"[PIPELINE] Running process_email...")
        result = process_email(file_stream, file_name=file_name)
        print(f"[PIPELINE] process_email completed")
        
        doc_type = result.get("type", "investor")
        
        # Stage 3-5: Transition progress metrics
        current_stage = "embedding"
        update_stage("embedding")
        current_stage = "retrieving"
        update_stage("retrieving")
        current_stage = "generating"
        update_stage("generating")
        current_stage = "scoring"
        update_stage("scoring")
        current_stage = "finalizing"
        update_stage("finalizing")
        
        # Build final insights structure
        final_insights = dict(result)
        final_insights["stage"] = "completed"
        final_insights["progress"] = 100
        final_insights["elapsed_time"] = round(time.time() - start_time, 2)
        
        # Update original PitchDeck record with completed data (in-place)
        db = SessionLocal()
        try:
            insight = db.query(PitchDeck).filter(PitchDeck.id == insight_id).first()
            if insight:
                insight.company = result.get("company", "Unknown")
                insight.summary = result.get("summary", "")
                insight.email_draft = result.get("email", "")
                insight.verdict = result.get("verdict", "Neutral")
                insight.score = result.get("score", 0.0)
                insight.status = "completed"
                insight.insights = final_insights
                db.commit()
        except Exception as e:
            db.rollback()
            print(f"[PIPELINE DB ERROR] Finalizing original record failed: {e}")
            raise
        finally:
            db.close()
            
        # Create corresponding ClientRevert record
        db = SessionLocal()
        try:
            if doc_type == "investor":
                new_record = ClientRevert(
                    sender="Inbound PDF",
                    subject="Pitch Deck Upload",
                    body="Document analyzed via FinRAG",
                    intent=result.get("intent", {}).get("intent"),
                    confidence=result.get("intent", {}).get("confidence"),
                    signals=json.dumps(result.get("intent", {}).get("signals", [])),
                    next_step=result.get("strategy", {}).get("next_step"),
                    priority=result.get("strategy", {}).get("priority"),
                    reasoning=result.get("strategy", {}).get("reasoning"),
                    score=result.get("score", 0.0),
                    email_draft=result.get("email", "")
                )
            else:
                new_record = ClientRevert(
                    sender="Inbound Business Inquiry",
                    subject="Client Contact",
                    body="Inquiry analyzed via FinRAG",
                    intent=result.get("intent", {}).get("intent"),
                    confidence=result.get("intent", {}).get("confidence"),
                    signals=json.dumps(result.get("intent", {}).get("signals", [])),
                    next_step=result.get("strategy", {}).get("next_step"),
                    priority=result.get("strategy", {}).get("priority"),
                    reasoning=result.get("strategy", {}).get("reasoning"),
                    query_type=result.get("query_type", "Sales"),
                    urgency_level=result.get("urgency", "Standard"),
                    email_draft=result.get("email", "")
                )
            
            db.add(new_record)
            db.commit()
            print(f"[PIPELINE] Completed in {time.time() - start_time:.2f}s")
        except Exception as e:
            db.rollback()
            print(f"[PIPELINE DB ERROR] Creating client revert record failed: {e}")
            raise
        finally:
            db.close()
            
    except Exception as e:
        print(f"[PIPELINE ERROR] Stage: {current_stage}, Error: {str(e)}")
        # Log failure state on original record in fresh session
        db = SessionLocal()
        try:
            insight = db.query(PitchDeck).filter(PitchDeck.id == insight_id).first()
            if insight:
                insight.status = "failed"
                insight.insights = {
                    "error": str(e),
                    "stage": current_stage,
                    "failed_at": current_stage
                }
                db.commit()
        except Exception as inner_e:
            print(f"[PIPELINE FATAL ERROR] Could not save failure state: {inner_e}")
        finally:
            db.close()
            
        if job_id:
            JobQueueService.transition_job(job_id, "failed",
                                            stage=current_stage,
                                            error=str(e))
    finally:
        # Check and update the job queue status
        db = SessionLocal()
        try:
            insight = db.query(PitchDeck).filter(PitchDeck.id == insight_id).first()
            if job_id and insight and insight.status == "completed":
                insights_data = insight.insights or {}
                infra_conf = insights_data.get("_infra_confidence", 1.0)
                degraded = insights_data.get("_degraded_stages", [])
                if degraded:
                    JobQueueService.transition_job(job_id, "degraded",
                                                    stage="completed", progress=100,
                                                    pipeline_data={
                                                        "infra_confidence": infra_conf,
                                                        "degraded_stages": degraded,
                                                    })
                else:
                    JobQueueService.transition_job(job_id, "completed",
                                                    stage="completed", progress=100)
        except Exception as e:
            print(f"[PIPELINE DB ERROR] Final job queue transition failed: {e}")
        finally:
            db.close()


@app.post("/test-post")
async def test_post(file: UploadFile = File(...)):
    """Test if POST with file works"""
    print(f"[TEST] POST received: {file.filename}")
    return {"status": "ok", "filename": file.filename}

process_executor_async = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bg_pipeline")


@app.post("/process")
async def process(
    file: UploadFile = File(...),
    fast_mode: bool = False,
    db: Session = Depends(get_db),
    x_client_id: str = Header(None),
    x_fast_mode: Optional[str] = Header(None)
):
    """
    Main Pipeline: PDF -> PipelineOrchestrator -> DB
    Returns immediately with {status: "processing", id: <deck_id>}.
    Frontend polls GET /status/{id} for completion.
    """
    try:
        client_id = x_client_id or "anonymous"
        check_rate_limit(client_id)
        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large. Max 50MB.")
        
        safe_filename = (file.filename or "unknown.pdf").encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        is_fast = fast_mode or (x_fast_mode and x_fast_mode.lower() == "true")
        print(f"[PROCESS] Starting for file={safe_filename}, fast_mode={is_fast}")
        
        # Create DB record immediately with "processing" status
        from app.db.models import PitchDeck
        deck = PitchDeck(
            company="Processing...",
            summary="",
            email_draft="",
            verdict="Pending",
            score=0.0,
            status="processing",
        )
        deck.insights = {"stage": "initializing", "progress": 0}
        db.add(deck)
        db.commit()
        db.refresh(deck)
        insight_id = deck.id
        
        # Create job queue entry
        job_id = JobQueueService.create_job(
            file_name=safe_filename,
            file_size=len(file_content),
        )
        JobQueueService.transition_job(job_id, "processing",
                                        stage="initializing", progress=0,
                                        result_id=insight_id)
        
        print(f"[PROCESS] Created deck_id={insight_id}, job_id={job_id}, launching background pipeline (fast={is_fast})")
        
        # Launch processing in background thread — returns immediately
        db_url = str(db.bind.url) if hasattr(db, 'bind') and db.bind else ""
        process_executor_async.submit(
            run_pipeline_background, file_content, safe_filename, insight_id, job_id, db_url, is_fast
        )
        
        return ProcessResponse(
            status="processing",
            id=insight_id,
            job_id=job_id,
        )
            
    except HTTPException:
        raise
    except Exception as e:
        try:
            safe_error = str(e).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        except:
            safe_error = repr(e)
        print(f"[PROCESS ERROR] {safe_error}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": safe_error})


@app.get("/status/{item_id}", response_model=StatusResponse)
def get_status(item_id: int, db: Session = Depends(get_db)):
    """Get processing status by ID with progress"""
    insight = db.query(PitchDeck).filter(PitchDeck.id == item_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Item not found")
    
    insights_data = insight.insights or {}
    insights_data["id"] = insight.id
    insights_data["company"] = insight.company or ""
    insights_data["status"] = insight.status or "processing"
    
    return StatusResponse.from_orm_row(insight, insights_data)


@app.get("/result/{item_id}", response_model=ResultResponse)
def get_result(item_id: int, db: Session = Depends(get_db)):
    """
    Get the full result for a completed job.
    Decoupled from /status — frontend calls this only when status=completed.
    """
    insight = db.query(PitchDeck).filter(PitchDeck.id == item_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if insight.status != "completed":
        return ResultResponse(
            id=item_id, status=insight.status or "processing",
            result_available=False
        )
    
    insights_data = insight.insights or {}
    return ResultResponse(
        id=insight.id,
        company=insight.company or "",
        status=insight.status or "completed",
        insights=InsightsResponse.from_raw(insights_data),
        result_available=True,
    )


@app.post("/retry/{item_id}")
def retry_pipeline(item_id: int, db: Session = Depends(get_db)):
    """Retry a failed pipeline job - simplified"""
    insight = db.query(PitchDeck).filter(PitchDeck.id == item_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if insight.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")
    
    return {"message": "Retry not supported - please upload the file again", "id": item_id}


@app.post("/cancel/{item_id}")
def cancel_pipeline(item_id: int, db: Session = Depends(get_db)):
    """Cancel a running pipeline job"""
    insight = db.query(PitchDeck).filter(PitchDeck.id == item_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if insight.status not in ["processing", "pending"]:
        raise HTTPException(status_code=400, detail="Can only cancel processing jobs")
    
    insight.status = "cancelled"
    insight.insights = {"stage": "cancelled", "progress": 0, "cancelled_at": insight.insights.get("progress", 0)}
    db.commit()
    
    return {"status": "cancelled", "id": insight.id, "message": "Job cancelled"}


# ── Job Queue API ─────────────────────────────────────────────────
from app.services.job_queue import JobQueueService


@app.get("/api/jobs")
def list_jobs(status: str = None, limit: int = 50):
    """List all jobs in the queue, optionally filtered by status."""
    jobs = JobQueueService.list_jobs(status=status, limit=min(limit, 200))
    return {"jobs": jobs, "count": len(jobs)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    """Get a single job's state."""
    job = JobQueueService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int):
    """Retry a failed job."""
    success = JobQueueService.retry_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job cannot be retried")
    return {"status": "retrying", "id": job_id}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    """Cancel a queued or processing job."""
    success = JobQueueService.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")
    return {"status": "cancelled", "id": job_id}


@app.get("/investors")
def get_investors(db: Session = Depends(get_db)):
    """Test DB connection"""
    try:
        data = db.query(ClientRevert).limit(5).all()
        return {"count": len(data)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/clients")
def get_clients(db: Session = Depends(get_db)):
    try:
        return db.query(ClientRevert).order_by(ClientRevert.timestamp.desc()).all()
    except Exception as e:
        print(f"[CLIENTS ERROR] {str(e)}")
        return {"error": str(e)}

@app.get("/insights")
def get_insights(db: Session = Depends(get_db)):
    """Get all pitch deck analyses"""
    try:
        items = db.query(PitchDeck).order_by(PitchDeck.timestamp.desc()).all()
        return [
            {
                "id": i.id,
                "company": i.company,
                "status": i.status,
                "summary": i.summary,
                "email_draft": i.email_draft,
                "verdict": i.verdict,
                "score": i.score,
                "insights": i.insights,
                "timestamp": i.timestamp.isoformat() if i.timestamp else None
            }
            for i in items
        ]
    except Exception as e:
        print(f"[INSIGHTS ERROR] {str(e)}")
        return {"error": str(e)}

@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    """Test DB basic connection"""
    try:
        # Simple query
        result = db.execute(text("SELECT 1")).scalar()
        return {"db": "connected", "test": result}
    except Exception as e:
        return {"db": "error", "message": str(e)}


@app.get("/library")
def get_library(db: Session = Depends(get_db)):
    items = db.query(PitchDeck).all()

    return [
        {
            "id": i.id,
            "company": i.company,
            "status": i.status,
            "summary": i.summary,
            "email_draft": i.email_draft,
            "verdict": i.verdict,
            "score": i.score,
            "insights": i.insights,
            "timestamp": i.timestamp.isoformat() if i.timestamp else None
        }
        for i in items
    ]


# ============================================================
# DB Manager Endpoints (Intelligence Cloud Master DB)
# ============================================================

TABLE_MAP = {
    "pitch_deck_library": PitchDeck,
    "client_reverts": ClientRevert,
}

TABLE_LABELS = {
    "pitch_deck_library": "Pitch Deck Library",
    "client_reverts": "Client Reverts",
}

def row_to_dict(row):
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if hasattr(val, 'isoformat'):
            val = val.isoformat()
        d[col.name] = val
    return d

@app.get("/db/tables")
def get_db_tables(db: Session = Depends(get_db)):
    result = []
    for table_name, model in TABLE_MAP.items():
        try:
            total = db.query(model).count()
            try:
                archived = db.query(model).filter(model.archived_at.isnot(None)).count()
            except:
                archived = 0
            columns = [{"name": c.name, "type": str(c.type)} for c in model.__table__.columns]
            result.append({
                "name": table_name,
                "label": TABLE_LABELS.get(table_name, table_name),
                "row_count": total,
                "archived_count": archived,
                "active_count": total - archived,
                "columns": columns,
            })
        except Exception as e:
            print(f"[DB TABLES ERROR] {table_name}: {e}")
            result.append({
                "name": table_name,
                "label": TABLE_LABELS.get(table_name, table_name),
                "error": str(e),
                "row_count": 0,
                "archived_count": 0,
                "active_count": 0,
                "columns": [],
            })
    return result

@app.get("/db/table/{table_name}")
def get_table_data(table_name: str, include_archived: bool = False, search: str = "", page: int = 1, per_page: int = 50, db: Session = Depends(get_db)):
    try:
        model = TABLE_MAP.get(table_name)
        if not model:
            return {"error": f"Unknown table: {table_name}"}
        query = db.query(model)
        try:
            if include_archived:
                query = query.filter(model.archived_at.isnot(None))
            else:
                query = query.filter(model.archived_at.is_(None))
        except:
            pass
        if search:
            search_filter = []
            for col in model.__table__.columns:
                try:
                    search_filter.append(col.cast(String).ilike(f"%{search}%"))
                except:
                    pass
            if search_filter:
                query = query.filter(or_(*search_filter))
        total = query.count()
        rows = query.order_by(model.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
        return {"total": total, "page": page, "per_page": per_page, "rows": [row_to_dict(r) for r in rows]}
    except Exception as e:
        print(f"[DB TABLE DATA ERROR] {e}")
        return {"error": str(e)}

@app.post("/db/batch-delete")
def batch_delete(data: dict, db: Session = Depends(get_db)):
    table = data.get("table")
    ids = data.get("ids", [])
    model = TABLE_MAP.get(table)
    if not model:
        return {"error": f"Unknown table: {table}"}
    if not ids:
        return {"error": "No IDs provided"}
    deleted = db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok", "deleted": deleted}

@app.post("/db/batch-archive")
def batch_archive(data: dict, db: Session = Depends(get_db)):
    table = data.get("table")
    ids = data.get("ids", [])
    reason = data.get("reason", "")
    model = TABLE_MAP.get(table)
    if not model:
        return {"error": f"Unknown table: {table}"}
    if not ids:
        return {"error": "No IDs provided"}
    if not hasattr(model, 'archived_at'):
        return {"error": f"Table {table} does not support archiving"}
    now = datetime.utcnow()
    rows = db.query(model).filter(model.id.in_(ids))
    rows.update({"archived_at": now, "archived_reason": reason}, synchronize_session=False)
    db.commit()
    return {"status": "ok", "archived": len(ids)}

@app.post("/db/batch-restore")
def batch_restore(data: dict, db: Session = Depends(get_db)):
    table = data.get("table")
    ids = data.get("ids", [])
    model = TABLE_MAP.get(table)
    if not model:
        return {"error": f"Unknown table: {table}"}
    if not ids:
        return {"error": "No IDs provided"}
    if not hasattr(model, 'archived_at'):
        return {"error": f"Table {table} does not support restore"}
    rows = db.query(model).filter(model.id.in_(ids))
    rows.update({"archived_at": None, "archived_reason": None}, synchronize_session=False)
    db.commit()
    return {"status": "ok", "restored": len(ids)}


@app.post("/send-email")
async def send_email_api(data: dict):
    """
    Approves and sends the drafted email
    """
    if not all(k in data for k in ["to", "subject", "body"]):
        raise HTTPException(status_code=400, detail="Missing required fields: to, subject, body")
    if not data.get("to") or not data.get("to").strip():
        raise HTTPException(status_code=400, detail="Invalid 'to' email address")
    try:
        success = await asyncio.to_thread(
            send_email,
            to=data.get("to"),
            subject=data.get("subject"),
            body=data.get("body")
        )
        return {"status": "sent", "success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask")
async def ask(data: dict = {}):
    """Ask a question - requires body: {"question": "...", "namespace": "..."}"""
    question = data.get("question", "")
    namespace = data.get("namespace") or data.get("company")
    
    if not namespace:
        raise HTTPException(
            status_code=400, 
            detail="namespace is required. Provide 'namespace' or 'company' in request body to scope retrieval."
        )
    
    from app.rag.retriever import retrieve, retrieve_with_sources
    from app.rag.generator import generate_all_with_citations
    
    # Get retrieval results with source metadata
    retrieval_result = retrieve_with_sources(question, namespace=namespace, top_k=5)
    context_chunks = retrieval_result["chunks"]
    sources = retrieval_result["sources"]
    
    # Generate response with citations
    result = generate_all_with_citations(context_chunks, sources)
    
    return {
        "question": question, 
        "answer": result.get("summary", "No answer found"),
        "citations": result.get("citations", []),
        "sources_count": len(sources)
    }


@app.post("/ask/debug")
async def ask_debug(data: dict = {}):
    """Debug endpoint that shows retrieval metadata"""
    import time
    question = data.get("question", "")
    section = data.get("section")
    doc_id = data.get("doc_id")
    namespace = data.get("namespace") or data.get("company")
    
    if not namespace:
        raise HTTPException(
            status_code=400, 
            detail="namespace is required. Provide 'namespace' or 'company' in request body."
        )
    
    from app.rag.retriever import retrieve_with_sources
    
    start_time = time.time()
    
    retrieval_result = retrieve_with_sources(
        question, 
        namespace=namespace,
        section=section, 
        doc_id=doc_id,
        top_k=5
    )
    
    latency_ms = round((time.time() - start_time) * 1000, 2)
    
    return {
        "question": question,
        "chunks_retrieved": retrieval_result["chunks"],
        "sources": retrieval_result["sources"],
        "count": retrieval_result["count"],
        "latency_ms": latency_ms,
        "filters_applied": {
            "namespace": namespace,
            "section": section,
            "doc_id": doc_id
        }
    }


@app.post("/ask/stream")
async def ask_stream(data: dict = {}):
    """Streaming endpoint - yields chunks as they're generated"""
    question = data.get("question", "")
    namespace = data.get("namespace") or data.get("company")
    
    if not namespace:
        raise HTTPException(
            status_code=400, 
            detail="namespace is required. Provide 'namespace' or 'company' in request body."
        )
    
    from app.rag.retriever import retrieve_with_sources
    from app.core.llm_client import get_safe_client
    
    # Get retrieval results
    retrieval_result = retrieve_with_sources(question, namespace=namespace, top_k=5)
    context_chunks = retrieval_result["chunks"]
    sources = retrieval_result["sources"]
    
    # Build context for LLM
    from app.rag.generator import limit_context
    merged_context = limit_context(context_chunks)
    
    # Create prompt
    prompt = f"""Based on the following context, answer the question about the document.

Context:
{merged_context}

Question: {question}

Provide a clear, detailed answer based on the context above.
"""
    
    # Stream the response
    async def generate():
        # Yield start event
        yield "data: {\"type\": \"start\", \"question\": \"" + question.replace("\"", "\\\"") + "\"}\n\n"
        
        # Stream chunks from LLM
        client = get_safe_client()
        for chunk in client.chat_completion_stream([{"role": "user", "content": prompt}]):
            # Fix backslash issue in f-string
            safe_chunk = chunk.replace(chr(10), ' ').replace('"', '\\"')
            yield f"data: {{\"type\": \"token\", \"content\": \"{safe_chunk}\"}}\n\n"
            await asyncio.sleep(0.01)
        
        # Yield sources at the end
        yield f"data: {{\"type\": \"sources\", \"count\": {len(sources)}}}\n\n"
        
        yield "data: {\"type\": \"done\"}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/compare")
def compare_documents_endpoint(data: dict = {}):
    """Compare multiple documents across specified dimensions"""
    import asyncio
    from app.rag.comparator import compare_documents
    
    doc_ids = data.get("doc_ids", [])
    dimensions = data.get("dimensions")
    companies = data.get("companies")
    namespaces = data.get("namespaces")
    comparison_type = data.get("comparison_type", "detailed")
    deck_type = data.get("deck_type", "seed")
    
    if not doc_ids or len(doc_ids) < 2:
        return {"error": "Need at least 2 documents to compare"}
    
    doc_ids = doc_ids[:3]
    
    try:
        result = compare_documents(doc_ids, dimensions, companies, comparison_type, deck_type, namespaces)
        return result
    except Exception as e:
        return {"error": str(e), "comparison_type": comparison_type}


@app.get("/documents/available")
def get_available_documents_endpoint():
    """Get all available documents for comparison"""
    from app.rag.comparator import get_available_documents
    
    documents = get_available_documents()
    return {"documents": documents, "count": len(documents)}


@app.post("/compare/quick")
def quick_compare_endpoint(data: dict = {}):
    """Quick comparison between two documents"""
    from app.rag.comparator import quick_compare
    
    doc_id1 = data.get("doc_id1", "")
    doc_id2 = data.get("doc_id2", "")
    company1 = data.get("company1", "Company A")
    company2 = data.get("company2", "Company B")
    namespace1 = data.get("namespace1") or data.get("company1_namespace")
    namespace2 = data.get("namespace2") or data.get("company2_namespace")
    
    result = quick_compare(doc_id1, doc_id2, company1, company2, [namespace1, namespace2])
    return result





@app.post("/classify-intent")
def classify_intent(data: dict = {}):
    """Classify query intent for better routing"""
    from app.rag.intent_classifier import classify_intent, get_retrieval_config
    
    query = data.get("query", "")
    intent_result = classify_intent(query)
    retrieval_config = get_retrieval_config(intent_result)
    
    return {
        "query": query,
        "intent": intent_result["intent"],
        "confidence": intent_result["confidence"],
        "suggested_sections": intent_result["suggested_sections"],
        "keywords_found": intent_result["keywords_found"],
        "retrieval_config": retrieval_config
    }


@app.post("/search/web")
def web_search(data: dict = {}):
    """Search the web for additional context"""
    from app.rag.web_searcher import search_web
    
    query = data.get("query", "")
    num_results = data.get("num_results", 5)
    
    results = search_web(query, num_results=num_results)
    return {"query": query, "results": results, "count": len(results)}


@app.post("/search/hybrid")
def hybrid_search(data: dict = {}):
    """Search combining local documents + web"""
    from app.rag.retriever import retrieve_with_sources
    from app.rag.web_searcher import smart_search
    
    query = data.get("query", "")
    use_web = data.get("use_web", True)
    web_threshold = data.get("web_threshold", 0.6)
    namespace = data.get("namespace") or data.get("company")
    
    result = smart_search(
        query, 
        local_retrieval_fn=lambda q: retrieve_with_sources(q, namespace=namespace, top_k=5),
        use_web=use_web,
        web_threshold=web_threshold,
        namespace=namespace
    )
    return result


@app.get("/documents/tables")
def get_tables():
    """Get all extracted tables from documents"""
    from app.services.document_processor import get_all_tables
    
    tables = get_all_tables()
    return {"tables": tables, "count": len(tables)}


@app.post("/ask/with-session")
async def ask_with_session(data: dict = {}):
    """Ask a question within a session (document-scoped)"""
    question = data.get("question", "")
    namespace = data.get("namespace") or data.get("company")
    doc_id = data.get("doc_id")  # Optional: scope to specific document
    
    if not namespace:
        raise HTTPException(
            status_code=400, 
            detail="namespace is required. Provide 'namespace' or 'company' in request body."
        )
    
    from app.rag.retriever import retrieve_with_sources
    from app.rag.generator import generate_all_with_citations
    
    retrieval_result = retrieve_with_sources(
        question, 
        namespace=namespace,
        doc_id=doc_id,
        top_k=5
    )
    context_chunks = retrieval_result["chunks"]
    sources = retrieval_result["sources"]
    
    result = generate_all_with_citations(context_chunks, sources)
    
    return {
        "question": question,
        "answer": result.get("summary", "No answer found"),
        "citations": result.get("citations", []),
        "sources_count": len(sources),
        "doc_id": doc_id,
        "namespace": namespace,
    }


@app.post("/fetch-emails")
def fetch_emails():
    """Fetch and process inbound emails from IMAP"""
    emails = fetch_inbound_emails()
    return {"count": len(emails), "emails": emails}


@app.post("/process-reverts")
def process_reverts():
    """Process inbound reverts: classify and save to DB"""
    return process_inbound_reverts()


@app.get("/reverts")
def get_all_reverts(db: Session = Depends(get_db)):
    """Get all client reverts"""
    try:
        return db.query(ClientRevert).order_by(ClientRevert.timestamp.desc()).all()
    except Exception as e:
        return {"error": str(e)}


@app.get("/reverts/{revert_id}")
def get_revert(revert_id: int, db: Session = Depends(get_db)):
    """Get a specific revert by ID"""
    revert = db.query(ClientRevert).filter(ClientRevert.id == revert_id).first()
    if not revert:
        raise HTTPException(status_code=404, detail="Revert not found")
    return revert


@app.get("/matches/investor/{investor_id}")
def matches_for_investor(investor_id: int):
    """Get matching clients for an investor"""
    return get_matches_for_investor(investor_id)


@app.get("/matches/client/{client_id}")
def matches_for_client(client_id: int):
    """Get matching investors for a client"""
    return get_matches_for_client(client_id)


@app.post("/match/investor/{investor_id}")
def match_investor(investor_id: int):
    """Process investor match and generate analysis"""
    return process_investor_match(investor_id)


@app.post("/match/client/{client_id}")
def match_client(client_id: int, document_path: str = None):
    """Trigger pitch deck analysis for client"""
    from app.services.matcher import trigger_client_analysis
    return trigger_client_analysis(client_id, document_path)


@app.post("/run-matching")
def run_matching():
    """Run full matching pipeline"""
    return run_matching_pipeline()


@app.post("/followups/investors")
def followup_investors():
    """Process investor follow-ups"""
    return process_investor_follow_ups()


@app.post("/followups/clients")
def followup_clients():
    """Process client follow-ups"""
    return process_client_follow_ups()


@app.post("/followups/all")
def followup_all():
    """Process all follow-ups"""
    return run_all_follow_ups()


@app.post("/respond/{entity_type}/{entity_id}")
def respond(entity_type: str, entity_id: int, intent: str):
    """Mark entity response (interested/not_interested)"""
    return mark_responded(entity_type, entity_id, intent)


@app.get("/archive/{entity_type}")
def get_archived(entity_type: str, db: Session = Depends(get_db)):
    """Get archived leads."""
    if entity_type == "investor":
        items = db.query(ClientRevert).filter(
            ClientRevert.status == "archived"
        ).all()
    elif entity_type == "client":
        items = db.query(ClientRevert).filter(
            ClientRevert.status == "archived"
        ).all()
    else:
        return {"error": "Invalid entity type. Use 'investor' or 'client'"}
    
    return [
        {
            "id": i.id,
            "company": i.company,
            "sender": i.sender,
            "archived_at": i.archived_at.isoformat() if i.archived_at else None,
            "archived_reason": i.archived_reason,
            "intent": i.intent
        }
        for i in items
    ]


@app.post("/archive/reactivate/{entity_type}/{entity_id}")
def reactivate_lead(entity_type: str, entity_id: int, db: Session = Depends(get_db)):
    """Reactivate archived lead."""
    if entity_type == "investor":
        entity = db.query(ClientRevert).filter(ClientRevert.id == entity_id).first()
    elif entity_type == "client":
        entity = db.query(ClientRevert).filter(ClientRevert.id == entity_id).first()
    else:
        return {"error": "Invalid entity type. Use 'investor' or 'client'"}
    
    if not entity:
        return {"error": f"{entity_type} not found"}
    
    entity.status = "pending"
    entity.archived_reason = "reactivated"
    entity.archived_at = None
    db.commit()
    
    return {
        "status": "reactivated",
        "entity_type": entity_type,
        "id": entity_id,
        "new_status": "pending"
    }


@app.get("/followups/status/{entity_type}/{entity_id}")
def followup_status(entity_type: str, entity_id: int):
    """Get follow-up status for entity"""
    return get_follow_up_status(entity_type, entity_id)


@app.post("/automation/daily")
def run_daily_automation():
    """
    Runs complete daily automation pipeline:
    1. Fetch emails from IMAP
    2. Process reverts (classify + save)
    3. Run matching (bi-directional)
    4. Process follow-ups + auto-archive
    """
    from app.services.email_listener import fetch_inbound_emails, process_inbound_reverts
    
    results = {}
    
    # Step 1: Fetch emails
    try:
        emails = fetch_inbound_emails()
        results["fetch"] = {"status": "ok", "count": len(emails)}
    except Exception as e:
        results["fetch"] = {"status": "error", "error": str(e)}
    
    # Step 2: Process reverts
    try:
        process_result = process_inbound_reverts()
        results["process"] = process_result
    except Exception as e:
        results["process"] = {"status": "error", "error": str(e)}
    
    # Step 3: Run matching (bi-directional)
    try:
        matching_result = run_matching_pipeline()
        results["matching"] = matching_result
    except Exception as e:
        results["matching"] = {"status": "error", "error": str(e)}
    
    # Step 4: Process follow-ups
    try:
        followup_result = run_all_follow_ups()
        results["followups"] = followup_result
    except Exception as e:
        results["followups"] = {"status": "error", "error": str(e)}
    
    return results


@app.post("/contradictions")
def check_contradictions_endpoint(data: dict = {}):
    """Check for contradictions across documents"""
    from app.rag.contradiction_checker import check_contradictions
    
    doc_ids = data.get("doc_ids", [])
    companies = data.get("companies")
    namespaces = data.get("namespaces") or data.get("namespace")
    
    result = check_contradictions(doc_ids, companies, namespaces=namespaces)
    return result


@app.post("/contradictions/single")
def check_single_contradiction(data: dict = {}):
    """Check a single document for internal inconsistencies"""
    from app.rag.contradiction_checker import check_single_document
    
    doc_id = data.get("doc_id", "")
    query = data.get("query", "key metrics")
    namespace = data.get("namespace") or data.get("company")
    
    result = check_single_document(doc_id, query, namespace=namespace)
    return result


@app.get("/documents/related/{doc_id}")
def get_related_documents(doc_id: str):
    """Get documents related to a given document"""
    from app.rag.relationship_graph import find_related_documents
    
    related = find_related_documents(doc_id, threshold=0.5, limit=10)
    return {"doc_id": doc_id, "related": related, "count": len(related)}


@app.get("/documents/clusters")
def get_document_clusters(threshold: float = 0.6):
    """Get clusters of related documents"""
    from app.rag.relationship_graph import get_document_clusters
    
    clusters = get_document_clusters(threshold)
    return {"clusters": clusters, "count": len(clusters)}


@app.get("/documents/graph")
def get_relationship_graph():
    """Get complete relationship graph"""
    from app.rag.relationship_graph import build_relationship_graph
    
    graph = build_relationship_graph()
    return graph


@app.post("/report/generate")
def generate_report_endpoint(data: dict = {}):
    """Generate an investment report"""
    from app.rag.report_generator import generate_report
    
    doc_ids = data.get("doc_ids")
    template = data.get("template", "detailed")
    company_name = data.get("company_name")
    namespace = data.get("namespace") or data.get("company")
    
    result = generate_report(doc_ids, template, company_name, namespace=namespace)
    return result


@app.post("/report/summary")
def quick_summary_endpoint(data: dict = {}):
    """Generate a quick summary"""
    from app.rag.report_generator import generate_quick_summary
    
    doc_id = data.get("doc_id")
    namespace = data.get("namespace") or data.get("company")
    
    result = generate_quick_summary(doc_id, namespace=namespace)
    return result


@app.get("/workflows")
def list_workflows():
    """List all available workflows"""
    from app.agents.workflow_engine import get_workflow_engine
    
    engine = get_workflow_engine()
    return {"workflows": engine.list_workflows()}


@app.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    """Get workflow definition"""
    from app.agents.workflow_engine import get_workflow_engine
    
    engine = get_workflow_engine()
    workflow = engine.get_workflow(workflow_id)
    
    if not workflow:
        return {"error": "Workflow not found"}
    
    return workflow


@app.post("/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, data: dict = {}):
    """Execute a workflow"""
    from app.agents.workflow_engine import get_workflow_engine
    
    context = data.get("context", {})
    engine = get_workflow_engine()
    result = await engine.execute_workflow(workflow_id, context)
    return result


@app.get("/workflows/history")
def get_workflow_history():
    """Get workflow execution history"""
    from app.agents.workflow_engine import get_workflow_engine
    
    engine = get_workflow_engine()
    return {"history": engine.get_execution_history(10)}


@app.post("/chunk/smart")
def smart_chunk_text(data: dict = {}):
    """Smart chunk text using semantic boundaries"""
    from app.rag.semantic_chunker import smart_chunk
    
    text = data.get("text", "")
    strategy = data.get("strategy", "auto")
    chunk_size = data.get("chunk_size", 600)
    
    chunks = smart_chunk(text, strategy, chunk_size)
    return {"chunks": chunks, "count": len(chunks)}


# ============ PITCH DECK CONFIGURATION API ============

@app.get("/pitch/config")
def get_pitch_config(mode: str = "general"):
    """Get pitch configuration for different presentation modes"""
    from app.config.pitch_config import PitchConfig, PitchMode
    
    try:
        pitch_mode = PitchMode(mode)
    except ValueError:
        pitch_mode = PitchMode.GENERAL
    
    return PitchConfig.get_config(pitch_mode)


@app.get("/pitch/positioning")
def get_pitch_positioning(mode: str = "general"):
    """Get positioning for a specific pitch mode"""
    from app.config.pitch_config import PitchConfig, PitchMode
    
    try:
        pitch_mode = PitchMode(mode)
    except ValueError:
        pitch_mode = PitchMode.GENERAL
    
    positioning = PitchConfig.get_positioning(pitch_mode)
    return positioning.__dict__


@app.get("/pitch/agents")
def get_pitch_agents(mode: str = "general"):
    """Get AI agent configurations for a pitch mode"""
    from app.config.pitch_config import PitchConfig, PitchMode
    
    try:
        pitch_mode = PitchMode(mode)
    except ValueError:
        pitch_mode = PitchMode.GENERAL
    
    agents = PitchConfig.get_agents(pitch_mode)
    return {"agents": [a.__dict__ for a in agents]}


@app.get("/pitch/roi")
def get_pitch_roi(mode: str = "general"):
    """Get ROI metrics for a pitch mode"""
    from app.config.pitch_config import PitchConfig, PitchMode
    
    try:
        pitch_mode = PitchMode(mode)
    except ValueError:
        pitch_mode = PitchMode.GENERAL
    
    metrics = PitchConfig.get_roi_metrics(pitch_mode)
    return {"metrics": [m.__dict__ for m in metrics]}


@app.get("/pitch/trust")
def get_pitch_trust(mode: str = "general"):
    """Get trust layer configuration for a pitch mode"""
    from app.config.pitch_config import PitchConfig, PitchMode
    
    try:
        pitch_mode = PitchMode(mode)
    except ValueError:
        pitch_mode = PitchMode.GENERAL
    
    trust = PitchConfig.get_trust_layer(pitch_mode)
    return trust.__dict__


@app.get("/pitch/verticals")
def get_pitch_verticals():
    """Get all vertical positioning options"""
    from app.config.pitch_config import PitchConfig
    return PitchConfig.get_verticals()


@app.post("/pitch/set-mode")
def set_pitch_mode(data: dict = {}):
    """Set the current pitch mode (stored in memory for session)"""
    mode = data.get("mode", "general")
    from app.config.pitch_config import PitchMode, PitchConfig
    
    try:
        pitch_mode = PitchMode(mode)
        return {"status": "ok", "mode": pitch_mode.value, "positioning": PitchConfig.get_positioning(pitch_mode).__dict__}
    except ValueError:
        return {"status": "error", "message": f"Invalid mode: {mode}. Valid modes: investor, enterprise, technical, general"}


@app.get("/analysis/deck-types")
def get_deck_types():
    """Get all available pitch deck types for analysis"""
    from app.rag.analysis_config import AnalysisConfig
    return {"deck_types": AnalysisConfig.get_all_types()}


@app.get("/analysis/config")
def get_analysis_config(deck_type: str = "seed"):
    """Get analysis configuration for a specific deck type"""
    from app.rag.analysis_config import AnalysisConfig, DeckType
    config = AnalysisConfig.get_config_by_name(deck_type)
    return {
        "name": config.name,
        "tagline": config.tagline,
        "focus_areas": config.focus_areas,
        "critical_metrics": config.critical_metrics,
        "red_flags": config.red_flags,
        "dimensions": [
            {"name": d.name, "description": d.description, "weight": d.weight, "keywords": d.keywords}
            for d in config.dimensions
        ]
    }


@app.get("/analysis/dimensions")
def get_analysis_dimensions(deck_type: str = "seed", mode: str = "detailed"):
    """Get analysis dimensions for a specific deck type"""
    from app.rag.analysis_config import AnalysisConfig, DeckType
    dimensions = AnalysisConfig.get_dimensions(DeckType(deck_type), mode)
    weighted = AnalysisConfig.get_weighted_dimensions(DeckType(deck_type))
    return {"dimensions": dimensions, "weighted_dimensions": weighted}
