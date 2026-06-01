import imaplib
import email
import os
import json
from datetime import datetime
from app.db.session import SessionLocal
from app.db.models import ClientRevert
from app.agents.profile_extractor import extract_investor_profile, extract_client_profile
from app.agents.router_agent import classify_revert


def fetch_inbound_emails(folder="INBOX", unread_only=True):
    """
    Fetch emails from IMAP server.
    Requires: IMAP_HOST, IMAP_USER, IMAP_PASS env vars.
    """
    host = os.getenv("IMAP_HOST")
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASS")
    
    if not host or not user or not password:
        print("[EMAIL] IMAP credentials not configured")
        return []
    
    try:
        mail = imaplib.IMAP4_SSL(host)
        mail.login(user, password)
        mail.select(folder)
        
        search_criteria = "UNSEEN" if unread_only else "ALL"
        status, message_ids = mail.search(None, search_criteria)
        
        if status != "OK":
            return []
        
        email_ids = message_ids[0].split()
        emails = []
        
        for eid in email_ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue
                
            msg = email.message_from_bytes(msg_data[0][1])
            
            subject = msg.get("Subject", "No Subject")
            sender = msg.get("From", "Unknown")
            date = msg.get("Date", datetime.now().isoformat())
            
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
                        except:
                            body = str(part.get_payload())
                        break
            else:
                try:
                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
                except:
                    body = str(msg.get_payload())
            
            emails.append({
                "subject": subject,
                "sender": sender,
                "date": date,
                "body": body[:5000]
            })
            
            if unread_only:
                mail.store(eid, "+FLAGS", "\\Seen")
        
        mail.close()
        mail.logout()
        
        print(f"[EMAIL] Fetched {len(emails)} emails")
        return emails
        
    except Exception as e:
        print(f"[EMAIL ERROR] {str(e)}")
        return []


def process_inbound_reverts():
    """
    Main pipeline: Fetch emails → Classify → Extract Profile → Save to DB → Trigger actions
    """
    emails = fetch_inbound_emails()
    
    if not emails:
        return {"status": "no_emails", "processed": 0}
    
    from app.agents.router_agent import classify_revert
    
    db = SessionLocal()
    results = []
    
    try:
        for email_data in emails:
            text = email_data["subject"] + " " + email_data["body"]
            
            classification = classify_revert(text)
            doc_type = classification.get("type", "investor")
            
            if doc_type == "investor":
                profile = extract_investor_profile(text)
                revert = ClientRevert(
                    sender=email_data["sender"],
                    subject=email_data["subject"],
                    body=email_data["body"],
                    type="investor",
                    status="pending",
                    cheque_size=profile.get("cheque_size"),
                    sector=profile.get("sector"),
                    intent=profile.get("intent"),
                    priority=profile.get("priority"),
                    next_step=profile.get("next_step"),
                    signals=json.dumps(profile.get("signals", []))
                )
                db.add(revert)
                db.commit()
                
                results.append({
                    "type": "investor",
                    "sender": email_data["sender"],
                    "id": revert.id,
                    "sector": profile.get("sector"),
                    "cheque_size": profile.get("cheque_size")
                })
                
            else:
                profile = extract_client_profile(text)
                revert = ClientRevert(
                    sender=email_data["sender"],
                    subject=email_data["subject"],
                    body=email_data["body"],
                    type="client",
                    status="pending",
                    company=profile.get("company"),
                    cheque_size=profile.get("cheque_size"),
                    sector=profile.get("sector"),
                    intent=profile.get("intent"),
                    urgency_level=profile.get("urgency"),
                    query_type=profile.get("query_type"),
                    next_step=profile.get("next_step"),
                    signals=json.dumps(profile.get("signals", []))
                )
                db.add(revert)
                db.commit()
                
                results.append({
                    "type": "client",
                    "sender": email_data["sender"],
                    "id": revert.id,
                    "company": profile.get("company"),
                    "sector": profile.get("sector")
                })
        
        print(f"[REVERT] Saved {len(results)} reverts to DB")
        
    except Exception as e:
        db.rollback()
        print(f"[REVERT ERROR] {str(e)}")
    finally:
        db.close()
    
    return {"status": "processed", "count": len(results), "results": results}


def get_pending_reverts(entity_type=None, limit=50):
    """
    Get unprocessed reverts from DB.
    entity_type: 'investor' | 'client' | None (all)
    """
    db = SessionLocal()
    try:
        if entity_type == "investor":
            items = db.query(ClientRevert).filter(
                ClientRevert.status == None
            ).limit(limit).all()
        elif entity_type == "client":
            items = db.query(ClientRevert).filter(
                ClientRevert.status == None
            ).limit(limit).all()
        else:
            inv = db.query(ClientRevert).limit(limit).all()
            cli = db.query(ClientRevert).limit(limit).all()
            items = inv + cli
        
        return items
    finally:
        db.close()


def trigger_document_analysis(revert_id, revert_type, document_path=None):
    """
    Trigger pitch deck analysis for a client revert.
    Called after client shows interest.
    """
    from app.main import process
    
    if revert_type != "client":
        return {"error": "Only client reverts need document analysis"}
    
    if not document_path:
        return {"error": "No document path provided"}
    
    return {"status": "triggered", "revert_id": revert_id}