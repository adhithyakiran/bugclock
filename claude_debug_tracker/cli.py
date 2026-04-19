"""
bugclock — CLI entry point.

Commands:
  init      Set up the tracker in your repo (DB + git hooks)
  start     Begin a debug session
  stop      End the current session (resolved or abandoned)
  status    Show the active session
  report    Analytics dashboard
  sessions  List recent sessions
  scan      Find Claude-generated files in the repo
  mark      Manually tag a file as Claude-generated
  export    Export session data (JSON or CSV)
  uninstall Remove git hooks
"""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from . import __version__
from . import hooks, storage, tracker, detector, reporter

console = Console()


@click.group()
@click.version_option(__version__, prog_name="bugclock")
def cli():
    """Track debugging time spent on Claude-generated code."""
    pass


# ── init ──────────────────────────────────────────────────────────────────────

@cli.command()
def init():
    """Initialize bugclock in the current repo."""
    storage.init_db()

    console.print()
    console.print(Panel(
        "[bold cyan]bugclock[/bold cyan]  initialized\n\n"
        f"  Database   [dim].claude-tracker/sessions.db[/dim]\n"
        f"  Registry   [dim].claude-tracker/marked_files.json[/dim]  [green](committable)[/green]",
        border_style="cyan",
        padding=(1, 2),
    ))

    hooks.install(verbose=False)
    console.print("  [green]✓[/green] Git hooks installed  [dim](pre-commit, post-commit)[/dim]")
    console.print()
    console.print("  Next steps:")
    console.print("    [cyan]bugclock mark <file>[/cyan]   — tag a file as Claude-generated")
    console.print("    [cyan]bugclock start[/cyan]         — begin a debug session")
    console.print("    [cyan]bugclock report[/cyan]        — view analytics")
    console.print()


# ── start ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("-f", "--file", "files", multiple=True, help="File(s) being debugged")
@click.option("-n", "--note", default="", help="Optional note about the bug")
def start(files, note):
    """Begin a debug session."""
    storage.init_db()

    active = tracker.get_active_session()
    if active:
        console.print(
            f"[yellow]Session #{active['id']} already active[/yellow] "
            f"(started {active['started_at'][:16].replace('T', ' ')} UTC).\n"
            "Run [cyan]bugclock stop[/cyan] first, or continue with a new one."
        )
        if not click.confirm("Start a new session anyway?", default=False):
            return

    files = list(files)

    # Auto-detect which supplied files are Claude-generated
    claude_files = [f for f in files if detector.is_claude_generated(f)]

    session_id = tracker.start_session(files=files, notes=note, source="manual")

    console.print()
    console.print(f"[green]✓[/green] Debug session [bold]#{session_id}[/bold] started")
    if files:
        console.print(f"  Files: {', '.join(files)}")
    if claude_files:
        console.print(f"  [cyan]Claude-generated:[/cyan] {', '.join(claude_files)}")
    console.print("  Run [cyan]bugclock stop[/cyan] when done.")
    console.print()


# ── stop ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--resolved/--abandoned", default=True,
              help="Mark session as resolved (default) or abandoned")
@click.option("-n", "--note", default="", help="Resolution note")
def stop(resolved, note):
    """End the current debug session."""
    active = tracker.get_active_session()
    if not active:
        console.print("[yellow]No active debug session found.[/yellow]")
        return

    status = "resolved" if resolved else "abandoned"
    result = tracker.stop_session(active["id"], status=status, notes=note)
    dur = tracker.duration_minutes(result)

    color = "green" if resolved else "red"
    console.print()
    console.print(
        f"[{color}]✓[/{color}] Session [bold]#{result['id']}[/bold] "
        f"[{color}]{status}[/{color}]  —  "
        f"[bold]{dur} min[/bold] spent debugging"
    )
    console.print()


