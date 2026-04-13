"""Shared utilities -- logging, console, and helper functions."""

from __future__ import annotations

import os
import sys

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.theme import Theme

# ---- Console ----------------------------------------------------------------

_theme = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "muted": "dim",
        "highlight": "bold magenta",
    }
)

# On Windows legacy console, avoid Unicode entirely
_is_legacy_windows = sys.platform == "win32" and not os.environ.get("WT_SESSION")

console = Console(theme=_theme, safe_box=_is_legacy_windows)


def print_success(message: str) -> None:
    console.print(f"[+] {message}", style="success")


def print_warning(message: str) -> None:
    console.print(f"[!] {message}", style="warning")


def print_error(message: str) -> None:
    console.print(f"[x] {message}", style="error")


def print_info(message: str) -> None:
    console.print(f"    {message}", style="info")


def print_muted(message: str) -> None:
    console.print(f"    {message}", style="muted")


# ---- Progress ---------------------------------------------------------------


def create_progress() -> Progress:
    """Create a rich progress bar for pipeline stages."""
    if _is_legacy_windows:
        # Avoid Braille/Unicode spinner on legacy Windows console
        return Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            console=console,
        )
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


# ─── Helpers ────────────────────────────────────────────────────────────────


def mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask a secret string, showing only the last N characters."""
    if not value:
        return "(not set)"
    if len(value) <= visible_chars:
        return "****"
    return "****" + value[-visible_chars:]
