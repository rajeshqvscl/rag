import os, json
from app.core.llm_client import get_safe_client
from app.rag.retriever import retrieve

def generate_draft(email, agent, use_rag=True, namespace=None):
    client = get_safe_client()
    context = retrieve(email, namespace=namespace) if use_rag else []
    context_text = "\n".join(context)

    prompt = f"""
Use ONLY context.

Context:
{context_text}

Email:
{email}

Return JSON:
{{"subject":"...","body":"...","context_used":{context}}}
"""

    content = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )

    try:
        return json.loads(content)
    except:
        return {"subject":"Re","body":"Fallback"}