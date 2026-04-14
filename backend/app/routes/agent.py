from fastapi import APIRouter, Query
from app.services.agent_service import process_agent_query
from app.services.chat_memory_service import chat_memory

router = APIRouter(prefix="/agent", tags=["agent"])

@router.get("/chat")
def chat_with_agent(
    q: str = Query(..., description="User message"),
    session_id: str = Query("default", description="Session ID for chat memory")
):
    history = chat_memory.get_history(session_id)
    # Convert history to Anthropic format if necessary
    # (Anthropic messages are usually [{'role': 'user', 'content': '...'}, ...])
    # Our history currently stores it like that, but we need to ensure alternating.
    
    anthropic_history = []
    for msg in history:
        anthropic_history.append({"role": msg["role"], "content": msg["content"]})

    answer, new_history = process_agent_query(q, history=anthropic_history)
    
    # Update our memory (process_agent_query returns full messages, we just want the new ones)
    for msg in new_history[len(anthropic_history):]:
        if msg["role"] in ["user", "assistant"] and isinstance(msg["content"], str):
             chat_memory.add_message(session_id, msg["role"], msg["content"])
        elif msg["role"] == "assistant" and isinstance(msg["content"], list):
            # Extract text from content blocks
            text = "".join([b.text for b in msg["content"] if hasattr(b, 'text')])
            if text:
                chat_memory.add_message(session_id, "assistant", text)

    return {"answer": answer, "session_id": session_id}
