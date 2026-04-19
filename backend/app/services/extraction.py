import json
from app.services.llm import call_claude

PROMPT = """You are a world-class Venture Capital Principal at a top-tier firm (Sequoia/Accel style).
Analyze the provided pitch deck context and generate a high-conviction investment analysis.

Your response MUST be a single, valid JSON object with the following schema:
{
  "company_name": "Official entity name",
  "revenue": "Current ARR or Revenue with currency",
  "growth_rate": "YoY or MoM percentage",
  "users": "User count or Customer count",
  "market_size": "TAM value",
  "stage": "Pre-seed/Seed/Series A/etc",
  "summary": "2-sentence high-level business model summary",
  "revenue_data": [
    {"year": "2023", "revenue": 1000000},
    {"year": "2024", "revenue": 2500000}
  ],
  "brief_analysis": "### 🚀 The Moat\n(Bullet points on competitive advantage)\n\n### 🚩 The Friction\n(Bullet points on risks and red flags)\n\n### ⚖️ VC Verdict\n(Definitive investment recommendation)",
  "email_draft": "Post-analysis follow-up email to the founders"
}

RULES:
1. Return ONLY the JSON object. No markdown code blocks, no preamble.
2. If a metric is missing, use null.
3. For revenue_data, extract historical or projected yearly revenues found in the text.
4. Professional tone: Precise, data-driven, and critical. 
"""

def extract_structured(context: str):
    prompt = f"{PROMPT}\n\n[CONTEXT FROM PITCH DECK]:\n{context}"
    print("[EXTRACTION] Sending context to Claude for synthesis...")
    
    raw_res = call_claude(prompt)
    
    # Try to parse JSON from the response
    try:
        # Clean up possible markdown garbage
        json_str = raw_res.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        
        start = json_str.find('{')
        end = json_str.rfind('}') + 1
        if start != -1 and end != 0:
            extracted = json.loads(json_str[start:end])
            print(f"[EXTRACTION] Success: Extracted data for {extracted.get('company_name')}")
            return extracted
            
        print("[WARNING] LLM returned non-JSON text.")
        return {"error": "No JSON found in response", "raw": raw_res}
        
    except Exception as e:
        print(f"[ERROR] JSON Extraction failed: {e}")
        return {"error": f"JSON parse error: {str(e)}", "raw": raw_res}
