import json


class Context:
    def __init__(self):
        self._messages: list[dict] = []

    def add(self, message: dict):
        self._messages.append(message)

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
                            "arguments": json.dumps(args),
                        },
                    }
                ],
            }
        )
        self._messages.append(
            {"role": "tool", "tool_call_id": f"call_{name}", "content": result}
        )

    def get_messages(self) -> list[dict]:
        return self._messages

    def clear(self):
        """Clear all messages except the system prompt."""
        # Keep only the system message (first message)
        if self._messages and self._messages[0].get("role") == "system":
            system_msg = self._messages[0]
            self._messages = [system_msg]
        else:
            self._messages = []
