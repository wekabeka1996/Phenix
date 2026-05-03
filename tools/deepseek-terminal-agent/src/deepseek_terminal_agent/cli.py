"""CLI entry point for deepseek-terminal-agent.

Commands:
  deepseek-agent chat                    — interactive multi-turn session
  deepseek-agent run "prompt"            — single-shot, print result
  deepseek-agent run --dry-run "prompt"  — show commands without executing

Global options:
  --config PATH        path to agent.yaml  (default: config/agent.yaml)
  --workspace DIR      override workspace root
  --verbose            show iteration-level debug output
  --env-file PATH      .env file to load  (default: .env)
"""
from __future__ import annotations

import sys
import traceback
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .agent_loop import AgentLoop, MaxIterationsError
from .config import load_settings
from .deepseek_client import DeepSeekClient
from .logging_utils import RunLogger
from .terminal_tool import TerminalExecutor

console = Console()


@click.group()
@click.option(
    "--config",
    "config_path",
    default="config/agent.yaml",
    show_default=True,
    help="Path to agent.yaml config file.",
)
@click.option("--workspace", default=None, help="Override workspace root directory.")
@click.option("--verbose", is_flag=True, help="Show per-iteration debug output.")
@click.option(
    "--env-file",
    default=".env",
    show_default=True,
    help="Path to .env file.",
)
@click.pass_context
def main(
    ctx: click.Context,
    config_path: str,
    workspace: Optional[str],
    verbose: bool,
    env_file: str,
) -> None:
    """DeepSeek Terminal Agent — coding/terminal AI powered by DeepSeek."""
    ctx.ensure_object(dict)
    settings = load_settings(config_path=config_path, env_file=env_file)
    if workspace:
        settings.terminal.workspace_root = workspace
    ctx.obj["settings"] = settings
    ctx.obj["verbose"] = verbose


@main.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Start an interactive multi-turn chat session."""
    settings = ctx.obj["settings"]
    verbose = ctx.obj["verbose"]

    logger = RunLogger(log_dir=settings.agent.log_dir)
    executor = TerminalExecutor(
        workspace_root=settings.terminal.workspace_root,
        default_timeout_sec=settings.terminal.default_timeout_sec,
        max_output_chars=settings.terminal.max_output_chars,
        require_approval_for_dangerous=settings.terminal.require_approval_for_dangerous,
        terminal_log_path=logger.terminal_log_path,
        dry_run=False,
        interactive=True,
    )
    client = DeepSeekClient(settings.deepseek)
    loop = AgentLoop(
        settings=settings,
        client=client,
        executor=executor,
        logger=logger,
        dry_run=False,
        verbose=verbose,
    )

    console.print(
        Panel(
            f"[bold green]DeepSeek Terminal Agent[/bold green]\n"
            f"Model     : [cyan]{settings.deepseek.model}[/cyan]\n"
            f"Workspace : [cyan]{settings.terminal.workspace_root}[/cyan]\n"
            f"Run logs  : [dim]{logger.run_url()}[/dim]\n\n"
            "Type [bold]exit[/bold] or [bold]quit[/bold] to end the session.",
            title="Chat Session",
        )
    )

    while True:
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Session ended.[/dim]")
            break
        if not user_input:
            continue

        try:
            answer = loop.run(user_input)
            console.print(
                Panel(Markdown(answer), title="[green]Agent[/green]"))
            logger.write_summary(answer)
        except MaxIterationsError as exc:
            console.print(f"[red][MAX ITERATIONS][/red] {exc}")
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
            break
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red][ERROR][/red] {exc}")
            if verbose:
                traceback.print_exc()


@main.command()
@click.argument("prompt")
@click.option("--dry-run", is_flag=True, help="Show commands without executing them.")
@click.pass_context
def run(ctx: click.Context, prompt: str, dry_run: bool) -> None:
    """Run a single prompt (non-interactive) and print the result."""
    settings = ctx.obj["settings"]
    verbose = ctx.obj["verbose"]

    logger = RunLogger(log_dir=settings.agent.log_dir)
    executor = TerminalExecutor(
        workspace_root=settings.terminal.workspace_root,
        default_timeout_sec=settings.terminal.default_timeout_sec,
        max_output_chars=settings.terminal.max_output_chars,
        require_approval_for_dangerous=settings.terminal.require_approval_for_dangerous,
        terminal_log_path=logger.terminal_log_path,
        dry_run=dry_run,
        interactive=False,
    )
    client = DeepSeekClient(settings.deepseek)
    loop = AgentLoop(
        settings=settings,
        client=client,
        executor=executor,
        logger=logger,
        dry_run=dry_run,
        verbose=verbose,
    )

    if dry_run:
        console.print(
            "[yellow][DRY RUN][/yellow] Commands shown but not executed.\n")

    try:
        answer = loop.run(prompt)
        console.print(
            Panel(Markdown(answer), title="[green]Agent Response[/green]"))
        logger.write_summary(answer)
        console.print(f"\n[dim]Run logs: {logger.run_url()}[/dim]")
    except MaxIterationsError as exc:
        console.print(f"[red][MAX ITERATIONS][/red] {exc}")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red][ERROR][/red] {exc}")
        if verbose:
            traceback.print_exc()
        sys.exit(1)
