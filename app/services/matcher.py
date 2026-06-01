from app.db.session import SessionLocal
from app.db.models import ClientRevert

import asyncio


CHEQUE_SIZE_RANGES = {
    "seed": (500000, 5000000),
    "series_a": (5000000, 20000000),
    "series_b": (20000000, 100000000),
    "growth": (100000000, 500000000),
    "large": (500000000, float("inf"))
}

SECTOR_KEYWORDS = {
    "hr_tech": ["hiring", "recruitment", "hr", "payroll", "staffing"],
    "saas": ["saas", "software", "cloud", "subscription"],
    "fintech": ["finance", "payments", "banking", "insurance"],
    "healthtech": ["health", "medical", "diagnostic", "clinical", "lab"],
    "defense": ["defense", "military", "rf", "antenna"],
    "agritech": ["agri", "farm", "crop", "irrigation"],
    "ai": ["ai", "ml", "machine learning", "automation"]
}


def parse_cheque_size(cheque_text: str) -> str:
    """
    Convert cheque size text to category.
    """
    text = cheque_text.lower()
    
    if any(x in text for x in ["50l", "5M", "seed"]):
        return "seed"
    if any(x in text for x in ["1cr", "10M", "series a"]):
        return "series_a"
    if any(x in text for x in ["5cr", "50M", "series b"]):
        return "series_b"
    if any(x in text for x in ["10cr", "100M", "growth"]):
        return "growth"
    if any(x in text for x in ["50cr", "500M", "large"]):
        return "large"
    
    return "seed"


def detect_sector(text: str) -> list:
    """
    Detect sectors from text based on keywords.
    """
    text = text.lower()
    detected = []
    
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(k in text for k in keywords):
            detected.append(sector)
    
    return detected if detected else ["general"]


def extract_client_profile(client_revert) -> dict:
    """
    Extract matching profile from client revert.
    """
    return {
        "id": client_revert.id,
        "company": client_revert.company,
        "sector": client_revert.sector or "general",
        "cheque_size": parse_cheque_size(client_revert.cheque_size or ""),
        "score": client_revert.score or 0,
        "intent": client_revert.intent
    }


def extract_investor_profile(investor_revert) -> dict:
    """
    Extract matching profile from investor revert.
    """
    return {
        "id": investor_revert.id,
        "company": investor_revert.company,
        "sector": investor_revert.sector or "general",
        "cheque_size": parse_cheque_size(investor_revert.cheque_size or ""),
        "intent": investor_revert.intent,
        "priority": investor_revert.priority
    }


def match_score(client_profile: dict, investor_profile: dict) -> float:
    """
    Calculate match score between client and investor.
    """
    score = 0
    
    if client_profile["sector"] == investor_profile["sector"]:
        score += 50
    
    client_range = CHEQUE_SIZE_RANGES.get(client_profile["cheque_size"], (0, float("inf")))
    investor_range = CHEQUE_SIZE_RANGES.get(investor_profile["cheque_size"], (0, float("inf")))
    
    if investor_range[0] <= client_range[1] and investor_range[1] >= client_range[0]:
        score += 30
    
    if client_profile.get("score", 0) >= 70:
        score += 20
    
    return min(score, 100)


def get_matches_for_investor(investor_id: int, min_score: int = 50):
    """
    Find matching clients for an investor.
    """
    db = SessionLocal()
    try:
        investor = db.query(ClientRevert).filter(ClientRevert.id == investor_id).first()
        if not investor:
            return []
        
        investor_profile = extract_investor_profile(investor)
        
        # Query ALL clients (not just specific statuses)
        clients = db.query(ClientRevert).all()
        
        matches = []
        for client in clients:
            # Skip if same entity
            if client.id == investor_id:
                continue
            
            client_profile = extract_client_profile(client)
            match_s = match_score(client_profile, investor_profile)
            
            if match_s >= min_score:
                matches.append({
                    "client": client_profile,
                    "match_score": match_s
                })
        
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches
        
    finally:
        db.close()