# ── status ────────────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show the currently active session."""
    storage.init_db()
    active = tracker.get_active_session()
    if not active:
        console.print("[dim]No active debug session.[/dim]")
        return

    from datetime import datetime
    started = datetime.fromisoformat(active["started_at"])
    elapsed = round((datetime.utcnow() - started).total_seconds() / 60, 1)
    files = ", ".join(active.get("files") or []) or "—"

    console.print()
    console.print(Panel(
        f"[bold green]Session #{active['id']} — ACTIVE[/bold green]\n\n"
        f"  Started   {active['started_at'][:16].replace('T', ' ')} UTC\n"
        f"  Elapsed   [bold yellow]{elapsed} min[/bold yellow]\n"
        f"  Files     {files}\n"
        f"  Author    {active.get('author') or '—'}",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


# ── report ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--days", default=30, show_default=True, help="Number of days to include")
def report(days):
    """Show the full analytics dashboard."""
    reporter.print_report(days=days)


# ── sessions ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--limit", default=20, show_default=True)
@click.option("--status", type=click.Choice(["resolved", "abandoned", "active"]), default=None)
def sessions(limit, status):
    """List recent debug sessions."""
    storage.init_db()
    rows = tracker.list_sessions(limit=limit, status=status)

    if not rows:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(box=box.ROUNDED)
    table.add_column("#", style="dim", width=5)
    table.add_column("Started", width=18)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Status", width=10)
    table.add_column("Source", width=8)
    table.add_column("Files")

    for s in rows:
        dur = tracker.duration_minutes(s)
        dur_str = f"{dur} min" if dur is not None else "[yellow]active[/yellow]"
        color = {"resolved": "green", "abandoned": "red", "active": "yellow"}.get(s["status"], "white")
        files = ", ".join(s.get("files") or []) or "—"
        if len(files) > 40:
            files = files[:37] + "..."
        table.add_row(
            str(s["id"]),
            s["started_at"][:16].replace("T", " "),
            dur_str,
            f"[{color}]{s['status']}[/{color}]",
            s.get("source") or "manual",
            files,
        )

    console.print(table)


# ── scan ──────────────────────────────────────────────────────────────────────

@cli.command()
def scan():
    """Scan the repo for Claude-generated files."""
    console.print("[dim]Scanning repository...[/dim]")
    files = detector.scan_repo()

    if not files:
        console.print("[yellow]No Claude-generated files detected.[/yellow]")
        console.print(
            "Add [cyan]# @claude-generated[/cyan] to any file, or use "
            "[cyan]bugclock mark <file>[/cyan]."
        )
        return

    console.print(f"\n[green]Found {len(files)} Claude-generated file(s):[/green]\n")
    for f in files:
        console.print(f"  [cyan]{f}[/cyan]")
    console.print()


# ── mark ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("filepath")
def mark(filepath):
    """Manually tag a file as Claude-generated."""
    storage.init_db()
    if not Path(filepath).exists():
        console.print(f"[red]File not found:[/red] {filepath}")
        sys.exit(1)
    storage.save_marked_file(filepath, method="manual")
    console.print(f"[green]✓[/green] Marked [cyan]{filepath}[/cyan] as Claude-generated")
    console.print(f"  Registry saved to [dim]{storage.MARKED_FILES_PATH}[/dim]  (commit this file to share with your team)")


# ── export ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json", show_default=True)
@click.option("--days", default=30, show_default=True)
@click.option("-o", "--output", default=None, help="Output file path (default: stdout)")
def export(fmt, days, output):
    """Export session data as JSON or CSV."""
    data = reporter.export_json(days) if fmt == "json" else reporter.export_csv(days)

    if output:
        Path(output).write_text(data)
        console.print(f"[green]✓[/green] Exported to [cyan]{output}[/cyan]")
    else:
        click.echo(data)


# ── uninstall ─────────────────────────────────────────────────────────────────

@cli.command()
def uninstall():
    """Remove git hooks installed by bugclock."""
    hooks.uninstall(verbose=True)
    console.print("[green]✓[/green] Hooks removed. Your session data is still in [dim].claude-tracker/[/dim].")
