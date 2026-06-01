import os
from datetime import datetime, timedelta, timezone
from app.db.session import SessionLocal
from app.db.models import ClientRevert
from app.services.email_sender import send_email
from app.agents.strategy_agent import generate_strategy


FOLLOW_UP_SCHEDULE = {
    "investor": {
        1: "initial",      # Day 1 - just got the inbound
        7: "first",       # Day 7 - first follow up
        17: "second",     # Day 17 - second follow up
        30: "archive"    # Day 30 - archive if no response
    },
    "client": {
        1: "initial",
        3: "first",
        5: "second",
        14: "archive"
    }
}


def get_follow_up_templates(entity_type: str, follow_up_num: str, profile: dict) -> dict:
    """Generate follow-up email content based on type and day."""
    
    if entity_type == "investor":
        templates = {
            "initial": {
                "subject": "Following up - {company}",
                "body": """Hi {name},

Thank you for reaching out regarding investment opportunities.

I've shared your interest with our portfolio companies. Would you like me to facilitate an introduction?

Please let me know your availability for a quick call.

Best regards,
LeadStream AI"""
            },
            "first": {
                "subject": "Following up - Day 7 - {company}",
                "body": """Hi {name},

Just following up on our earlier conversation about investment opportunities.

Have you had a chance to review the portfolio? I'm happy to schedule a call to discuss further.

Best regards,
LeadStream AI"""
            },
            "second": {
                "subject": "Final follow up - {company}",
                "body": """Hi {name},

Final follow up. We have several exciting opportunities in {sector} sector matching your {cheque_size} investment criteria.

Would love to connect this week if interested.

Best regards,
LeadStream AI"""
            }
        }
    else:  # client
        templates = {
            "initial": {
                "subject": "Thank you for your inquiry - {company}",
                "body": """Hi {name},

Thank you for reaching out to us.

Our team is reviewing your requirements. We'll get back to you shortly.

Best regards,
LeadStream AI"""
            },
            "first": {
                "subject": "Following up on your inquiry - Day 3",
                "body": """Hi {name},

Following up on your recent inquiry. We'd love to understand your needs better.

Would a demo help? Please let me know your availability.

Best regards,
LeadStream AI"""
            },
            "second": {
                "subject": "Last chance to connect - {company}",
                "body": """Hi {name},

Final follow up. Our {sector} solutions are available for immediate deployment.

Limited availability for personalized onboarding this month.

Best regards,
LeadStream AI"""
            }
        }
    
    template = templates.get(follow_up_num, templates["first"])
    
    subject = template["subject"].format(
        company=profile.get("company", "Company"),
        sector=profile.get("sector", "our")
    )
    
    body = template["body"].format(
        name=profile.get("name", "Team"),
        company=profile.get("company", "Company"),
        sector=profile.get("sector", "our"),
        cheque_size=profile.get("cheque_size", "investment")
    )
    
    return {"subject": subject, "body": body}


def get_entity_status(entity, entity_type: str) -> dict:
    """Extract status fields from entity."""
    if entity_type == "investor":
        return {
            "id": entity.id,
            "company": entity.company,
            "sender": entity.sender,
            "subject": entity.subject,
            "status": entity.status,
            "intent": entity.intent,
            "sector": entity.sector,
            "cheque_size": entity.cheque_size,
            "last_contacted": entity.processed_at,
            "timestamp": entity.timestamp
        }
    else:
        return {
            "id": entity.id,
            "company": entity.company,
            "sender": entity.sender,
            "subject": entity.subject,
            "status": entity.status,
            "intent": entity.intent,
            "sector": entity.sector,
            "cheque_size": entity.cheque_size,
            "last_contacted": entity.processed_at,
            "timestamp": entity.timestamp
        }


def calculate_days_since(entity, entity_type: str) -> int:
    """Calculate days since first contact."""
    if entity_type == "investor":
        timestamp = entity.timestamp
    else:
        timestamp = entity.timestamp
    
    if not timestamp:
        return 0
    
    # Convert to naive datetime for comparison
    if timestamp.tzinfo:
        # Make now naive
        now = datetime.now()
        ts = timestamp.replace(tzinfo=None)
        return abs((now - ts).days)
    else:
        return abs((datetime.now() - timestamp).days)


def get_follow_up_day(entity, entity_type: str) -> str:
    """Determine which follow-up stage we're at."""
    days = calculate_days_since(entity, entity_type)
    schedule = FOLLOW_UP_SCHEDULE[entity_type]
    
    if days <= 1:
        return "initial"
    elif days <= 7:
        return "first"
    elif days <= 17 if entity_type == "investor" else days <= 5:
        return "second"
    else:
        return "archive"


