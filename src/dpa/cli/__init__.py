"""CLI entry point for the data pipeline agent.

Provides three commands:
    - ``run``: Interactive REPL or scenario execution
    - ``replay``: Replay a saved session from JSONL
    - ``metrics``: Display collected metrics

Usage::

    # Interactive REPL
    PYTHONPATH=src python -m dpa.cli.main run

    # Run a scenario
    PYTHONPATH=src python -m dpa.cli.main run --scenario drift-demo

    # Replay a session
    PYTHONPATH=src python -m dpa.cli.main replay sessions/2025-09-05_abc123.jsonl

    # View metrics
    PYTHONPATH=src python -m dpa.cli.main metrics
    PYTHONPATH=src python -m dpa.cli.main metrics --format json
"""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from dpa.core import PipelineAgent
from dpa.metrics import get_metrics
from dpa.sessions import Session

console = Console()


@click.group()
def cli() -> None:
    """Adaptive Data Pipeline Agent (DPA) — LLM-driven data pipeline orchestration."""
    pass


@cli.command()
@click.option("--model", default="", help="LLM model name (overrides DPA_MODEL env var)")
@click.option("--scenario", help="Run a predefined scenario from examples/*.md")
def run(model: str, scenario: str | None) -> None:
    """Run in interactive REPL mode or execute a scenario.

    Without --scenario, starts a REPL where you can type natural language
    commands. With --scenario, reads steps from the corresponding markdown
    file in examples/ and executes them sequentially.
    """
    agent = PipelineAgent(model=model)
    session = Session(name=scenario or "repl")

    if scenario:
        _run_scenario(agent, session, scenario)
    else:
        _repl(agent, session)


@cli.command()
@click.argument("session_file")
def replay(session_file: str) -> None:
    """Replay a session from a JSONL file.

    Displays all messages, tool calls, and errors from a previous session
    in chronological order with syntax highlighting.
    """
    from pathlib import Path

    s = Session.load(Path(session_file))
    for msg in s.messages():
        role = msg.get("role", "")
        content = msg.get("content", "")
        tool = msg.get("tool", "")
        if role == "user":
            console.print(f"[bold blue]User:[/bold blue] {content}")
        elif role == "assistant" and content:
            console.print(Markdown(content))
        elif role == "tool_call":
            console.print(f"  [dim]-> {tool}({msg.get('args', {})}) -> {msg.get('result', {})} ({msg.get('latency_ms', 0)}ms)[/dim]")
        elif role == "error":
            console.print(f"[bold red]Error:[/bold red] {content}")


@cli.command()
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "json", "jsonl"]))
def metrics(fmt: str) -> None:
    """Show collected metrics (counters, histograms, uptime).

    Formats:
        - table: Rich table display (default)
        - json: Pretty-printed JSON
        - jsonl: Single-line JSON for piping
    """
    m = get_metrics()
    snap = m.snapshot()

    if fmt == "json":
        console.print_json(json.dumps(snap, ensure_ascii=False, default=str))
        return

    if fmt == "jsonl":
        console.print(json.dumps(snap, ensure_ascii=False, default=str))
        return

    # Table format
    console.print(f"\n[bold]Metrics Snapshot[/bold] (uptime: {snap['uptime_seconds']:.1f}s)\n")

    if snap["counters"]:
        table = Table(title="Counters")
        table.add_column("Name", style="cyan")
        table.add_column("Value", style="green", justify="right")
        for name, value in sorted(snap["counters"].items()):
            table.add_row(name, str(value))
        console.print(table)

    if snap["histograms"]:
        table = Table(title="Histograms")
        table.add_column("Name", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Avg", justify="right")
        table.add_column("P95", justify="right")
        table.add_column("Max", justify="right")
        for name, stats in sorted(snap["histograms"].items()):
            table.add_row(
                name,
                str(stats["count"]),
                f"{stats['min']:.1f}",
                f"{stats['avg']:.1f}",
                f"{stats['p95']:.1f}",
                f"{stats['max']:.1f}",
            )
        console.print(table)


def _repl(agent: PipelineAgent, session: Session) -> None:
    """Run the interactive REPL loop.

    Supports special commands:
        - ``exit`` / ``quit``: Exit the REPL
        - ``history``: Display session history
        - ``metrics``: Show collected metrics
    """
    console.print("[bold green]DPA REPL[/bold green] — type 'exit' to quit, 'history' to view session, 'metrics' to view metrics\n")
    while True:
        try:
            user_input = console.input("[bold blue]> [/bold blue]")
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.strip() in ("exit", "quit"):
            break
        if user_input.strip() == "history":
            for msg in session.messages():
                console.print(f"  {msg.get('role')}: {msg.get('content', msg.get('tool', ''))}")
            continue
        if user_input.strip() == "metrics":
            m = get_metrics()
            snap = m.snapshot()
            console.print(f"Uptime: {snap['uptime_seconds']:.1f}s")
            for k, v in snap["counters"].items():
                console.print(f"  {k}: {v}")
            continue
        if not user_input.strip():
            continue

        with console.status("[dim]Thinking...[/dim]"):
            response = agent.run(user_input, session)
        console.print(Markdown(response))
        console.print(f"[dim]Session saved to {session.path}[/dim]\n")


def _run_scenario(agent: PipelineAgent, session: Session, scenario: str) -> None:
    """Execute a predefined scenario from a markdown file.

    Parses the markdown file for lines starting with "- " and executes
    each as a user command. Displays results and metrics summary.

    Args:
        agent: PipelineAgent instance.
        session: Session for persistence.
        scenario: Scenario name (filename without .md extension).
    """
    from pathlib import Path

    script = Path("examples") / f"{scenario}.md"
    if not script.exists():
        console.print(f"[red]Scenario not found:[/red] {script}")
        return

    content = script.read_text(encoding="utf-8")
    steps = [line.strip().lstrip("- ") for line in content.splitlines() if line.strip().startswith("- ")]

    console.print(f"[bold]Running scenario: {scenario}[/bold] ({len(steps)} steps)\n")
    for i, step in enumerate(steps, 1):
        console.print(f"[bold blue]Step {i}:[/bold blue] {step}")
        with console.status("[dim]Executing...[/dim]"):
            response = agent.run(step, session)
        console.print(Markdown(response))
        console.print()

    console.print(f"[green]Scenario complete.[/green] Session: {session.path}")

    # Show metrics summary
    m = get_metrics()
    snap = m.snapshot()
    console.print(f"\n[bold]Metrics Summary:[/bold]")
    console.print(f"  LLM calls: {snap['counters'].get('llm_calls_total', 0)}")
    console.print(f"  Tool calls: {snap['counters'].get('tool_calls_total', 0)}")
    console.print(f"  Tokens input: {snap['counters'].get('llm_tokens_input_total', 0)}")
    console.print(f"  Tokens output: {snap['counters'].get('llm_tokens_output_total', 0)}")
