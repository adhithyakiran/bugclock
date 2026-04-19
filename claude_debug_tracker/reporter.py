"""
Rich-powered analytics and reporting.
Produces terminal reports, JSON/CSV exports, and ASCII bar charts.
"""

import json
import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text
from rich.columns import Columns

from .storage import get_db, init_db
from .tracker import duration_minutes, list_sessions

console = Console()


# ── Public API ────────────────────────────────────────────────────────────────

def print_report(days: int = 30):
    """Print a full analytics report to the terminal."""
    init_db()
    sessions = _fetch_completed(days)

    if not sessions:
        console.print(
            Panel(
                "[yellow]No completed debug sessions in the last "
                f"{days} days.[/yellow]\n\n"
                "Run [bold cyan]bugclock start[/bold cyan] to begin tracking.",
                title="Claude Debug Tracker",
                border_style="cyan",
            )
        )
        return

    stats = _compute_stats(sessions)

    # ── Header ────────────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"[bold cyan]Claude Debug Tracker[/bold cyan]  "
            f"[dim]last {days} days[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    # ── Key metrics ───────────────────────────────────────────────────────────
    metric_panels = [
        Panel(
            f"[bold white]{stats['total_sessions']}[/bold white]\n[dim]Total Sessions[/dim]",
            border_style="blue",
        ),
        Panel(
            f"[bold green]{stats['resolved']}[/bold green]\n[dim]Resolved[/dim]",
            border_style="green",
        ),
        Panel(
            f"[bold red]{stats['abandoned']}[/bold red]\n[dim]Abandoned[/dim]",
            border_style="red",
        ),
        Panel(
            f"[bold yellow]{stats['total_minutes']} min[/bold yellow]\n[dim]Total Debug Time[/dim]",
            border_style="yellow",
        ),
        Panel(
            f"[bold magenta]{stats['avg_minutes']} min[/bold magenta]\n[dim]Avg per Session[/dim]",
            border_style="magenta",
        ),
        Panel(
            f"[bold white]{stats['longest_minutes']} min[/bold white]\n[dim]Longest Session[/dim]",
            border_style="white",
        ),
    ]
    console.print(Columns(metric_panels, equal=True, expand=True))
    console.print()

    # ── Daily chart ───────────────────────────────────────────────────────────
    _print_daily_chart(sessions, days=min(days, 14))

    # ── Recent sessions table ─────────────────────────────────────────────────
    _print_sessions_table(sessions[:10])

    # ── Top debugged files ────────────────────────────────────────────────────
    _print_top_files(sessions)

    # ── Auto vs manual breakdown ──────────────────────────────────────────────
    auto = sum(1 for s in sessions if s.get("source") == "auto")
    manual = len(sessions) - auto
    if auto:
        console.print(
            f"[dim]Session sources: {manual} manual · {auto} auto-inferred from commits[/dim]\n"
        )


def export_json(days: int = 30) -> str:
    sessions = _fetch_completed(days)
    enriched = []
    for s in sessions:
        s["duration_minutes"] = duration_minutes(s)
        enriched.append(s)
    return json.dumps(enriched, indent=2)


def export_csv(days: int = 30) -> str:
    sessions = _fetch_completed(days)
    buf = io.StringIO()
    fields = ["id", "started_at", "ended_at", "duration_minutes", "status",
              "files", "author", "source", "notes", "commit_hash"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for s in sessions:
        s["duration_minutes"] = duration_minutes(s)
        s["files"] = "; ".join(s.get("files") or [])
        writer.writerow(s)
    return buf.getvalue()


# ── Private helpers ───────────────────────────────────────────────────────────

def _fetch_completed(days: int) -> List[dict]:
    init_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE status != 'active' AND started_at >= ? "
        "ORDER BY started_at DESC",
        (cutoff,),
    ).fetchall()
    conn.close()

    import json as _json
    result = []
    for r in rows:
        d = dict(r)
        d["files"] = _json.loads(d.get("files") or "[]")
        result.append(d)
    return result


def _compute_stats(sessions: List[dict]) -> dict:
    durations = [d for s in sessions if (d := duration_minutes(s)) is not None]
    resolved = sum(1 for s in sessions if s["status"] == "resolved")
    abandoned = len(sessions) - resolved
    total = round(sum(durations), 1)
    avg = round(total / len(durations), 1) if durations else 0.0
    longest = round(max(durations), 1) if durations else 0.0
    return {
        "total_sessions": len(sessions),
        "resolved": resolved,
        "abandoned": abandoned,
        "total_minutes": total,
        "avg_minutes": avg,
        "longest_minutes": longest,
    }


def _print_daily_chart(sessions: List[dict], days: int = 14):
    # Bucket by day
    buckets: dict = defaultdict(float)
    for s in sessions:
        d = duration_minutes(s)
        if d is None:
            continue
        day = s["started_at"][:10]
        buckets[day] += d

    if not buckets:
        return

    today = datetime.utcnow().date()
    day_range = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    max_val = max(buckets.values()) or 1
    bar_width = 20

    table = Table(title="Daily Debug Time (minutes)", box=box.SIMPLE, show_header=True)
    table.add_column("Date", style="dim", width=12)
    table.add_column("Minutes", justify="right", width=8)
    table.add_column("", width=bar_width + 2)

    for day in day_range:
        val = buckets.get(day, 0.0)
        filled = int((val / max_val) * bar_width)
        bar = "[cyan]" + "█" * filled + "[/cyan]" + "░" * (bar_width - filled)
        table.add_row(day, f"{round(val, 1)}", bar)

    console.print(table)
    console.print()


def _print_sessions_table(sessions: List[dict]):
    table = Table(title="Recent Sessions", box=box.ROUNDED, show_lines=False)
    table.add_column("#", style="dim", width=5)
    table.add_column("Started", width=20)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Status", width=10)
    table.add_column("Files", width=30)
    table.add_column("Author", width=16)

    for s in sessions:
        dur = duration_minutes(s)
        dur_str = f"{dur} min" if dur is not None else "—"
        files = ", ".join(s.get("files") or []) or "[dim]—[/dim]"
        if len(files) > 30:
            files = files[:27] + "..."

        status_color = {"resolved": "green", "abandoned": "red"}.get(s["status"], "yellow")
        table.add_row(
            str(s["id"]),
            s["started_at"][:16].replace("T", " "),
            dur_str,
            f"[{status_color}]{s['status']}[/{status_color}]",
            files,
            s.get("author") or "—",
        )

    console.print(table)
    console.print()


def _print_top_files(sessions: List[dict]):
    file_time: dict = defaultdict(float)
    file_count: dict = defaultdict(int)

    for s in sessions:
        d = duration_minutes(s) or 0.0
        for f in s.get("files") or []:
            file_time[f] += d
            file_count[f] += 1

    if not file_time:
        return

    top = sorted(file_time.items(), key=lambda x: x[1], reverse=True)[:8]

    table = Table(title="Most-Debugged Files", box=box.SIMPLE)
    table.add_column("File", style="cyan")
    table.add_column("Sessions", justify="right", width=10)
    table.add_column("Total Time", justify="right", width=12)

    for filepath, total in top:
        table.add_row(filepath, str(file_count[filepath]), f"{round(total, 1)} min")

    console.print(table)
    console.print()
