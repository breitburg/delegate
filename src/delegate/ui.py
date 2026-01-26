from enum import Enum
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.console import Group
from questionary import select
from prompt_toolkit import prompt
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.formatted_text import FormattedText
import json
import difflib


class Mode(Enum):
    AUTO = "auto"
    MANUAL = "manual"


class UI:
    def __init__(self):
        self.console = Console()
        self.mode: Mode = Mode.MANUAL
        self.live = None
        self._pending_tool = None
        self._pending_tool_lines = 0
        self._reasoning = ""
        self._content = ""

    def set_mode(self, mode: Mode):
        self.mode = mode

    def _get_prompt_text(self) -> FormattedText:
        bg = "darkmagenta" if self.mode == Mode.AUTO else "yellow"
        fg = "white" if self.mode == Mode.AUTO else "black"
        return FormattedText(
            [
                ("bg:" + bg + " fg:" + fg + " bold", f" {self.mode.value.upper()} "),
                ("", " › "),
            ]
        )

    def print_assistant_thinking(self):
        self._reasoning = ""
        self._content = ""
        panel = Panel(
            Text("Thinking...", style="italic dim"),
            title="[bold blue]Assistant[/bold blue]",
            border_style="blue",
        )
        self.live = Live(panel, console=self.console, refresh_per_second=10)
        self.live.start()

    def update_assistant_reasoning(self, reasoning: str):
        self._reasoning = reasoning
        self._update_display()

    def update_assistant_content(self, content: str):
        self._content = content
        self._update_display()

    def _update_display(self):
        if not self.live:
            return

        # Build separate renderables for reasoning (grey) and content (normal)
        renderables = []
        if self._reasoning:
            renderables.append(Markdown(self._reasoning, style="dim"))
        if self._content:
            renderables.append(Markdown(self._content))

        if renderables:
            title = "[bold blue]Assistant[/bold blue]"

            if len(renderables) == 1:
                content = renderables[0]
            else:
                # Add spacing between reasoning and content
                content = Group(renderables[0], Text(""), renderables[1])

            panel = Panel(
                content,
                title=title,
                border_style="blue",
            )
            self.live.update(panel)

    def _stop_live(self):
        if self.live:
            self.live.stop()
            self.live = None

    def finish_assistant(self):
        self._stop_live()

    def cancel_assistant(self):
        self._stop_live()

    def get_user_input(self) -> str:
        self._stop_live()

        # Set up key bindings for Tab to switch modes
        kb = KeyBindings()

        @kb.add(Keys.ControlI)  # ControlI is Tab
        def _(event):
            modes = list(Mode)
            current_index = modes.index(self.mode)
            next_index = (current_index + 1) % len(modes)
            self.set_mode(modes[next_index])

        user_input = prompt(lambda: self._get_prompt_text(), key_bindings=kb)
        return user_input.strip()

    def _format_diff(self, old: str, new: str) -> str:
        diff_lines = list(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile="before",
                tofile="after",
            )
        )

        if not diff_lines:
            return "No changes"

        formatted = []
        for line in diff_lines:
            if line.startswith("---") or line.startswith("+++"):
                formatted.append(f"[dim]{line.rstrip()}[/dim]")
            elif line.startswith("@@"):
                formatted.append(f"[cyan dim]{line.rstrip()}[/cyan dim]")
            elif line.startswith("-") and not line.startswith("---"):
                formatted.append(f"[red]{line.rstrip()}[/red]")
            elif line.startswith("+") and not line.startswith("+++"):
                formatted.append(f"[green]{line.rstrip()}[/green]")
            else:
                formatted.append(line.rstrip())

        return "\n".join(formatted)

    def _truncate_result(self, content: str) -> str:
        if len(content) >= 20000:
            return content[:20000] + "\n\n[red]Full output was truncated[/red]"
        return content

    def print_tool(self, name: str, args: dict, result: str = ""):
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."

        content = f"[bold]{name}[/bold]({args_str})"

        if result:
            try:
                result_data = json.loads(result)
                if result_data.get("type") == "file_change":
                    old_content = result_data.get("old_content", "")
                    new_content = result_data.get("new_content", "")

                    if old_content.strip() or new_content.strip():
                        if not old_content.strip():
                            content += f"\n\n[yellow]New file created: {result_data.get('filePath', '')}[/yellow]"
                        else:
                            diff_output = self._format_diff(old_content, new_content)
                            content += f"\n\n{self._truncate_result(diff_output)}"
                    else:
                        content += f"\n[dim]{result}[/dim]"
                else:
                    content += f"\n[dim]{self._truncate_result(result)}[/dim]"
            except json.JSONDecodeError:
                content += f"\n[dim]{self._truncate_result(result)}[/dim]"

        self.console.print(
            Panel(
                content,
                title="[bold yellow]Tool Call[/bold yellow]",
                border_style="yellow",
            )
        )

    def print_error(self, message: str):
        self.console.print(
            Panel(
                Text(message, style="red"),
                title="[bold red]Error[/bold red]",
                border_style="red",
            )
        )

    def confirm_tool(
        self, name: str, args: dict, result: str = ""
    ) -> tuple[bool, bool]:
        self._stop_live()

        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."

        self.console.print(
            Panel(
                f"[bold]{name}[/bold]({args_str})",
                title="[bold yellow]Tool Call[/bold yellow]",
                border_style="yellow",
            )
        )

        try:
            choice = select(
                "Do you want to proceed?",
                choices=["Allow", "Always allow for this session", "Deny"],
                default="Allow",
            ).ask()
            if choice == "Always allow for this session":
                return True, True
            return choice == "Allow", False
        except (KeyboardInterrupt, EOFError):
            return False, False

    def update_tool_result(self, name: str, args: dict, result: str):
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."

        content = f"[bold]{name}[/bold]({args_str})"

        if result:
            try:
                result_data = json.loads(result)
                if result_data.get("type") == "file_change":
                    old_content = result_data.get("old_content", "")
                    new_content = result_data.get("new_content", "")

                    if old_content.strip() or new_content.strip():
                        if not old_content.strip():
                            content += f"\n\n[yellow]New file created: {result_data.get('filePath', '')}[/yellow]"
                        else:
                            diff_output = self._format_diff(old_content, new_content)
                            content += f"\n\n{self._truncate_result(diff_output)}"
                    else:
                        content += f"\n[dim]{result}[/dim]"
                else:
                    content += f"\n[dim]{self._truncate_result(result)}[/dim]"
            except json.JSONDecodeError:
                content += f"\n[dim]{self._truncate_result(result)}[/dim]"

        panel = Panel(
            content,
            title="[bold yellow]Tool Call[/bold yellow]",
            border_style="yellow",
        )

        lines = 4
        lines += content.count("\n")
        self.console.print(f"\x1b[{lines}F")
        self.console.print(panel)

    def print_system(self, message: str):
        self.console.print(Text(message, style="dim"))

    def print_info(self, message: str):
        self.console.print("\n")
        self.console.print(
            Panel(
                Text(message, style="black"),
                border_style="grey58",
                style="on grey58",
            )
        )
        self.console.print("\n")


ui = UI()
