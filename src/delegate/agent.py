import json
import os
import platform
import threading
import time
from datetime import date
from openai import OpenAI
from rich.text import Text
from .context import Context
from .tools import registry
from .ui import ui, Mode
from pyfiglet import Figlet


class Agent:
    def __init__(
        self,
        model: str = "glm-4.7:cloud",
        temperature: float = 0.7,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "delegate",
        compact_every: int = 10,
        continue_session: bool = False,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.compact_every = compact_every
        self.context = Context(continue_session=continue_session)
        self._system_prompt = self._load_system_prompt()
        self._compaction_prompt = self._load_compaction_prompt()
        self._agent_thread: threading.Thread | None = None
        self._stop_requested = False

        # Set up UI with stop callback
        from .ui import UI
        global ui
        ui = UI(stop_callback=self.stop)

    def _load_system_prompt(self) -> str:
        """Load and format the system prompt from the system.md file."""
        package_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(package_dir, "..", "..", "prompts", "system.md")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_content = f.read()

        # Replace placeholders with actual values
        today = date.today()
        return system_content.format(
            platform=platform.system(),
            pwd=os.getcwd(),
            date=today.strftime("%A, %B %d, %Y"),
        )

    def _load_compaction_prompt(self) -> str:
        """Load the compaction instruction from the compaction.md file."""
        package_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(package_dir, "..", "..", "prompts", "compaction.md")

        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    def _compact_context(self):
        """Ask the model to summarize the current context, then replace it with the summary."""
        ui.print_system("Compacting context...")

        compaction_messages = self.context.get_messages() + [
            {"role": "user", "content": self._compaction_prompt}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=compaction_messages,
            temperature=self.temperature,
        )
        summary = response.choices[0].message.content

        self.context.clear()
        self.context.add(
            {
                "role": "user",
                "content": f"Summary of the conversation so far:\n\n{summary}\n\nContinue from here.",
            }
        )

        ui.print_system(f"Context compacted ({len(summary)} chars)")

    def run(self):
        f = Figlet(font="small", width=80)
        ui.console.print(Text(f.renderText("Delegate"), style="dim"))

        # Display quick usage guide
        ui.print_system("Press `Tab` to toggle modes  \n`Esc` to halt the agent  \n`/clear` to erase session")
        ui.console.print()

        # Display restored session message
        messages = self.context.get_messages()
        if messages:
            ui.print_info(f"Restored session with {len(messages)} messages")

        while True:
            try:
                # Only ask for input if the agent is not running
                if self.is_running():
                    # Wait a bit for the agent to finish
                    time.sleep(0.1)
                    continue

                user_input = ui.get_user_input()

                if not user_input:
                    continue

                if user_input == "/quit":
                    ui.print_system("Goodbye!")
                    break

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
        self.start()

    def _execute_tool(self, name: str, args: dict) -> str:
        tool_func = registry.get_tool(name)
        if not tool_func:
            return f"Error: Tool '{name}' not found"
        return tool_func(**args)

    def _run_agent_loop(self):
        while True:
            if self._stop_requested:
                break

            if len(self.context.get_messages()) >= self.compact_every:
                self._compact_context()

            ui.print_assistant_thinking()

            try:
                # Prepend system prompt to messages for the API call
                messages = [
                    {"role": "system", "content": self._system_prompt}
                ] + self.context.get_messages()

                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=registry.get_definitions(),
                    stream=True,
                    temperature=self.temperature,
                )

                content = ""
                reasoning = ""
                tool_calls_by_index: dict[int, dict] = {}

                for chunk in stream:
                    if self._stop_requested:
                        break

                    delta = chunk.choices[0].delta

                    reasoning_chunk = delta.model_extra.get("reasoning_content")
                    if reasoning_chunk:
                        reasoning += reasoning_chunk
                        ui.update_assistant_reasoning(reasoning)

                    if delta.content:
                        content += delta.content
                        ui.update_assistant_content(content)

                    if delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            index = tool_call_delta.index
                            if index not in tool_calls_by_index:
                                tool_calls_by_index[index] = {
                                    "id": tool_call_delta.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_call_delta.function.name,
                                        "arguments": "",
                                    },
                                }
                            if tool_call_delta.function.arguments:
                                tool_calls_by_index[index]["function"]["arguments"] += (
                                    tool_call_delta.function.arguments
                                )

                tool_calls_data = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]

                if self._stop_requested:
                    ui.cancel_assistant()
                    break

                if tool_calls_data:
                    ui.cancel_assistant()

                    for tool_call in tool_calls_data:
                        if self._stop_requested:
                            break

                        func = tool_call.get("function", {})
                        tool_name = func.get("name")
                        if not tool_name:
                            continue

                        tool_args = json.loads(func.get("arguments", "{}"))

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

    def start(self):
        """Start the agent loop in a separate thread."""
        if self._agent_thread and self._agent_thread.is_alive():
            ui.print_system("Agent is already running")
            return

        self._stop_requested = False
        self._agent_thread = threading.Thread(target=self._run_agent_loop, daemon=True)
        self._agent_thread.start()

    def stop(self):
        """Stop the agent loop."""
        if not self._agent_thread or not self._agent_thread.is_alive():
            ui.print_system("Agent is not running")
            return

        self._stop_requested = True
        self._agent_thread.join(timeout=5.0)

        if self._agent_thread.is_alive():
            ui.print_system("Agent did not stop gracefully")
        else:
            ui.print_system("Agent stopped")

    def is_running(self) -> bool:
        """Check if the agent loop is currently running."""
        return self._agent_thread is not None and self._agent_thread.is_alive()
