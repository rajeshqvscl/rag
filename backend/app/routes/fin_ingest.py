from fastapi import APIRouter, Query
from app.services.fin_service import ingest_fin_data

router = APIRouter(prefix="/fin", tags=["financial"])


@router.get("/ingest")
def ingest_fin(symbol: str = Query(..., description="Stock symbol e.g. AAPL")):
    try:
        # Synchronous ingestion
        result = ingest_fin_data(symbol)
        return {"status": "success", "message": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

