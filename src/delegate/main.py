import typer
from delegate.agent import Agent

app = typer.Typer(help="Lightweight coding agent with OpenAI-compatible APIs")


@app.command()
def main(
    model: str = typer.Option(
        "glm-4.7:cloud",
        "-m",
        "--model",
        help="Model to use (default for Ollama: glm-4.7:cloud)",
    ),
    temperature: float = typer.Option(
        0.7,
        "-t",
        "--temperature",
        min=0.0,
        max=2.0,
        help="Temperature for response generation",
    ),
    base_url: str = typer.Option(
        "http://localhost:11434/v1",
        "-u",
        "--base-url",
        help="API base URL (default: Ollama)",
    ),
    api_key: str = typer.Option("ollama", "-k", "--api-key", help="API key"),
):
    """
    Start the coding agent CLI.
    """
    agent = Agent(
        model=model, temperature=temperature, base_url=base_url, api_key=api_key
    )
    agent.run()
