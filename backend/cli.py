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

from backend._version import __version__

console = Console()

BANNER = f"""[bold gold1]
 ╔═══════════════════════════════════════════════════╗
 ║          ميزان  ·  MIZAN v{__version__:<25s}║
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

    if not settings.has_any_provider:
        console.print(
            "[bold red]No API key configured.[/]\n"
            "Run [cyan]mizan setup[/] or set one of these in your .env file:\n"
            "  ANTHROPIC_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY\n"
        )
        return

    console.print("  [dim]Type your message and press Enter. Type 'exit' to quit.[/]\n")

    asyncio.run(_chat_loop(settings, agent, model))


async def _chat_loop(settings, agent_name, model_override):
    """Async chat loop using the unified provider interface."""
    from backend.providers import create_provider, get_default_model

    provider_name = settings.llm_provider or None
    model = model_override or settings.default_model
    provider = create_provider(provider=provider_name, model=model)

    if not provider:
        console.print("[bold red]Could not initialize LLM provider.[/]")
        return

    if not model_override:
        model = model or get_default_model(provider.provider_name)

    console.print(f"  [dim]Provider: {provider.provider_name} | Model: {model}[/]\n")

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
            with provider.stream(
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

    # Ask for API keys
    console.print("\n[bold]AI Provider Configuration[/]")
    console.print("[dim]You need at least one API key to use MIZAN.[/]\n")

    api_key = Prompt.ask(
        "Anthropic API Key (sk-ant-...)",
        default="",
        password=True,
    )
    if api_key:
        env_content = env_content.replace("sk-ant-your-key-here", api_key)

    openrouter_key = Prompt.ask(
        "OpenRouter API Key (sk-or-... — optional, 300+ models)",
        default="",
        password=True,
    )
    if openrouter_key:
        env_content = env_content.replace(
            "OPENROUTER_API_KEY=",
            f"OPENROUTER_API_KEY={openrouter_key}",
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
    console.print(f"MIZAN v{__version__}")


@main.command()
@click.option("--check", is_flag=True, default=False, help="Diagnose only, don't fix")
@click.option("--fix", is_flag=True, default=False, help="Auto-fix all issues")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def doctor(check, fix, as_json):
    """
    Self-healing diagnostic — check system health and auto-fix issues.

    \b
    "And We send down of the Quran that which is a healing (shifa)
     and a mercy for the believers." — 17:82
    """
    from backend.doctor import run_doctor, report_to_dict, CheckStatus

    if not as_json:
        console.print(BANNER)
        console.print("[bold]MIZAN Doctor (شفاء - Shifa)[/]")
        console.print("[dim]Diagnosing system health...[/]\n")

    auto_fix = fix or (not check)  # Default: auto-fix unless --check
    report = run_doctor(auto_fix=auto_fix, check_only=check)

    if as_json:
        import json
        console.print(json.dumps(report_to_dict(report), indent=2))
        return

    # Rich formatted output
    status_styles = {
        CheckStatus.PASS:  ("[green]✓[/]", "green"),
        CheckStatus.WARN:  ("[yellow]⚠[/]", "yellow"),
        CheckStatus.FAIL:  ("[red]✗[/]", "red"),
        CheckStatus.FIXED: ("[cyan]⚕[/]", "cyan"),
        CheckStatus.SKIP:  ("[dim]–[/]", "dim"),
    }

    for c in report.checks:
        icon, style = status_styles[c.status]
        console.print(f"  {icon} [{style}]{c.name}[/]: {c.message}")
        if c.status == CheckStatus.FIXED and c.fix_message:
            console.print(f"       [cyan]Healed:[/] {c.fix_message}")
        elif c.status == CheckStatus.FAIL and c.fix_description:
            console.print(f"       [red]Fix:[/] {c.fix_description}")
        elif c.status == CheckStatus.WARN and c.fix_description:
            console.print(f"       [yellow]Hint:[/] {c.fix_description}")

    console.print()

    total = len(report.checks)
    skipped = sum(1 for c in report.checks if c.status == CheckStatus.SKIP)

    if report.healthy:
        console.print(
            Panel(
                f"[green bold]HEALTHY[/]\n"
                f"{report.passed}/{total - skipped} passed, "
                f"{report.warnings} warnings, "
                f"{report.fixes_applied} auto-healed",
                title="Diagnosis",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[red bold]NEEDS ATTENTION[/]\n"
                f"{report.passed}/{total - skipped} passed, "
                f"{report.failures} failures, "
                f"{report.warnings} warnings\n\n"
                f"Run [cyan]mizan doctor --fix[/] to auto-heal"
                if check else
                f"Some issues could not be auto-fixed. See above.",
                title="Diagnosis",
                border_style="red",
            )
        )


if __name__ == "__main__":
    main()
