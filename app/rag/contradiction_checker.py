"""
Contradiction Detection - Find conflicting claims across documents
"""

from typing import List, Dict, Any, Tuple
from .retriever import retrieve_with_sources
from app.core.llm_client import get_safe_client


def extract_claims(text: str) -> List[str]:
    """Extract key claims from text using simple sentence extraction"""
    import re
    
    # Split by sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    claims = []
    for sentence in sentences:
        sentence = sentence.strip()
        # Filter to likely claims (contains numbers, metrics, or key terms)
        if any(kw in sentence.lower() for kw in ["revenue", "growth", "users", "margin", "profit", "percentage", "%", "₹", "$"]):
            if len(sentence) > 20 and len(sentence) < 500:
                claims.append(sentence)
    
    return claims[:10]  # Limit to 10 claims per document


def compare_claims(claims_a: List[str], claims_b: List[str], company_a: str, company_b: str) -> List[Dict]:
    """Compare claims between two documents to find contradictions"""
    client = get_safe_client()
    
    contradictions = []
    
    for claim_a in claims_a[:5]:  # Limit comparisons
        for claim_b in claims_b[:5]:
            # Skip if different companies
            if company_a.lower() in claim_b.lower() or company_b.lower() in claim_a.lower():
                continue
            
            prompt = f"""Compare these two statements and determine if they contain contradictory information.

Statement 1 ({company_a}): {claim_a}
Statement 2 ({company_b}): {claim_b}

Are these contradictory? Reply with ONLY one word: YES or NO
If YES, explain the contradiction in 1 sentence."""

            try:
                response = client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=100
                )
                
                if "YES" in response.upper():
                    contradictions.append({
                        "claim_a": claim_a[:200],
                        "claim_b": claim_b[:200],
                        "company_a": company_a,
                        "company_b": company_b,
                        "explanation": response,
                        "confidence": 0.8
                    })
            except Exception as e:
                print(f"[CONTRADICTION CHECK ERROR] {e}")
    
    return contradictions


def check_contradictions(doc_ids: List[str], companies: List[str] = None, namespaces: List[str] = None) -> Dict[str, Any]:
    """
    Check for contradictions across multiple documents
    
    Args:
        doc_ids: List of document IDs
        companies: Optional company names
        namespaces: Optional list of namespaces (one per doc_id)
    
    Returns:
        {conflicts: [...], summary: str}
    """
    if companies is None:
        companies = [f"Company {i+1}" for i in range(len(doc_ids))]
    
    # Extract claims from each document
    all_claims = {}
    
    for idx, doc_id in enumerate(doc_ids):
        ns = namespaces[idx] if namespaces and idx < len(namespaces) else (companies[idx].lower().replace(" ", "_") if companies[idx] else None)
        result = retrieve_with_sources(f"key metrics {companies[idx]}", namespace=ns, doc_id=doc_id, top_k=3)
        claims = []
        for chunk in result["chunks"]:
            claims.extend(extract_claims(chunk))
        all_claims[companies[idx]] = claims
    
    # Compare all pairs
    all_contradictions = []
    company_list = list(all_claims.keys())
    
    for i in range(len(company_list)):
        for j in range(i + 1, len(company_list)):
            company_a = company_list[i]
            company_b = company_list[j]
            
            contradictions = compare_claims(
                all_claims[company_a],
                all_claims[company_b],
                company_a,
                company_b
            )
            all_contradictions.extend(contradictions)
    
    return {
        "conflicts": all_contradictions,
        "document_pairs_checked": len(company_list) * (len(company_list) - 1) // 2,
        "total_claims_checked": sum(len(c) for c in all_claims.values()),
        "conflicts_found": len(all_contradictions),
        "summary": f"Found {len(all_contradictions)} potential contradictions across {len(doc_ids)} documents"
    }


def check_single_document(doc_id: str, query: str = "key metrics", namespace: str = None) -> Dict[str, Any]:
    """Check a single document for internal inconsistencies"""
    result = retrieve_with_sources(query, namespace=namespace, doc_id=doc_id, top_k=5)
    
    # Extract claims
    all_text = " ".join(result["chunks"])
    claims = extract_claims(all_text)
    
    if len(claims) < 2:
        return {
            "inconsistencies": [],
            "message": "Not enough claims to check for inconsistencies"
        }
    
    # Compare claims within same document
    client = get_safe_client()
    inconsistencies = []
    
    for i in range(min(len(claims), 5)):
        for j in range(i + 1, min(len(claims), 5)):
            prompt = f"""These two statements are from the same document. 
Do they contradict each other?

Statement 1: {claims[i]}
Statement 2: {claims[j]}

Reply with YES or NO. If YES, explain the contradiction."""

            try:
                response = client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=100
                )
                
                if "YES" in response.upper():
                    inconsistencies.append({
                        "claim_1": claims[i][:150],
                        "claim_2": claims[j][:150],
                        "explanation": response
                    })
            except:
                pass
    
    return {
        "inconsistencies": inconsistencies,
        "total_claims": len(claims),
        "checked_pairs": min(len(claims), 5) * (min(len(claims), 5) - 1) // 2
    }