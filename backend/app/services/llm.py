import os
import json
import urllib.request
from dotenv import load_dotenv

def call_claude(prompt: str):
    """
    ULTRA-PURE NATIVE CONNECT
    Uses zero external libraries (no httpx/anthropic) to avoid installation errors.
    """
    # Force reload environment from disk
    load_dotenv(override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        print("[LLM] CRITICAL: ANTHROPIC_API_KEY is empty in environment.")
        return "ERROR: Key missing."

    # Professional sanitization
    api_key = api_key.strip().replace('"', '').replace("'", "")
    
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    payload = {
        "model": "claude-3-5-sonnet-20240620",
        "max_tokens": 2048,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    print(f"[LLM] NATIVE TRACE: Connecting to Anthropic API...")
    print(f"      - x-api-key Signature: {api_key[:12]}...{api_key[-5:]}")
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=60.0) as response:
            res_body = response.read().decode("utf-8")
            result = json.loads(res_body)
            content = result.get("content", [{}])[0].get("text", "")
            print("[LLM] SUCCESS: Response received via native urllib.")
            return content
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"[LLM] API ERROR {e.code}: {error_body}")
        raise RuntimeError(f"LLM_API_ERROR: {e.code} - {error_body}")
    except Exception as e:
        print(f"[LLM] NATIVE CONNECTION ERROR: {str(e)}")
        raise RuntimeError(f"LLM_INTERNAL_ERROR: {str(e)}")
