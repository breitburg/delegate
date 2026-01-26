import json
import os


class Context:
    def __init__(self):
        self._messages: list[dict] = []
        self._session_file = os.path.join(os.getcwd(), ".delegate-session.json")
        self._load()

    def _load(self):
        """Load messages from the session file if it exists."""
        if os.path.exists(self._session_file):
            try:
                with open(self._session_file, "r", encoding="utf-8") as f:
                    self._messages = json.load(f)
            except (json.JSONDecodeError, IOError):
                # If file is corrupted or can't be read, start fresh
                self._messages = []

    def _save(self):
        """Save messages to the session file."""
        try:
            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(self._messages, f, indent=2)
        except IOError:
            # Silently fail if we can't save (e.g., permission issues)
            pass

    def add(self, message: dict):
        self._messages.append(message)
        self._save()

    def add_tool_call(self, name: str, args: dict, result: str):
        self._messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{name}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": args,
                        },
                    }
                ],
            }
        )
        self._messages.append(
            {"role": "tool", "tool_call_id": f"call_{name}", "content": result}
        )
        self._save()

    def get_messages(self) -> list[dict]:
        return self._messages

    def clear(self):
        """Clear all messages."""
        self._messages = []
        self._save()
