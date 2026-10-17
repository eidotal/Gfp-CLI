"""
utils.py - Centralized Perforce, path, and system utilities for gfp-cli.

Compatible with Python >= 3.6.4.
"""

import os
import shlex
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict

# Python version compatibility ("#ifdef" equivalent for Python < 3.7)
TEXT_MODE: Dict[str, Any] = {"text": True} if sys.version_info >= (3, 7) else {"universal_newlines": True}

# ANSI terminal control sequences for alternate buffer management
ENTER_ALT_SCREEN = "\033[?1049h"
EXIT_ALT_SCREEN = "\033[?1049l"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

# ANSI color codes
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_MAGENTA = "\033[35m"
COLOR_CYAN = "\033[36m"
COLOR_WHITE = "\033[37m"


@contextmanager
def alternate_screen():
    """
    Context manager that switches the terminal to the secondary screen buffer
    and restores the main terminal buffer and cursor upon exit.
    """
    if not sys.stdout.isatty():
        yield
        return

    try:
        sys.stdout.write(ENTER_ALT_SCREEN + HIDE_CURSOR)
        sys.stdout.flush()
        yield
    finally:
        sys.stdout.write(EXIT_ALT_SCREEN + SHOW_CURSOR)
        sys.stdout.flush()


def get_active_client(run_p4):
    """
    Resolves active Perforce client workspace name via:
      1. Environment variable P4CLIENT
      2. 'p4 set P4CLIENT' (stripping comments and parenthetical annotations)
      3. 'p4 info' (Client name:)
    Returns client name string or None if unresolvable.
    """
    p4client = os.environ.get("P4CLIENT")
    if p4client:
        return p4client.strip()

    try:
        p4_set_out = run_p4(["set", "P4CLIENT"], capture=True, check=False)
        if p4_set_out:
            for line in p4_set_out.splitlines():
                if line.startswith("P4CLIENT="):
                    val = line.split("=", 1)[1].split()[0].strip()
                    val = val.split("(")[0].strip()
                    if val:
                        return val
    except Exception:
        pass

    try:
        p4_info_out = run_p4(["info"], capture=True, check=False)
        if p4_info_out:
            for line in p4_info_out.splitlines():
                if line.startswith("Client name:"):
                    val = line.split(":", 1)[1].strip()
                    if val:
                        return val
    except Exception:
        pass

    return None


def get_user(run_p4):
    """
    Resolves Perforce user name via:
      1. Environment variable P4USER
      2. 'p4 set P4USER' (stripping comments and parenthetical annotations)
      3. 'p4 info' (User name:)
      4. Environment variable USER / fallback to 'devuser'
    """
    p4user = os.environ.get("P4USER")
    if p4user:
        return p4user.strip()

    try:
        set_out = run_p4(["set", "P4USER"], capture=True, check=False)
        if set_out:
            for line in set_out.splitlines():
                if line.startswith("P4USER="):
                    val = line.split("=", 1)[1].split()[0].strip()
                    val = val.split("(")[0].strip()
                    if val:
                        return val
    except Exception:
        pass

    try:
        info_out = run_p4(["info"], capture=True, check=False)
        if info_out:
            for line in info_out.splitlines():
                if line.startswith("User name:"):
                    val = line.split(":", 1)[1].strip()
                    if val:
                        return val
    except Exception:
        pass

    return os.environ.get("USER", "devuser")


def get_p4port(run_p4):
    """
    Resolves P4PORT via:
      1. Environment variable P4PORT
      2. 'p4 set P4PORT' (stripping parenthetical source annotations like (set) or (config))
      3. 'p4 info' (Server address:)
    Returns P4PORT string or None if unresolvable.
    """
    if os.environ.get("P4PORT"):
        return os.environ["P4PORT"].strip()

    try:
        set_out = run_p4(["set", "P4PORT"], capture=True, check=False)
        if set_out and "P4PORT=" in set_out:
            for line in set_out.splitlines():
                if line.startswith("P4PORT="):
                    val = line.split("P4PORT=", 1)[1].split()[0].strip()
                    val = val.split("(")[0].strip()
                    if val:
                        return val
    except Exception:
        pass

    try:
        info_out = run_p4(["info"], capture=True, check=False)
        if info_out:
            for line in info_out.splitlines():
                if line.startswith("Server address:"):
                    val = line.split(":", 1)[1].strip()
                    if val:
                        return val
    except Exception:
        pass

    return None


