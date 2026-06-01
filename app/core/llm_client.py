import os
import time
import threading
from dotenv import load_dotenv

load_dotenv()

from groq import Groq

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

_safe_client = None

LLM_CALL_SEMAPHORE = threading.Semaphore(2)

def get_safe_client():
    global _safe_client
    if _safe_client is None:
        groq_key = os.getenv("GROQ_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        
        # Primary: Groq with Llama, Fallback: Gemini
        if groq_key:
            print("[INFO] Using Groq (Llama) as primary LLM")
            _safe_client = SafeGroqClient(groq_key, gemini_key)
        elif gemini_key and GEMINI_AVAILABLE:
            print("[INFO] Using Gemini as fallback LLM")
            _safe_client = GeminiClient(gemini_key)
        else:
            raise Exception("GROQ_API_KEY or GEMINI_API_KEY must be set")
    return _safe_client


class GeminiClient:
    """Gemini API client as fallback"""
    
    def __init__(self, api_key):
        if not GEMINI_AVAILABLE:
            raise Exception("google-generativeai not installed. Run: pip install google-generativeai")
        
        genai.configure(api_key=api_key)
        self.client = genai
        self.default_model = "gemini-2.0-flash-exp"
        self.stats = {"total_calls": 0, "successful_calls": 0, "errors": 0}
    
    def get_stats(self):
        return self.stats
    
    def chat_completion(self, messages, model=None, temperature=0.1, max_retries=3, initial_delay=1, response_format=None, max_tokens=4096):
        model = model or self.default_model

        with LLM_CALL_SEMAPHORE:
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    
                    # Convert messages to Gemini format
                    gemini_messages = []
                    for msg in messages:
                        role = "model" if msg["role"] == "assistant" else "user"
                        gemini_messages.append({
                            "role": role,
                            "parts": [{"text": msg["content"]}]
                        })
                    
                    generation_config = {
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    }
                    
                    if response_format and response_format.get("type") == "json_object":
                        generation_config["response_mime_type"] = "application/json"
                    
                    result = self.client.generate_content(
                        model=model,
                        contents=gemini_messages,
                        generation_config=generation_config
                    )
                    
                    duration = time.time() - start_time
                    self.stats["successful_calls"] += 1
                    
                    content = result.text.strip()
                    print(f"[LLM SUCCESS] Model: {model} | Time: {duration:.2f}s | Chars: {len(content)}")
                    return content
                    
                except Exception as e:
                    self.stats["errors"] += 1
                    error_str = str(e).lower()
                    print(f"[LLM ERROR] Attempt {attempt+1} with {model}: {e}")
                    
                    if "rate limit" in error_str or "429" in error_str:
                        wait_time = initial_delay * (2 ** attempt)
                        print(f"[RETRY] Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise e
        
        raise Exception("Max retries reached for Gemini call")


class SafeGroqClient:
    def __init__(self, groq_api_key=None, gemini_api_key=None):
        self.groq_api_key = groq_api_key
        self.gemini_api_key = gemini_api_key
        
        if groq_api_key:
            self.client = Groq(api_key=groq_api_key, timeout=30.0)
        
        self.default_model = "llama-3.1-8b-instant"
        self.fallback_models = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]
        self.gemini_client = None
        self.stats = {"total_calls": 0, "successful_calls": 0, "errors": 0}

    def get_stats(self):
        return self.stats

    def chat_completion(self, messages, model=None, temperature=0.1, max_retries=2, initial_delay=0.5, response_format=None, max_tokens=None):
        model = model or self.default_model
        max_tokens = max_tokens or 2048

        # Try Groq models first
        if model == self.default_model:
            models_to_try = [self.default_model] + self.fallback_models
        else:
            models_to_try = [model]

        last_error = None
        groq_failed = False

        with LLM_CALL_SEMAPHORE:
            for current_model in models_to_try:
                for attempt in range(max_retries):
                    try:
                        start_time = time.time()
                        
                        # Calculate approximate input tokens
                        input_text = messages[0]["content"] if messages else ""
                        input_tokens = len(input_text) // 4
                        
                        res = self.client.chat.completions.create(
                            model=current_model,
                            messages=messages,
                            temperature=temperature,
                            response_format=response_format,
                            max_tokens=max_tokens
                        )
                        duration = time.time() - start_time
                        self.stats["successful_calls"] += 1
                        
                        content = res.choices[0].message.content.strip()
                        
                        # Log token usage
                        usage = getattr(res, 'usage', None)
                        if usage:
                            prompt_tokens = getattr(usage, 'prompt_tokens', input_tokens)
                            completion_tokens = getattr(usage, 'completion_tokens', len(content) // 4)
                            total_tokens = getattr(usage, 'total_tokens', prompt_tokens + completion_tokens)
                            print(f"[LLM SUCCESS] Model: {current_model} | Time: {duration:.2f}s | Input: {prompt_tokens} | Output: {completion_tokens} | Total: {total_tokens}")
                        else:
                            print(f"[LLM SUCCESS] Model: {current_model} | Time: {duration:.2f}s | Chars: {len(content)}")
                        
                        return content
                    except Exception as e:
                        self.stats["errors"] += 1
                        error_str = str(e).lower()
                        print(f"[LLM ERROR] Attempt {attempt+1} with {current_model}: {e}")
                        if "rate limit" in error_str or "429" in error_str:
                            wait_time = initial_delay * (2 ** attempt)
                            print(f"[RETRY] Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"[LLM FATAL] Non-retryable error: {e}")
                            last_error = e
                            groq_failed = True
                            break
                if groq_failed:
                    break
                print(f"[INFO] Trying fallback model: {current_model} failed, moving to next...")
        
        # If all Groq models failed and we have Gemini, try Gemini as final fallback
        if self.gemini_api_key and GEMINI_AVAILABLE:
            print(f"[INFO] All Groq models failed. Trying Gemini fallback...")
            try:
                if not self.gemini_client:
                    self.gemini_client = GeminiClient(self.gemini_api_key)
                
                # Convert messages format for Gemini
                return self.gemini_client.chat_completion(
                    messages, 
                    model="gemini-2.0-flash-exp",
                    temperature=temperature,
                    max_retries=max_retries,
                    initial_delay=initial_delay,
                    response_format=response_format,
                    max_tokens=max_tokens
                )
            except Exception as e:
                print(f"[LLM ERROR] Gemini fallback also failed: {e}")
        
        self.stats["errors"] += 1
        raise last_error or Exception("Max retries reached for LLM call due to rate limits.")

    def chat_completion_stream(self, messages, model=None, temperature=0.1, max_retries=3, initial_delay=1, response_format=None, max_tokens=4096, chunk_size: int = 30):
        """
        Simulated streaming - returns a generator that yields chunks of the response
        Note: Groq doesn't support true streaming, so we chunk the complete response
        """
        # First get the full response
        full_response = self.chat_completion(
            messages, model, temperature, max_retries, initial_delay, response_format, max_tokens
        )
        
        # Yield in chunks to simulate streaming
        for i in range(0, len(full_response), chunk_size):
            chunk = full_response[i:i + chunk_size]
            yield chunk
            time.sleep(0.02)  # Small delay between chunks for effect