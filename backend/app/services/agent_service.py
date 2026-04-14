import os
import json
from anthropic import Anthropic
from app.services.fin_service import fetch_yfinance, fetch_sec_filing

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

TOOLS = [
    {
        "name": "get_stock_info",
        "description": "Get detailed financial information and company overview for a stock symbol from Yahoo Finance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g., AAPL"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_sec_filings",
        "description": "Fetch and search SEC filings (like 10-K) for a given stock symbol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol"},
                "form_type": {"type": "string", "description": "Form type, default is 10-K"}
            },
            "required": ["symbol"]
        }
    }
]

def process_agent_query(user_query: str, history=None):
    messages = history or []
    messages.append({"role": "user", "content": user_query})

    try:
        response = client.messages.create(
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
        if tool_name == "get_stock_info":
            docs = fetch_yfinance(tool_input["symbol"])
            result = "\n".join([d["text"] for d in docs[:3]]) # Summary
        elif tool_name == "get_sec_filings":
            docs = fetch_sec_filing(tool_input["symbol"], tool_input.get("form_type", "10-K"))
            result = "\n".join([d["text"] for d in docs[:3]]) # Summary

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

        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            tools=TOOLS,
            messages=messages
        )

    return response.content[0].text, messages
