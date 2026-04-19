import os
from dotenv import load_dotenv

# Search for .env in current and parent directories
load_dotenv()

def get_anthropic_key():
    return os.getenv("ANTHROPIC_API_KEY")

def validate_env():
    key = get_anthropic_key()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    if not key.startswith("sk-ant-"):
        raise RuntimeError(f"ANTHROPIC_API_KEY invalid format: {key[:10]}...")

# For backward compatibility with services that import the constant
# We assign it here, but it's better to use get_anthropic_key()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
