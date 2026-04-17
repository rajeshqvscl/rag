import os
import json
from anthropic import Anthropic

# Lazy load client to reduce startup memory
_client = None
MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        _client = Anthropic(api_key=api_key)
    return _client

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
    messages = history or []
    messages.append({"role": "user", "content": user_query})

    try:
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=2000,
            tools=TOOLS,
            messages=messages
        )
    except Exception as e:
        # Fallback when Claude API is unavailable
        fallback_response = f"I'm currently unable to access my advanced AI capabilities due to API limitations. However, I can help you with basic financial information.\n\nYour query: {user_query}\n\nPlease try:\n1. Using the main search function for existing data\n2. Ingesting financial data first with the /fin/ingest endpoint\n3. Contacting support if this issue persists"
        
        messages.append({"role": "assistant", "content": fallback_response})
        return fallback_response, messages

    while response.stop_reason == "tool_use":
        tool_use = next(block for block in response.content if block.type == "tool_use")
        tool_name = tool_use.name
        tool_input = tool_use.input
        tool_use_id = tool_use.id

        print(f"Agent using tool: {tool_name} with {tool_input}")

        # Execute Tool
        result = "Tool execution failed."
        if tool_name == "search_knowledge_base":
            # Search internal knowledge base
            try:
                from app.services.pgvector_memory_service import pgvector_memory_service
                memories = pgvector_memory_service.search_similar(
                    query=tool_input.get("query", ""),
                    k=5
                )
                if memories:
                    result = "Found relevant information:\n" + "\n".join([
                        f"- {m.get('text', '')[:200]}..." for m in memories[:3]
                    ])
                else:
                    result = "No relevant information found in knowledge base."
            except Exception as e:
                result = f"Knowledge base search error: {str(e)}"
                
        elif tool_name == "get_email_replies":
            # Get email replies
            try:
                from app.config.database import get_db
                from app.models.database import EmailReply
                db = next(get_db())
                
                query = db.query(EmailReply)
                if tool_input.get("company"):
                    query = query.filter(EmailReply.company.ilike(f"%{tool_input['company']}%"))
                if tool_input.get("sender_type"):
                    query = query.filter(EmailReply.sender_type == tool_input["sender_type"])
                if tool_input.get("intent_status"):
                    query = query.filter(EmailReply.intent_status == tool_input["intent_status"])
                
                replies = query.order_by(EmailReply.received_at.desc()).limit(5).all()
                
                if replies:
                    result = f"Found {len(replies)} email replies:\n" + "\n".join([
                        f"- From {r.sender_name or r.sender_email}: {r.intent_status} ({r.sender_type})"
                        for r in replies
                    ])
                else:
                    result = "No email replies found matching the criteria."
                    
                db.close()
            except Exception as e:
                result = f"Email search error: {str(e)}"

        # Continue Conversation
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result
                }
            ]
        })

        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=2000,
            tools=TOOLS,
            messages=messages
        )

    return response.content[0].text, messages
