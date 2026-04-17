import os
import json

# Claude is disabled for agent queries - only used for classification, identification, and email drafts
# Agent now uses local fallback only
def _get_client():
    raise NotImplementedError("Claude is disabled for agent queries. Use local fallback only.")

# Tools available to the agent (market data tools removed)
TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Search the internal knowledge base for documents, pitch decks, and previous analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "context": {"type": "string", "description": "Optional context filter (company, deal, market, financial, general)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_email_replies",
        "description": "Get email replies and their classification status for a company or investor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company name to filter by"},
                "sender_type": {"type": "string", "description": "Filter by sender type: investor, client, unknown"},
                "intent_status": {"type": "string", "description": "Filter by intent: interested, not_interested, pending"}
            }
        }
    }
]

def process_agent_query(user_query: str, history=None):
    """
    Process agent query using local tools only.
    Claude is disabled for agent queries - only used for classification, identification, and email drafts.
    """
    messages = history or []
    messages.append({"role": "user", "content": user_query})

    # Direct fallback response since Claude is disabled
    fallback_response = f"Claude AI is currently configured for classification, identification, and email draft generation only. For general queries, please use the main search function or specific endpoints.\n\nYour query: {user_query}\n\nAvailable features:\n1. Document search and analysis\n2. Email classification and identification\n3. Email draft generation\n4. Pitch deck analysis\n\nPlease use the appropriate feature from the UI."
    
    messages.append({"role": "assistant", "content": fallback_response})
    return fallback_response, messages