import os, json
from app.core.llm_client import get_safe_client

def classify_revert(text: str):
    """
    Identifies if an incoming message is from an Investor or a Client.
    """
    client = get_safe_client()

    prompt = f"""
    You are a business triage agent. Classify the following communication.
    
    Categories:
    - "investor": Mentions of funding, pitch decks, cap tables, equity, IRR, series rounds, or partner meetings.
    - "client": Mentions of product pricing, demo requests, sales, support, partnerships, or business inquiries.

    Return ONLY a JSON object:
    {{
      "type": "investor" | "client",
      "reason": "short explanation"
    }}

    Text:
    {text[:2000]}
    """

    print(f"[DEBUG] Classifying text (first 500 chars): {text[:500]}...")
    content = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    try:

        # More robust JSON extraction
        if "{" in content and "}" in content:
            content = content[content.find("{"):content.rfind("}")+1]
        
        result = json.loads(content)
        print(f"[DEBUG] Classification Result: {result.get('type')} | Reason: {result.get('reason')}")
        return result
    except Exception as e:
        print(f"[WARNING] Classification parsing failed: {e}. Content: {content}")
        return {"type": "investor", "reason": "defaulting to investor (parsing error)"}
