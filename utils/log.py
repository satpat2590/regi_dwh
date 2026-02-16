"""
Color-coded logging utilities for the pipeline.

Provides consistent, color-coded console output across all pipeline scripts.
Uses colorama for cross-platform terminal color support.
"""

import datetime
import logging
import sys

from colorama import Fore, Style, init

# Initialize colorama (auto-reset after each print)
init(autoreset=True)


# ---------------------------------------------------------------------------
# Color constants for pipeline stages
# ---------------------------------------------------------------------------

class C:
    """Color shortcuts for pipeline output."""
    HEADER = Fore.CYAN + Style.BRIGHT
    STEP = Fore.BLUE + Style.BRIGHT
    OK = Fore.GREEN + Style.BRIGHT
    WARN = Fore.YELLOW + Style.BRIGHT
    ERR = Fore.RED + Style.BRIGHT
    INFO = Fore.WHITE
    DIM = Style.DIM
    TICKER = Fore.MAGENTA + Style.BRIGHT
    SECTOR = Fore.CYAN
    VALUE = Fore.GREEN
    RESET = Style.RESET_ALL


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Pipeline-level logging
# ---------------------------------------------------------------------------

def header(msg: str) -> None:
    """Print a bold section header."""
    print(f"\n{C.HEADER}{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}{C.RESET}\n")


def step(msg: str) -> None:
    """Print a pipeline step."""
    print(f"{C.STEP}[{_ts()}] >> {msg}{C.RESET}")


def info(msg: str) -> None:
    """Print an info message."""
    print(f"{C.DIM}[{_ts()}]{C.RESET} {msg}")


def ok(msg: str) -> None:
    """Print a success message."""
    print(f"{C.OK}[{_ts()}] OK {msg}{C.RESET}")


def warn(msg: str) -> None:
    """Print a warning."""
    print(f"{C.WARN}[{_ts()}] WARN {msg}{C.RESET}")


def err(msg: str) -> None:
    """Print an error."""
    print(f"{C.ERR}[{_ts()}] ERR {msg}{C.RESET}")


def ticker_msg(ticker: str, msg: str) -> None:
    """Print a ticker-scoped message."""
    print(f"{C.DIM}[{_ts()}]{C.RESET} {C.TICKER}{ticker}{C.RESET} {msg}")


def progress(current: int, total: int, ticker: str, msg: str) -> None:
    """Print a progress line like [3/21] AAPL: ..."""
    pct = (current / total) * 100 if total else 0
    print(
        f"{C.DIM}[{_ts()}]{C.RESET} "
        f"{C.STEP}[{current}/{total}]{C.RESET} "
        f"{C.TICKER}{ticker}{C.RESET}: {msg}"
    )


def summary_table(title: str, rows: list[tuple[str, str]]) -> None:
    """Print a summary table with label-value pairs."""
    print(f"\n{C.HEADER}{title}{C.RESET}")
    max_label = max(len(r[0]) for r in rows) if rows else 0
    for label, value in rows:
        print(f"  {label:<{max_label}}  {C.VALUE}{value}{C.RESET}")
    print()


# ---------------------------------------------------------------------------
# Verbose logging setup
# ---------------------------------------------------------------------------

def setup_verbose_logging(name: str = "pipeline", level: int = logging.DEBUG) -> logging.Logger:
    """
    Create a verbose logger that writes to both console and logs/pipeline.log.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers on re-import
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (INFO+)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler (DEBUG+)
    import os
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "pipeline.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
