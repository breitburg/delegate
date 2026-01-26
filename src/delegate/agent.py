import json
import os
import platform
from datetime import date
from openai import OpenAI
from typing import cast
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from .context import Context
from .tools import registry
from .ui import ui, Mode
from pyfiglet import Figlet


class Agent:
    def __init__(
        self,
        model: str = "glm-4.7:cloud",
        temperature: float = 0.7,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.context = Context()
        self._init()

    def _init(self):
        # Get the package directory and find the system prompt
        package_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(package_dir, "..", "..", "prompts", "system.md")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_content = f.read()

        # Replace placeholders with actual values
        today = date.today()
        system_content = system_content.format(
            platform=platform.system(),
            pwd=os.getcwd(),
            date=today.strftime("%A, %B %d, %Y"),
        )

        self.context.add({"role": "system", "content": system_content})

    def run(self):
        f = Figlet(font="small", width=80)
        ui.print_system(f.renderText("Delegate"))
        while True:
            try:
                user_input = ui.get_user_input()

                if not user_input:
                    continue

                if user_input == "/quit":
                    ui.print_system("Goodbye!")
                    break

                if user_input == "/auto":
                    ui.set_mode(Mode.AUTO)
                    continue

                if user_input == "/manual":
                    ui.set_mode(Mode.MANUAL)
                    continue

                if user_input == "/clear":
                    self.context.clear()
                    ui.print_system("Conversation context cleared")
                    continue

                self._process_message(user_input)

            except (KeyboardInterrupt, EOFError):
                ui.print_system("\nGoodbye!")
                break

    def _process_message(self, message: str):
        self.context.add({"role": "user", "content": message})
        self._run_agent_loop()

    def _execute_tool(self, name: str, args: dict) -> str:
        tool_func = registry.get_tool(name)
        if not tool_func:
            return f"Error: Tool '{name}' not found"
        return tool_func(**args)

    def _run_agent_loop(self):
        while True:
            ui.print_assistant_thinking()

            try:
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=cast(
                        list[ChatCompletionMessageParam], self.context.get_messages()
                    ),  # type: ignore
                    temperature=self.temperature,
                    tools=cast(
                        list[ChatCompletionToolParam], registry.get_definitions()
                    ),  # type: ignore
                    stream=True,
                    timeout=60,
                )

                content = ""
                tool_calls_data = []

                for chunk in stream:
                    delta = chunk.choices[0].delta

                    if delta.content:
                        content += delta.content
                        ui.update_assistant_content(content)

                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            tool_calls_data.append(
                                {
                                    "id": tool_call.id,
                                    "type": tool_call.type,
                                    "function": {
                                        "name": tool_call.function.name
                                        if tool_call.function
                                        else None,
                                        "arguments": tool_call.function.arguments
                                        if tool_call.function
                                        else None,
                                    },
                                }
                            )

                if tool_calls_data:
                    ui.cancel_assistant()

                    merged_calls = self._merge_tool_calls(tool_calls_data)

                    for tool_call in merged_calls:
                        if tool_call["type"] != "function":
                            continue
                        if not tool_call["function"]:
                            continue

                        tool_name = tool_call["function"]["name"]
                        if not tool_name:
                            continue

                        tool_args_str = tool_call["function"]["arguments"] or ""
                        tool_args = json.loads(tool_args_str) if tool_args_str else {}

                        if ui.mode != Mode.MANUAL:
                            result = self._execute_tool(tool_name, tool_args)
                            ui.print_tool(tool_name, tool_args, result)

                        else:
                            allowed, always = ui.confirm_tool(tool_name, tool_args)

                            if always:
                                ui.set_mode(Mode.AUTO)
                                ui.print_system("Switched to auto mode")
                                result = self._execute_tool(tool_name, tool_args)

                            elif not allowed:
                                ui.print_system("Tool execution interrupted by user")
                                self.context.add_tool_call(
                                    tool_name,
                                    tool_args,
                                    "Tool execution interrupted by user",
                                )
                                return

                            else:
                                result = self._execute_tool(tool_name, tool_args)

                            ui.update_tool_result(tool_name, tool_args, result)

                        self.context.add_tool_call(tool_name, tool_args, result)

                elif content:
                    ui.finish_assistant()
                    self.context.add({"role": "assistant", "content": content})
                    break

            except Exception as e:
                ui.cancel_assistant()
                ui.print_error(f"API error: {str(e)}")
                break

    def _merge_tool_calls(self, tool_calls_data: list[dict]) -> list[dict]:
        merged = {}
        for call in tool_calls_data:
            call_id = call["id"]
            if call_id not in merged:
                merged[call_id] = {
                    "id": call_id,
                    "type": call["type"],
                    "function": {"name": call["function"]["name"], "arguments": ""},
                }
            if call["function"]["arguments"]:
                merged[call_id]["function"]["arguments"] += call["function"][
                    "arguments"
                ]
        return list(merged.values())
