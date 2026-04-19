import os
import uvicorn
from fastapi import FastAPI, Depends, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# DEFINE DIRECTORIES
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "frontend"))

# LOAD ENV
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# CLOUD ADAPTER
PORT = int(os.getenv("PORT", 9000))
IS_HUGGINGFACE = os.getenv("SPACE_ID") is not None

from app.services.security_service import get_api_key

app = FastAPI(title="FinRAG Professional")

# GLOBAL CORS (Essential for Hugging Face)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    print("\n" + "="*50)
    print("FINRAG PROFESSIONAL BACKEND STARTING")
    print(f"Frontend: {FRONTEND_DIR}")
    
    # Initialize database
    try:
        from app.config.database import init_db
        init_db()
        print("Database: [SUCCESS]")
        
        # Diagnostic Key Print
        from app.config import get_anthropic_key
        raw_key = get_anthropic_key() or ""
        clean_key = raw_key.strip().replace('"', '').replace("'", "")
        if clean_key.startswith("sk-ant-"):
            print(f"ANTHROPIC_KEY: {clean_key[:12]}...{clean_key[-5:]} ({len(clean_key)} chars)")
        else:
            print("ANTHROPIC_KEY: [INVALID PREFIX OR MISSING]")
    except Exception as e:
        print(f"Database/Key Init Error: {e}")
    print("="*50 + "\n")

# Import Routers
from app.routes import query, library, settings, upload, auth, pitch_deck

app.include_router(query.router, tags=["search"], dependencies=[Depends(get_api_key)])
app.include_router(library.router, tags=["library"], dependencies=[Depends(get_api_key)])
app.include_router(settings.router, tags=["settings"], dependencies=[Depends(get_api_key)])
app.include_router(upload.router, tags=["upload"], dependencies=[Depends(get_api_key)])
app.include_router(auth.router, tags=["auth"])
app.include_router(pitch_deck.router, tags=["pitch-deck"], dependencies=[Depends(get_api_key)])

# HIGH-PRIORITY STATIC MAPPING (Cloud Optimized)
@app.get("/")
async def get_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/style.css")
async def get_css():
    return FileResponse(os.path.join(FRONTEND_DIR, "style.css"))

@app.get("/app.js")
async def get_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))

@app.get("/favicon.png")
@app.get("/favicon.ico")
async def get_favicon():
    # If favicon exists, return it; otherwise return a 204 No Content to avoid crashes
    path = os.path.join(FRONTEND_DIR, "favicon.png")
    if os.path.exists(path):
        return FileResponse(path)
    return ""  # Professional silent fallback

# Mount remaining static assets (Images, etc)
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    # Render uses $PORT, defaults to 10000
    render_port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=render_port)