def get_matches_for_client(client_id: int, min_score: int = 50):
    """
    Find matching investors for a client.
    """
    db = SessionLocal()
    try:
        client = db.query(ClientRevert).filter(ClientRevert.id == client_id).first()
        if not client:
            return []
        
        client_profile = extract_client_profile(client)
        
        # Query ALL investors (not just specific statuses)
        investors = db.query(ClientRevert).all()
        
        matches = []
        for investor in investors:
            # Skip if same entity
            if investor.id == client_id:
                continue
            
            investor_profile = extract_investor_profile(investor)
            match_s = match_score(client_profile, investor_profile)
            
            if match_s >= min_score:
                matches.append({
                    "investor": investor_profile,
                    "match_score": match_s
                })
        
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches
        
    finally:
        db.close()


def process_client_match(client_id: int, min_score: int = 50):
    """
    Full match processing for a client - find matching investors.
    """
    from app.agents.strategy_agent import generate_strategy
    
    matches = get_matches_for_client(client_id, min_score)
    
    db = SessionLocal()
    try:
        client = db.query(ClientRevert).filter(ClientRevert.id == client_id).first()
        if not client:
            return {"error": "Client not found"}
        
        if not matches:
            client.status = "no_match"
            db.commit()
            return {"status": "no_match", "client_id": client_id}
        
        client.matched_investors = matches
        client.status = "matched"
        db.commit()
        
        intent_obj = {"intent": "neutral", "confidence": 0.8, "signals": []}
        strategy = generate_strategy(intent_obj, f"Matched with {len(matches)} investors")
        
        return {
            "status": "matched",
            "client_id": client_id,
            "matches": matches,
            "strategy": strategy
        }
        
    finally:
        db.close()


def process_investor_match(investor_id: int, min_score: int = 50):
    """
    Full match processing for an investor.
    """
    from app.agents.strategy_agent import generate_strategy
    
    matches = get_matches_for_investor(investor_id, min_score)
    
    db = SessionLocal()
    try:
        investor = db.query(ClientRevert).filter(ClientRevert.id == investor_id).first()
        if not investor:
            return {"error": "Investor not found"}
        
        if not matches:
            investor.status = "no_match"
            db.commit()
            return {"status": "no_match", "investor_id": investor_id}
        
        investor.status = "matched"
        db.commit()
        
        intent_obj = {"intent": "neutral", "confidence": 0.8, "signals": []}
        strategy = generate_strategy(intent_obj, f"Matched with {len(matches)} clients")
        
        return {
            "status": "matched",
            "investor_id": investor_id,
            "matches": matches,
            "strategy": strategy
        }
        
    finally:
        db.close()


def trigger_client_analysis(client_id: int, document_path: str):
    """
    Trigger pitch deck analysis for a client who showed interest.
    """
    from app.main import process, run_pipeline_background
    
    db = SessionLocal()
    try:
        client = db.query(ClientRevert).filter(ClientRevert.id == client_id).first()
        if not client:
            return {"error": "Client not found"}
        
        if client.intent not in ["interested", "positive", "eager"]:
            return {"error": "Client not interested - cannot analyze"}
        
        client.status = "analyzing"
        client.document_path = document_path
        db.commit()
        
        return {
            "status": "analyzing",
            "client_id": client_id,
            "document_path": document_path
        }
        
    finally:
        db.close()


def run_matching_pipeline():
    """
    Run full matching pipeline for both investors and clients (bi-directional).
    """
    db = SessionLocal()
    try:
        # Investors → Clients
        pending_investors = db.query(ClientRevert).filter(
            ClientRevert.status == "pending"
        ).all()
        
        investor_results = []
        for investor in pending_investors:
            result = process_investor_match(investor.id)
            investor_results.append(result)
        
        # Clients → Investors (bi-directional)
        pending_clients = db.query(ClientRevert).filter(
            ClientRevert.status.in_(["interested", "pending"])
        ).all()
        
        client_results = []
        for client in pending_clients:
            result = process_client_match(client.id)
            client_results.append(result)
        
        return {
            "status": "completed",
            "investor_matches": len(investor_results),
            "client_matches": len(client_results),
            "results": {
                "investors": investor_results,
                "clients": client_results
            }
        }
        
    finally:
        db.close()