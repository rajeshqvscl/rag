"""Test Claude API connectivity"""
from dotenv import load_dotenv
load_dotenv()
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
model = os.getenv('CLAUDE_MODEL', 'claude-3-5-sonnet-latest')
print(f'Testing model: {model}')

try:
    r = client.messages.create(
        model=model,
        max_tokens=50,
        messages=[{'role': 'user', 'content': 'Say hello'}]
    )
    print(f'Success! Response: {r.content[0].text[:50]}')
except Exception as e:
    print(f'Error: {e}')
