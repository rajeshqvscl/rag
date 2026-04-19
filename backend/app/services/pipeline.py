from app.services.parser import extract_text
from app.services.retrieval import build_bm25, retrieve
from app.services.extraction import extract_structured
from app.services.rag_service import RAGService
import re
import os

def clean_text(text: str) -> str:
    """Professional data cleanup"""
    text = re.sub(r'[^\x20-\x7E\n\t]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def split_into_semantic_chunks(text: str, max_chars: int = 1500) -> list:
    blocks = text.split('\n\n')
    final_chunks = []
    current_chunk = ""
    for block in blocks:
        if len(current_chunk) + len(block) < max_chars:
            current_chunk += block + "\n\n"
        else:
            if current_chunk:
                final_chunks.append(current_chunk.strip())
            if len(block) > max_chars:
                for i in range(0, len(block), max_chars):
                    final_chunks.append(block[i:i+max_chars])
                current_chunk = ""
            else:
                current_chunk = block + "\n\n"
    if current_chunk:
        final_chunks.append(current_chunk.strip())
    return [c for c in final_chunks if len(c) > 20]

def miner_regex_metrics(context: str) -> dict:
    """
    PROFESSIONAL FALLBACK:
    Hard-coded Regex Miner to find metrics when LLM fails.
    """
    metrics = {
        "revenue": "Not found",
        "growth_rate": "Not found",
        "market_size": "Not found",
        "users": "Not found"
    }
    
    # Simple patterns for financial data
    revenue_patterns = [
        r'\$?(\d+\.?\d*[MBK])\s*(?:revenue|ARR|MRR|turnover)',
        r'(?:revenue|ARR|MRR)\s*(?::|=)?\s*\$?(\d+\.?\d*[MBK])'
    ]
    growth_patterns = [
        r'(\d+)%\s*(?:growth|YoY|MoM|CAGR)',
        r'(?:growth|YoY)\s*(?::|=)?\s*(\d+)%'
    ]
    market_patterns = [
        r'\$?(\d+\.?\d*[TMB])\s*(?:TAM|market size|SAM)',
        r'(?:TAM|market size)\s*(?::|=)?\s*\$?(\d+\.?\d*[TMB])'
    ]
    
    for p in revenue_patterns:
        match = re.search(p, context, re.IGNORECASE)
        if match:
            metrics["revenue"] = match.group(1)
            break
            
    for p in growth_patterns:
        match = re.search(p, context, re.IGNORECASE)
        if match:
            metrics["growth_rate"] = match.group(1) + "%"
            break

    for p in market_patterns:
        match = re.search(p, context, re.IGNORECASE)
        if match:
            metrics["market_size"] = match.group(1)
            break
            
    return metrics

def run_pipeline(file_path: str):
    print(f"\n--- [PIPELINE START: {os.path.basename(file_path)}] ---")
    
    # 1. Extraction Test
    try:
        raw_text = extract_text(file_path)
        print(f"[1/4] PARSE SUCCESS: {len(raw_text)} characters.")
    except Exception as e:
        raise RuntimeError(f"PARSING_FAILURE: {e}")

    text = clean_text(raw_text)
    
    # 2. Semantic Sandboxed Indexing
    sandbox_rag = RAGService(use_hnsw=False)
    chunks = split_into_semantic_chunks(text)
    docs = [{"text": chunk, "id": i} for i, chunk in enumerate(chunks)]
    sandbox_rag.add_documents(docs)
    
    # 3. Targeted Mining
    queries = {
        "finance": "Revenue, ARR, Profit",
        "growth": "Growth Rate, Traction",
        "market": "TAM, Market Size",
        "funding": "Raising, Valuation"
    }
    
    master_context = []
    for category, query in queries.items():
        hits = sandbox_rag.query(query, k=2)
        print(f"      - {category.upper()} Pass: Found {len(hits)} nodes.")
        for h in hits:
            if h['text'] not in master_context:
                master_context.append(h['text'])

    context_block = "\n\n---\n\n".join(master_context)

    # 4. Final Synthesis
    try:
        structured = extract_structured(context_block)
        
        # Check if the extraction actually worked
        if "error" in structured:
            print(f"[WARNING] LLM Primary Error. Activating Regex Miner...")
            regex_data = miner_regex_metrics(context_block)
            
            return {
                "status": "partial_success",
                "data": {
                    "summary": "AI ANALYST OFFLINE: (API Key Error).",
                    "brief_analysis": f"DATA MINED VIA REGEX:\nI have successfully retrieved {len(master_context)} data nodes. Since the AI Brain is offline, I have applied direct pattern matching to the text.",
                    "revenue": regex_data["revenue"],
                    "growth_rate": regex_data["growth_rate"],
                    "market_size": regex_data["market_size"],
                    "users": regex_data["users"]
                },
                "metadata": {"error": structured.get('error'), "fallback": "regex_miner"}
            }
            
        print(f"[4/4] LLM SYNTHESIS COMPLETE.")
        print("--- [PIPELINE SUCCESS] ---\n")
        
        return {
            "status": "success",
            "data": structured,
            "metadata": {"chars": len(text), "nodes": len(master_context)}
        }
        
    except Exception as e:
        print(f"[CRITICAL] EMERGENCY FALLBACK: {e}")
        regex_data = miner_regex_metrics(context_block)
        return {
            "status": "partial_success",
            "data": {
                "summary": "SYSTEM EMERGENCY FALLBACK.",
                "brief_analysis": "Retrieved data nodes remain safe in local memory. Full AI synthesis requires a valid API key.",
                "revenue": regex_data["revenue"],
                "growth_rate": regex_data["growth_rate"]
            },
            "metadata": {"error": str(e), "fallback": "emergency_regex"}
        }
