from app.services.file_extractor import extract_text
from app.services.claude_service import structure_text
from app.services.rag_service import rag
from app.services.fin_service import ingest_fin_data

# Optional Celery import
try:
    from app.celery_app import celery_app
except ImportError:
    celery_app = None

# Lazy import for Google Drive (optional integration)
_drive_available = False
try:
    from app.services.drive_service import find_or_create_folder, upload_file
    _drive_available = True
except ImportError:
    def find_or_create_folder(company): return None
    def upload_file(path, folder_id): return None


def process_file_task(file_path, file_name, company):
    try:
        print("\n===== TASK STARTED =====")
        print("File:", file_name)

        # Early-exit guards
        if not file_path:
            return {"status": "error", "error": "file_path is None"}
        file_name = file_name or ""
        company = company or ""

        # 1. Drive Upload
        folder_id = find_or_create_folder(company)
        drive_id = upload_file(file_path, folder_id)

        print("Uploaded:", drive_id)

        # 2. Extract
        text = extract_text(file_path) or ""  # ← safe guard

        if not text.strip():
            return {"status": "empty"}

        # 3. Claude
        structured = structure_text(text) or {}  # ← safe guard

        # 4. RAG — use safe defaults so no key is None
        rag.add_documents([{
            "text": structured.get("content") or "",
            "type": structured.get("type") or "unknown",
            "section": structured.get("section") or "general"
        }])

        print("Stored in RAG:", rag.index.ntotal)

        return {
            "status": "success",
            "file": file_name,
            "content": structured.get("content") or "",
            "type": structured.get("type") or "unknown"
        }

    except Exception as e:
        print("ERROR:", str(e))
        return {"status": "error", "error": str(e)}

# Only register Celery task if celery is available
def ingest_market_data_task(symbol):
    try:
        from app.services.fin_service import ingest_fin_data
        return ingest_fin_data(symbol)
    except Exception as e:
        return str(e)

# Register with Celery if available
if celery_app:
    ingest_market_data_task = celery_app.task(name="ingest_market_data_task")(ingest_market_data_task)
