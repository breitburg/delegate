import typer
from delegate.agent import Agent

app = typer.Typer(help="Lightweight coding agent with OpenAI-compatible APIs")


@app.command()
def main(
    model: str = typer.Option(
        "qwopus3.5-4b-v3",
        "-m",
        "--model",
        help="Model to use",
    ),
    temperature: float = typer.Option(
        0.3,
        "-t",
        "--temperature",
        min=0.0,
        max=2.0,
        help="Temperature for response generation",
    ),
    base_url: str = typer.Option(
        "http://localhost:1234/v1",
        "-u",
        "--base-url",
        help="API base URL",
    ),
    api_key: str = typer.Option(
        "delegate",
        "-k",
        "--api-key",
        help="API key (default: 'delegate')",
    ),
    compact_every: int = typer.Option(
        10,
        "-n",
        "--compact-every",
        min=2,
        help="Compact the context once it reaches this many messages",
    ),
    continue_session: bool = typer.Option(
        False,
        "-c",
        "--continue",
        help="Continue previous session in the current directory",
    ),
):
    """
    Start the coding agent CLI.
    """
    agent = Agent(
        model=model,
        temperature=temperature,
        base_url=base_url,
        api_key=api_key,
        compact_every=compact_every,
        continue_session=continue_session,
    )
    agent.run()
