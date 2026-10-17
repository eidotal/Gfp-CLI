import os
import re
import sys
from pathlib import Path

try:
    from utils import run_pager
except ImportError:
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from utils import run_pager

COMMAND_NAME = "log"
HELP = "Display changelist history"


def translate_path(path_str):
    """Translates git-style paths (., ./, dir, dir/) into Perforce wildcards (dir/...)."""
    if not path_str or path_str in (".", "./"):
        return "..."
    if path_str == "..." or path_str.endswith("/...") or path_str.endswith("..."):
        return path_str
    if path_str.endswith("/") or os.path.isdir(path_str):
        clean = path_str.rstrip("/")
        return f"{clean}/..." if clean else "..."
    return path_str


def setup_parser(parser):
    parser.add_argument(
        "path",
        nargs="?",
        default="...",
        help="Optional file or directory path to view history for (default: ...)",
    )
    parser.add_argument("-n", "--max-count", default=None, type=int, help="Number of changes to show")
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Display full changelist history without truncation (uses p4 changes -L)",
    )
    parser.add_argument(
        "--oneline",
        action="store_true",
        help="Compact one-line format for changelist history",
    )
    parser.add_argument(
        "-p",
        "--patch",
        action="store_true",
        help="Show unified diff/patch for each changelist",
    )
    parser.add_argument(
        "-u",
        "--user",
        "--author",
        dest="user",
        default=None,
        help="Filter changelist history by author/user",
    )


def execute(args, run_p4, **kwargs):
    converter = kwargs.get("to_p4_path") or translate_path
    if args.max_count is not None:
        limit = str(args.max_count)
    elif getattr(args, "all", False):
        limit = None
    else:
        limit = "10"

    target = [converter(args.path)] if args.path else ["..."]

    output_text = None
    if args.patch:
        cmd = ["changes"]
        if limit:
            cmd.extend(["-m", limit])
        if args.user:
            cmd.extend(["-u", args.user])
        cmd.extend(target)
        history = run_p4(cmd, capture=True, check=False)
        patches = []
        if history:
            for line in history.splitlines():
                match = re.search(r"\bChange\s+(\d+)\b", line)
                if match:
                    cl_id = match.group(1)
                    desc = run_p4(["describe", "-du", cl_id], capture=True, check=False)
                    if desc and desc.strip():
                        patches.append(desc.strip())
        if patches:
            output_text = "\n\n".join(patches)
    elif args.oneline:
        cmd = ["changes"]
        if limit:
            cmd.extend(["-m", limit])
        if args.user:
            cmd.extend(["-u", args.user])
        cmd.extend(["-s", "submitted"] + target)
        history = run_p4(cmd, capture=True, check=False)
        if history and history.strip():
            output_text = history.strip()
    else:
        desc_flag = "-L" if getattr(args, "all", False) else "-l"
        cmd = ["changes"]
        if limit:
            cmd.extend(["-m", limit])
        if args.user:
            cmd.extend(["-u", args.user])
        cmd.extend([desc_flag] + target)
        history = run_p4(cmd, capture=True, check=False)
        if history and history.strip():
            output_text = history.strip()

    if output_text:
        run_pager(output_text)
