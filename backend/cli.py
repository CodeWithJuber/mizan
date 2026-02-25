"""
MIZAN CLI — Command-line interface for the Agentic Personal AI
===============================================================

Usage:
    mizan chat          Interactive chat with your AI
    mizan serve         Start the API server
    mizan status        Show system status
    mizan setup         Interactive setup wizard
"""

import os
import sys
import json
import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.table import Table
from rich.live import Live
from rich.text import Text

console = Console()

BANNER = """[bold gold1]
 ╔═══════════════════════════════════════════════════╗
 ║          ميزان  ·  MIZAN v3.0                     ║
 ║      Agentic Personal AI                          ║
 ║  "And He imposed the balance (Mizan)" — 55:7      ║
 ╚═══════════════════════════════════════════════════╝
[/bold gold1]"""


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """MIZAN — Agentic Personal AI with Quranic Cognitive Architecture."""
    if ctx.invoked_subcommand is None:
        console.print(BANNER)
        console.print("  Run [bold cyan]mizan --help[/] for commands\n")
        console.print("  [dim]Quick start:[/]")
        console.print("    [cyan]mizan setup[/]     — First-time setup")
        console.print("    [cyan]mizan serve[/]     — Start API server")
        console.print("    [cyan]mizan chat[/]      — Interactive chat")
        console.print()


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, help="Port to listen on")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload")
def serve(host, port, reload):
    """Start the MIZAN API server."""
    console.print(BANNER)
    console.print(f"  Starting server on [bold cyan]http://{host}:{port}[/]")
    console.print(f"  API docs at [bold cyan]http://{host}:{port}/docs[/]\n")

    import uvicorn
    uvicorn.run(
        "backend.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@main.command()
@click.option("--agent", default=None, help="Agent name to chat with")
@click.option("--model", default=None, help="Override AI model")
def chat(agent, model):
    """Interactive chat with your AI agent."""
    console.print(BANNER)

    # Check for API key
    from backend.settings import get_settings
    settings = get_settings()

    if not settings.has_anthropic and not settings.has_openai:
        console.print(
            "[bold red]No API key configured.[/]\n"
            "Run [cyan]mizan setup[/] or set ANTHROPIC_API_KEY in your .env file.\n"
        )
        return

    console.print("  [dim]Type your message and press Enter. Type 'exit' to quit.[/]\n")

    asyncio.run(_chat_loop(settings, agent, model))


async def _chat_loop(settings, agent_name, model_override):
    """Async chat loop using the agent directly."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = model_override or settings.default_model
    history = []

    system_prompt = (
        "You are MIZAN, an agentic personal AI assistant. "
        "You are helpful, accurate, and thoughtful. "
        "You think step by step and provide clear, actionable responses."
    )

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/]")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye![/]")
            break

        if not user_input.strip():
            continue

        history.append({"role": "user", "content": user_input})

        console.print("[bold gold1]MIZAN[/] ", end="")

        try:
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=history[-20:],  # Keep last 20 messages for context
            ) as stream:
                full_response = ""
                for text in stream.text_stream:
                    console.print(text, end="", highlight=False)
                    full_response += text

                console.print()  # Newline after response
                history.append({"role": "assistant", "content": full_response})

        except anthropic.APIError as e:
            console.print(f"\n[red]API Error: {e}[/]")
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/]")


@main.command()
def status():
    """Show MIZAN system status."""
    console.print(BANNER)

    import httpx
    try:
        resp = httpx.get("http://localhost:8000/api/status", timeout=5)
        data = resp.json()

        table = Table(title="System Status", border_style="gold1")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details")

        table.add_row("System", data.get("status", "unknown"), f"v{data.get('version', '?')}")
        agents = data.get("agents", {})
        table.add_row("Agents", str(agents.get("total", 0)), f"{agents.get('active', 0)} active")
        table.add_row("Connections", str(data.get("connections", 0)), "WebSocket")
        table.add_row("Sessions", str(data.get("sessions", 0)), "Active chats")

        console.print(table)

    except httpx.ConnectError:
        console.print("[yellow]Server not running.[/] Start with: [cyan]mizan serve[/]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")


@main.command()
def setup():
    """Interactive setup wizard for first-time configuration."""
    console.print(BANNER)
    console.print("[bold]First-time setup wizard[/]\n")

    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"

    if env_file.exists():
        overwrite = Prompt.ask(
            ".env file already exists. Overwrite?",
            choices=["y", "n"],
            default="n",
        )
        if overwrite != "y":
            console.print("[dim]Keeping existing .env[/]")
            return

    # Copy template
    if env_example.exists():
        env_content = env_example.read_text()
    else:
        env_content = ""

    # Ask for API key
    console.print("\n[bold]AI Provider Configuration[/]")
    console.print("[dim]You need at least one API key to use MIZAN.[/]\n")

    api_key = Prompt.ask(
        "Anthropic API Key (sk-ant-...)",
        default="",
        password=True,
    )

    if api_key:
        env_content = env_content.replace(
            "sk-ant-your-key-here", api_key
        )

    # Write .env
    env_file.write_text(env_content)
    console.print(f"\n[green]Wrote {env_file}[/]")

    # Create data directory
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    console.print(f"[green]Created {data_dir}[/]")

    console.print("\n[bold green]Setup complete![/]")
    console.print("  Start the server: [cyan]mizan serve[/]")
    console.print("  Or chat directly: [cyan]mizan chat[/]\n")


@main.command()
def version():
    """Show MIZAN version."""
    console.print("MIZAN v3.0.0")


if __name__ == "__main__":
    main()
