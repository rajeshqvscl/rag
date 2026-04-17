import sys
import os
from dotenv import load_dotenv

# Load environment variables FIRST before any imports
# Try Render's secret files location first, then local .env
if os.path.exists('/etc/secrets/.env'):
    load_dotenv('/etc/secrets/.env')
    print("Loaded .env from /etc/secrets/.env")
else:
    load_dotenv()
    print("Loaded .env from local directory")

# Fix Windows encoding issues
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi import Depends
from app.services.security_service import get_api_key

app = FastAPI(
    title="FinRAG Intelligence Portal"
)

# Startup event to initialize database and services
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*50)
    print("Starting FinRAG Backend...")
    print("="*50)
    
    # Initialize database
    try:
        from app.config.database import init_db, DATABASE_URL
        init_db()
        db_type = "Neon PostgreSQL" if "neon.tech" in DATABASE_URL else "PostgreSQL" if DATABASE_URL.startswith("postgresql") else "SQLite"
        print(f"✓ Database initialized ({db_type})")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
    
    # Start watcher service (optional)
    try:
        from app.services.watcher_service import start_watcher
        start_watcher()
        print("✓ Watcher service started")
    except Exception as e:
        print(f"⚠ Watcher service disabled: {e}")
    
    print("="*50)
    print("Backend ready at http://localhost:9000")
    print("="*50 + "\n")

# CORS for local dev and external API calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", "X-API-KEY"],
    allow_credentials=True,
    expose_headers=["*"]
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    error_details = traceback.format_exc()
    print(f"UNHANDLED ERROR: {exc}\n{error_details}")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc), "traceback": error_details}
    )

from app.routes.query import router as query_router
from app.routes.library import router as library_router
from app.routes.settings import router as settings_router
from app.routes.upload import router as upload_router
from app.routes.auth import router as auth_router
from app.routes.fin_ingest import router as fin_ingest_router
from app.routes.memory import router as memory_router
from app.routes.drafts import router as drafts_router
from app.routes.analytics import router as analytics_router
from app.routes.integrations import router as integrations_router
from app.routes.crm import router as crm_router
from app.routes.predictive import router as predictive_router
from app.routes.pgvector_memory import router as pgvector_memory_router
from app.routes.pitch_deck import router as pitch_deck_router
from app.routes.sentiment import router as sentiment_router
from app.routes.search import router as search_router
from app.routes.context_memory import router as context_memory_router
from app.routes.email_reply import router as email_reply_router
from app.routes.email_webhook import router as email_webhook_router
from app.routes.agent import router as agent_router
from app.routes.backup import router as backup_router
from app.routes.cache import router as cache_router
from app.routes.collaboration import router as collaboration_router
from app.routes.enterprise_security import router as enterprise_security_router
from app.routes.market import router as market_router
from app.routes.multimodal import router as multimodal_router

app.include_router(query_router, dependencies=[Depends(get_api_key)])
app.include_router(library_router, dependencies=[Depends(get_api_key)])
app.include_router(settings_router, dependencies=[Depends(get_api_key)])
app.include_router(upload_router, dependencies=[Depends(get_api_key)])
app.include_router(auth_router)
app.include_router(fin_ingest_router, dependencies=[Depends(get_api_key)])
app.include_router(memory_router, dependencies=[Depends(get_api_key)])
app.include_router(drafts_router, dependencies=[Depends(get_api_key)])
app.include_router(analytics_router, dependencies=[Depends(get_api_key)])
app.include_router(integrations_router, dependencies=[Depends(get_api_key)])
app.include_router(crm_router, dependencies=[Depends(get_api_key)])
app.include_router(predictive_router, dependencies=[Depends(get_api_key)])
app.include_router(pgvector_memory_router, dependencies=[Depends(get_api_key)])
app.include_router(pitch_deck_router, dependencies=[Depends(get_api_key)])
app.include_router(sentiment_router, dependencies=[Depends(get_api_key)])
app.include_router(search_router, dependencies=[Depends(get_api_key)])
app.include_router(context_memory_router, dependencies=[Depends(get_api_key)])
app.include_router(email_reply_router, dependencies=[Depends(get_api_key)])
app.include_router(email_webhook_router, dependencies=[Depends(get_api_key)])
app.include_router(agent_router, dependencies=[Depends(get_api_key)])
app.include_router(backup_router, dependencies=[Depends(get_api_key)])
app.include_router(cache_router, dependencies=[Depends(get_api_key)])
app.include_router(collaboration_router, dependencies=[Depends(get_api_key)])
app.include_router(enterprise_security_router, dependencies=[Depends(get_api_key)])
app.include_router(market_router, dependencies=[Depends(get_api_key)])
app.include_router(multimodal_router, dependencies=[Depends(get_api_key)])

# Health Check Endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "FinRAG Backend",
        "version": "4.6",
        "endpoints": {
            "api": "http://localhost:9000",
            "frontend": "http://localhost:9001"
        }
    }

# Serve Frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

# Serve CSS and JS directly in root if needed for the HTML to find them easily
@app.get("/{file_path:path}")
def serve_static_files(file_path: str):
    full_path = os.path.join(frontend_path, file_path)
    if os.path.exists(full_path):
        return FileResponse(full_path)
    return {"error": "Not Found"}