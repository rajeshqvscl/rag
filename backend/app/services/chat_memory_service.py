import json
import os
from typing import List, Dict

MEMORY_FILE = "app/data/chat_memory.json"

class ChatMemoryService:
    def __init__(self):
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        if not os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "w") as f:
                json.dump({}, f)

    def add_message(self, session_id: str, role: str, content: str):
        with open(MEMORY_FILE, "r") as f:
            all_memory = json.load(f)
        
        if session_id not in all_memory:
            all_memory[session_id] = []
        
        all_memory[session_id].append({"role": role, "content": content})
        
        # Keep only last 20 messages
        all_memory[session_id] = all_memory[session_id][-20:]
        
        with open(MEMORY_FILE, "w") as f:
            json.dump(all_memory, f, indent=2)

    def get_history(self, session_id: str) -> List[Dict]:
        if not os.path.exists(MEMORY_FILE):
            return []
        with open(MEMORY_FILE, "r") as f:
            all_memory = json.load(f)
        return all_memory.get(session_id, [])

    def clear_history(self, session_id: str):
        with open(MEMORY_FILE, "r") as f:
            all_memory = json.load(f)
        if session_id in all_memory:
            del all_memory[session_id]
            with open(MEMORY_FILE, "w") as f:
                json.dump(all_memory, f, indent=2)

chat_memory = ChatMemoryService()
