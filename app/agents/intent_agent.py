import os, json
from app.core.llm_client import get_safe_client


def analyze_intent(email_text: str):
    client = get_safe_client()

    prompt = f"""
    Analyze the following investor/founder communication and determine the intent.
    
    Categories:
    - "interested": Positive engagement, meeting requests, or follow-up questions.
    - "neutral": Informational, auto-replies, or non-committal.
    - "not_interested": Explicit rejections or "pass" signals.

    Return ONLY a JSON object in this format:
    {{
      "intent": "category_name",
      "confidence": float (0.0 to 1.0),
      "signals": ["short", "actionable", "phrases"]
    }}

    Rules for Signals:
    - Max 3 signals.
    - Each signal must be 1-3 words max.
    - Focus on verbs like "schedule call", "send details", "interested".
    - DO NOT include full sentences or legal boilerplate.

    Text:
    {email_text}
    """

    content = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    try:
        if content.startswith("```json"):
            content = content[7:-3].strip()
        data = json.loads(content)
        
        # 🔥 Realistic Confidence Cap
        if "confidence" in data:
            data["confidence"] = min(float(data["confidence"]), 0.9)
            
        return data
    except:
        return {
            "intent": "neutral",
            "confidence": 0.5,
            "signals": ["analysis error"]
        }