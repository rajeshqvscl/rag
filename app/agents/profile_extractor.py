import json
from app.core.llm_client import get_safe_client

def safe_client():
    return get_safe_client()


def extract_investor_profile(email_text: str) -> dict:
    """
    Extract investor profile from email: cheque size, sector, intent, priority.
    """
    prompt = f"""
    Analyze this investor email and extract key information.

    Return ONLY a JSON object with these keys:
    1. "cheque_size": The investment amount (e.g., "seed", "series_a", "series_b", "growth", "large")
    2. "sector": Primary sector interest (e.g., "saas", "hr_tech", "fintech", "healthtech", "defense", "agritech", "ai")
    3. "intent": "interested", "neutral", or "not_interested"
    4. "priority": "high", "medium", or "low"
    5. "next_step": What they want to do next (e.g., "schedule call", "see deck", "join round")
    6. "signals": List of key signals from the email

    Email:
    {email_text[:2000]}
    """

    try:
        response = safe_client().chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        if "{" in response and "}" in response:
            response = response[response.find("{"):response.rfind("}")+1]
        
        return json.loads(response)
    except Exception as e:
        print(f"[PROFILE EXTRACT ERROR] {e}")
        return {
            "cheque_size": "seed",
            "sector": "general",
            "intent": "neutral",
            "priority": "medium",
            "next_step": "follow_up",
            "signals": []
        }


def extract_client_profile(email_text: str) -> dict:
    """
    Extract client profile from email: business type, needs, urgency.
    """
    prompt = f"""
    Analyze this client business inquiry email and extract key information.

    Return ONLY a JSON object with these keys:
    1. "company": Company name (or "Unknown")
    2. "cheque_size": Their budget/size (e.g., "seed", "series_a", "series_b", "growth", "large")
    3. "sector": Business sector (e.g., "saas", "hr_tech", "fintech", "healthtech", "defense", "agritech", "ai")
    4. "intent": "interested", "neutral" (wantsdemo), or "not_interested"
    5. "urgency": "high", "medium", or "low"
    6. "query_type": "Sales", "Partnership", "Support", "Pricing"
    7. "signals": List of key signals (e.g., "demo requested", "pricing asked", "NDA requested")
    8. "next_step": What they want next

    Email:
    {email_text[:2000]}
    """

    try:
        response = safe_client().chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        if "{" in response and "}" in response:
            response = response[response.find("{"):response.rfind("}")+1]
        
        return json.loads(response)
    except Exception as e:
        print(f"[CLIENT PROFILE ERROR] {e}")
        return {
            "company": "Unknown",
            "cheque_size": "seed",
            "sector": "general",
            "intent": "neutral",
            "urgency": "medium",
            "query_type": "Sales",
            "signals": [],
            "next_step": "follow_up"
        }