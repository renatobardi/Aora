from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

console = Console()


def make_progress() -> Progress:
    """Progress bar with spinner + counter + elapsed time."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def make_spinner() -> Progress:
    """Spinner only — for operations with unknown duration."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )


def ok_line(name: str, count: int) -> str:
    n = escape(name)
    if count > 0:
        return f"[green]  \\[OK]   {n}: {count} novo(s)[/green]"
    return f"  \\[OK]   {n}: {count} novo(s)"


def warn_line(name: str, reason: str) -> str:
    return f"[yellow]  \\[WARN] {escape(name)}: {escape(reason)}[/yellow]"


def err_line(name: str, reason: str) -> str:
    return f"[red]  \\[NOK]  {escape(name)}: {escape(reason)}[/red]"
