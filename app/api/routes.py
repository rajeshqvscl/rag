from fastapi import APIRouter, HTTPException
from app.services.email_processor import process_email
from app.services.email_sender import send_email

router = APIRouter()


@router.post("/process-email")
async def process(payload: dict):
    return await process_email(payload.get("file"), payload.get("file_name", "unknown"))


@router.post("/send-email")
def send(payload: dict):
    if not all(k in payload for k in ["to", "subject", "body"]):
        raise HTTPException(status_code=400, detail="Missing required fields: to, subject, body")
    send_email(
        payload["to"],
        payload["subject"],
        payload["body"]
    )

    return {"status": "sent"}


@router.get("/email/{email_id}")
def get_email(email_id: int):
    raise HTTPException(status_code=501, detail="Email retrieval not implemented")


@router.post("/fetch-emails")
def fetch_emails():
    emails = fetch_inbound_emails()
    return {"count": len(emails), "emails": emails}


@router.post("/process-reverts")
def process_reverts():
    return process_inbound_reverts()


@router.get("/matches/investor/{investor_id}")
def investor_matches(investor_id: int):
    return get_matches_for_investor(investor_id)


@router.get("/matches/client/{client_id}")
def client_matches(client_id: int):
    return get_matches_for_client(client_id)


@router.post("/match/investor/{investor_id}")
def match_investor(investor_id: int):
    return process_investor_match(investor_id)


@router.post("/analyze-client/{client_id}")
def analyze_client(client_id: int, document_path: str = None):
    return trigger_client_analysis(client_id, document_path)


@router.post("/run-matching")
def run_matching():
    return run_matching_pipeline()