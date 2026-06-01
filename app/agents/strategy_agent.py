import os, json
from app.core.llm_client import get_safe_client

def generate_strategy(intent_data, email_text):
    """
    Suggests a specific follow-up strategy based on intent and content.
    """
    client = get_safe_client()

    intent = intent_data.get("intent", "neutral")
    signals = ", ".join(intent_data.get("signals", []))

    prompt = f"""
    You are a venture capital deal-flow strategist.
    Based on the detected intent and communication signals, suggest the BEST next step.

    Intent: {intent}
    Signals: {signals}
    Full Communication: {email_text}

    Logic:
    - If meeting requested -> "Schedule call within 24-48 hours"
    - If data/deck requested -> "Send data room / deck"
    - If vague/neutral -> "Follow up in 10–14 days with additional traction updates"
    - If pass -> "Archive lead & maintain network"

    Return ONLY a JSON object:
    {{
      "next_step": "short action sentence",
      "priority": "high|medium|low",
      "reason": "short explanation of why this step was chosen"
    }}
    """

    content = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    try:
        if content.startswith("```json"):
            content = content[7:-3].strip()
        return json.loads(content)
    except:
        return {
            "next_step": "Manual Review",
            "priority": "medium",
            "reason": "System was unable to determine strategy automatically."
        }