def process_investor_follow_ups():
    """Process follow-ups for all pending investors with auto-archive."""
    db = SessionLocal()
    processed = []
    archived = []
    
    try:
        investors = db.query(ClientRevert).filter(
            ClientRevert.status.in_(["pending", "matched", "no_match", "neutral"])
        ).all()
        
        for investor in investors:
            days = calculate_days_since(investor, "investor")
            status = investor.status
            
            # Auto-archive at day 30
            if days >= 30 and status in ["pending", "matched", "no_match", "neutral"]:
                investor.status = "archived"
                investor.archived_at = datetime.now()
                investor.archived_reason = "no_response_d30"
                db.commit()
                archived.append({
                    "id": investor.id,
                    "company": investor.company,
                    "reason": "no_response_d30"
                })
                continue
            
            # Skip if already replied
            if investor.intent in ["interested", "not_interested"]:
                continue
            
            # Check if we should send follow-up
            if days >= 7 and days < 17:
                follow_up = "first"
            elif days >= 17 and days < 30:
                follow_up = "second"
            else:
                continue
            
            # Get profile and send email
            profile = get_entity_status(investor, "investor")
            email_content = get_follow_up_templates("investor", follow_up, profile)
            
            # Send email
            try:
                send_email(
                    to=investor.sender,
                    subject=email_content["subject"],
                    body=email_content["body"]
                )
                investor.processed_at = datetime.now()
                investor.follow_up_count = (investor.follow_up_count or 0) + 1
                db.commit()
                
                processed.append({
                    "id": investor.id,
                    "company": investor.company,
                    "day": days,
                    "follow_up": follow_up
                })
            except Exception as e:
                print(f"[FOLLOWUP ERROR] Investor {investor.id}: {e}")
        
        return {
            "status": "completed",
            "processed": len(processed),
            "archived": len(archived),
            "results": processed,
            "archived_results": archived
        }
        
    finally:
        db.close()


def process_client_follow_ups():
    """Process follow-ups for all pending clients with auto-archive."""
    db = SessionLocal()
    processed = []
    archived = []
    
    try:
        clients = db.query(ClientRevert).filter(
            ClientRevert.status.in_(["pending", "interested", "matched", "neutral"])
        ).all()
        
        for client in clients:
            days = calculate_days_since(client, "client")
            
            # Auto-archive at day 14
            if days >= 14 and client.status in ["pending", "interested", "matched", "neutral"]:
                client.status = "archived"
                client.archived_at = datetime.now()
                client.archived_reason = "no_response_d14"
                db.commit()
                archived.append({
                    "id": client.id,
                    "company": client.company,
                    "reason": "no_response_d14"
                })
                continue
            
            # Skip if already replied
            if client.intent in ["interested", "not_interested"]:
                continue
            
            # Check if we should send follow-up
            if days >= 3 and days < 5:
                follow_up = "first"
            elif days >= 5 and days < 14:
                follow_up = "second"
            else:
                continue
            
            # Get profile and send email
            profile = get_entity_status(client, "client")
            email_content = get_follow_up_templates("client", follow_up, profile)
            
            # Send email
            try:
                send_email(
                    to=client.sender,
                    subject=email_content["subject"],
                    body=email_content["body"]
                )
                client.processed_at = datetime.now()
                client.follow_up_count = (client.follow_up_count or 0) + 1
                db.commit()
                
                processed.append({
                    "id": client.id,
                    "company": client.company,
                    "day": days,
                    "follow_up": follow_up
                })
            except Exception as e:
                print(f"[FOLLOWUP ERROR] Client {client.id}: {e}")
        
        return {
            "status": "completed",
            "processed": len(processed),
            "archived": len(archived),
            "results": processed,
            "archived_results": archived
        }
        
    finally:
        db.close()


def mark_responded(entity_type: str, entity_id: int, intent: str):
    """Mark entity as responded with their intent and trigger matching if interested."""
    db = SessionLocal()
    
    try:
        if entity_type == "investor":
            entity = db.query(ClientRevert).filter(ClientRevert.id == entity_id).first()
        else:
            entity = db.query(ClientRevert).filter(ClientRevert.id == entity_id).first()
        
        if not entity:
            return {"error": f"{entity_type} not found"}
        
        # Update status based on response
        if intent in ["interested", "positive", "eager"]:
            entity.status = "interested"
            entity.intent = "interested"
        elif intent in ["not_interested", "pass", "no"]:
            entity.status = "not_interested"
            entity.intent = "not_interested"
        else:
            entity.status = "neutral"
            entity.intent = "neutral"
        
        entity.processed_at = datetime.now()
        db.commit()
        
        matching_result = None
        
        # Auto-trigger matching if interested
        if intent in ["interested", "positive", "eager"]:
            from app.services.matcher import process_investor_match, process_client_match
            
            if entity_type == "investor":
                matching_result = process_investor_match(entity_id)
            else:
                matching_result = process_client_match(entity_id)
        
        return {
            "status": "updated",
            "entity_type": entity_type,
            "id": entity_id,
            "new_status": entity.status,
            "intent": entity.intent,
            "matching": matching_result
        }
        
    finally:
        db.close()


def get_follow_up_status(entity_type: str, entity_id: int) -> dict:
    """Get current follow-up status for an entity."""
    db = SessionLocal()
    
    try:
        if entity_type == "investor":
            entity = db.query(ClientRevert).filter(ClientRevert.id == entity_id).first()
        else:
            entity = db.query(ClientRevert).filter(ClientRevert.id == entity_id).first()
        
        if not entity:
            return {"error": f"{entity_type} not found"}
        
        days = calculate_days_since(entity, entity_type)
        follow_up_stage = get_follow_up_day(entity, entity_type)
        
        return {
            "id": entity.id,
            "company": entity.company,
            "days_since_contact": days,
            "current_stage": follow_up_stage,
            "status": entity.status,
            "intent": entity.intent,
            "last_contacted": entity.processed_at.isoformat() if entity.processed_at else None
        }
        
    finally:
        db.close()


def run_all_follow_ups():
    """Run both investor and client follow-ups."""
    investor_results = process_investor_follow_ups()
    client_results = process_client_follow_ups()
    
    return {
        "investors": investor_results,
        "clients": client_results,
        "total_processed": investor_results["processed"] + client_results["processed"]
    }