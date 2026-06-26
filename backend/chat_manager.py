"""
Chat Manager — Handles loading and saving chat history to JSON files.
"""
import os
import json
import uuid
from datetime import datetime
from typing import List, Optional

CHATS_DIR = os.path.join(os.path.dirname(__file__), "data", "chats")

class ChatManager:
    def __init__(self):
        os.makedirs(CHATS_DIR, exist_ok=True)
        self._chats = {} # chat_id -> chat_data
        self._load_all_chats()

    def _load_all_chats(self):
        for filename in os.listdir(CHATS_DIR):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(CHATS_DIR, filename), "r", encoding="utf-8") as f:
                        chat_data = json.load(f)
                        self._chats[chat_data["id"]] = chat_data
                except Exception as e:
                    print(f"Error loading chat {filename}: {e}")

    def _save_chat(self, chat_id: str):
        if chat_id not in self._chats:
            return
        
        filepath = os.path.join(CHATS_DIR, f"{chat_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self._chats[chat_id], f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving chat {chat_id}: {e}")

    def create_chat(self, title: str = "New Chat") -> dict:
        chat_id = str(uuid.uuid4())
        chat = {
            "id": chat_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "messages": [],
        }
        self._chats[chat_id] = chat
        self._save_chat(chat_id)
        return chat

    def get_chat(self, chat_id: str) -> Optional[dict]:
        return self._chats.get(chat_id)

    def list_chats(self) -> List[dict]:
        chats = []
        for chat_id, data in self._chats.items():
            chats.append({
                "id": data["id"], 
                "title": data["title"], 
                "created_at": data["created_at"], 
                "updated_at": data["updated_at"], 
                "message_count": len(data.get("messages", []))
            })
        chats.sort(key=lambda x: x["updated_at"], reverse=True)
        return chats

    def add_message(self, chat_id: str, role: str, content: str, metadata: Optional[dict] = None) -> dict:
        chat = self.get_chat(chat_id)
        if not chat:
            chat = self.create_chat()
            chat_id = chat["id"]
        
        msg = {
            "id": str(uuid.uuid4()), 
            "role": role, 
            "content": content, 
            "timestamp": datetime.now().isoformat(), 
            "metadata": metadata or {}
        }
        chat["messages"].append(msg)
        chat["updated_at"] = datetime.now().isoformat()
        
        # Auto-title from first user message
        if role == "user" and len([m for m in chat["messages"] if m["role"] == "user"]) == 1:
            chat["title"] = content[:60] + ("..." if len(content) > 60 else "")
            
        self._save_chat(chat_id)
        return msg

    def delete_chat(self, chat_id: str) -> bool:
        if chat_id in self._chats:
            del self._chats[chat_id]
            filepath = os.path.join(CHATS_DIR, f"{chat_id}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        return False

    def update_title(self, chat_id: str, title: str) -> bool:
        chat = self.get_chat(chat_id)
        if not chat: return False
        chat["title"] = title
        chat["updated_at"] = datetime.now().isoformat()
        self._save_chat(chat_id)
        return True
