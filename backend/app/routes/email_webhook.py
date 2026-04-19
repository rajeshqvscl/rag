"""
Email webhook — routes incoming emails through the agentic pipeline.

POST /email-webhook/incoming  → full agentic processing
GET  /email-webhook/status    → webhook health
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
from app.services.security_service import get_api_key

router = APIRouter()


class IncomingEmailPayload(BaseModel):
    """Flexible email payload — accepts standard webhook formats."""
    # Sendgrid / Mailgun style
    from_email: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None
    subject: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None
    # Generic
    email_text: Optional[str] = None
    company: Optional[str] = None
    sender_name: Optional[str] = None

    class Config:
        populate_by_name = True


@router.post("/email-webhook/incoming")
async def handle_incoming_email(
    request: Request,
    api_key: str = Depends(get_api_key)
):
    """
    Incoming email webhook — runs full agentic pipeline:
    classify → retrieve → analyze → draft reply → schedule follow-up → store
    """
    try:
        # Try to parse as JSON; fall back to form data
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            payload = dict(form)

        # Extract email text from various formats
        email_text = (
            payload.get("email_text")
            or payload.get("text")
            or payload.get("body")
            or payload.get("plain")
            or ""
        )
        # Strip HTML if only HTML available
        if not email_text and payload.get("html"):
            import re
            email_text = re.sub(r'<[^>]+>', ' ', payload.get("html", "")).strip()

        if not email_text:
            return {
                "status": "skipped",
                "reason": "No email body found in payload",
                "payload_keys": list(payload.keys())
            }

        company = payload.get("company") or payload.get("from_company") or ""

        # Run agent pipeline
        from app.services.agent_service import process_email_agent
        result = process_email_agent(
            email_text=email_text,
            company=company,
            store_result=True,
        )

        return {
            "status": "processed",
            "agent_result": result,
        }

    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail=f"Webhook processing error: {e}\n{traceback.format_exc()}"
        )


@router.post("/email-webhook/test")
async def test_webhook(
    request: Request,
    api_key: str = Depends(get_api_key)
):
    """
    Test the agent pipeline with a sample email (no DB persistence).
    """
    try:
        body = await request.json()
        email_text = body.get("email_text", "Hello, I'm interested in learning more about your investment thesis.")
        company = body.get("company", "")

        from app.services.agent_service import process_email_agent
        result = process_email_agent(
            email_text=email_text,
            company=company,
            store_result=False,  # Don't persist test runs
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/email-webhook/status")
def get_webhook_status(api_key: str = Depends(get_api_key)):
    """Webhook health status."""
    return {
        "status": "active",
        "webhook_enabled": True,
        "pipeline": "agentic_rag",
        "endpoints": {
            "incoming": "POST /email-webhook/incoming",
            "test": "POST /email-webhook/test",
        }
    }
