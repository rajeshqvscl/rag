import json
from app.core.llm_client import get_safe_client

def safe_client():
    return get_safe_client()

def triage_document(text):
    """
    Consolidated triage: Classification + Intent + Company Extraction in 1 call.
    """
    prompt = f"""
    Analyze the following document text and provide a structured JSON triage report.
    
    RETURN ONLY A JSON OBJECT WITH THESE KEYS:
    1. "type": "investor" (mentions funding, decks, cap table) or "client" (pricing, demo, sales).
    2. "intent": "interested", "neutral", or "not_interested".
    3. "signals": A list of key signals (e.g., "schedule call", "NDA request").
    4. "company": The company's LEGAL/BRAND name (e.g. "Unnati", "Google"). NOT a tagline or positioning statement like "Building Naukri 2.0" or "AI Copilot for recruiters". If unsure, return "Unknown".
    5. "reason": A short explanation of the classification.

    Text:
    {text[:4000]}
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
        print(f"[ERROR] Triage failed: {e}")
        return {
            "type": "investor",
            "intent": "neutral",
            "signals": [],
            "company": "Unknown",
            "reason": "fallback due to error"
        }