def get_active_stream(run_p4):
    """Resolves active stream from client spec (p4 client -o), extracting Stream: if not none/null."""
    try:
        client_out = run_p4(["client", "-o"], capture=True, check=False)
        if client_out:
            for line in client_out.splitlines():
                if line.startswith("Stream:"):
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        val = parts[1].strip()
                        if val and val.lower() not in ("none", "null"):
                            return val
    except Exception:
        pass
    return None


def resolve_stream_path(stream_name, active_stream=None):
    """Ensures a stream name has full Perforce depot syntax (//depot/stream)."""
    if not stream_name:
        return stream_name
    if stream_name.startswith("//"):
        return stream_name
    if active_stream and active_stream.startswith("//"):
        parts = active_stream.strip("/").split("/")
        if len(parts) >= 1:
            depot = parts[0]
            return f"//{depot}/{stream_name}"
    return stream_name


def escape_p4_path(path_str):
    """Escapes Perforce special characters (@, #, %, *) in literal filenames/paths."""
    if not path_str:
        return path_str
    # Must escape '%' first to prevent double-encoding
    return path_str.replace("%", "%25").replace("@", "%40").replace("#", "%23").replace("*", "%2A")


def unescape_p4_path(path_str):
    """Unescapes Perforce special characters (%25, %40, %23, %2A) back to literal characters."""
    if not path_str:
        return path_str
    # Must unescape '%25' LAST to prevent accidental double-unescaping
    return path_str.replace("%40", "@").replace("%23", "#").replace("%2A", "*").replace("%2a", "*").replace("%25", "%")


def to_p4_path(path_str):
    """Converts a local file/directory path to Perforce path syntax with character escaping."""
    if not path_str or path_str in (".", "./"):
        return "..."
    if path_str == "..." or path_str.endswith("/...") or path_str.endswith("..."):
        if path_str == "...":
            return "..."
        clean_prefix = path_str[:-3]
        return f"{escape_p4_path(clean_prefix)}..."
    if os.path.isdir(path_str) or path_str.endswith("/"):
        clean = path_str.rstrip("/")
        return f"{escape_p4_path(clean)}/..."
    return escape_p4_path(path_str)


translate_path = to_p4_path


def find_workspace_root():
    """Locates the root directory containing .gfp, queries p4 info for Client root, or falls back to cwd."""
    curr = Path.cwd().resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".gfp").is_dir():
            return parent

    try:
        res = subprocess.run(
            ["p4", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            **TEXT_MODE,
        )
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                if line.startswith("Client root:"):
                    root_val = line.split(":", 1)[1].strip()
                    if root_val and root_val.lower() != "null":
                        p = Path(root_val)
                        if p.is_dir():
                            return p.resolve()
    except Exception:
        pass

    return curr


def run_pager(text):
    """
    Routes text through the system pager if in an interactive TTY, else prints directly.
    Honors $PAGER or defaults to 'less -FR' to cleanly use the alternate screen buffer.
    """
    if text is None:
        return
    if sys.stdout.isatty():
        pager_cmd = os.environ.get("PAGER") or "less -R"
        try:
            cmd_args = shlex.split(pager_cmd)
            subprocess.run(cmd_args, input=text, **TEXT_MODE)
            return
        except (BrokenPipeError, KeyboardInterrupt):
            return
        except Exception:
            pass
    print(text)


__all__ = [
    "TEXT_MODE",
    "ENTER_ALT_SCREEN",
    "EXIT_ALT_SCREEN",
    "HIDE_CURSOR",
    "SHOW_CURSOR",
    "COLOR_RESET",
    "COLOR_BOLD",
    "COLOR_RED",
    "COLOR_GREEN",
    "COLOR_YELLOW",
    "COLOR_BLUE",
    "COLOR_MAGENTA",
    "COLOR_CYAN",
    "COLOR_WHITE",
    "alternate_screen",
    "get_active_client",
    "get_user",
    "get_p4port",
    "get_active_stream",
    "resolve_stream_path",
    "escape_p4_path",
    "unescape_p4_path",
    "to_p4_path",
    "translate_path",
    "find_workspace_root",
    "run_pager",
]
