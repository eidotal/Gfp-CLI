import sys
from pathlib import Path

try:
    from utils import to_p4_path
except ImportError:
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from utils import to_p4_path

COMMAND_NAME = "pull"
HELP = "Sync latest revisions and resolve safe conflicts"


def setup_parser(parser):
    parser.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="Optional files or directory paths to sync and resolve",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force re-sync of files (p4 sync -f)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Dry run preview of revisions to sync (p4 sync -n)",
    )


def execute(args, run_p4, **kwargs):
    converter = kwargs.get("to_p4_path") or to_p4_path
    target_paths = [converter(p) for p in args.paths] if getattr(args, "paths", None) else []

    sync_cmd = ["sync"]
    if getattr(args, "force", False):
        sync_cmd.append("-f")
    if getattr(args, "dry_run", False):
        sync_cmd.append("-n")
    if target_paths:
        sync_cmd.extend(target_paths)

    if getattr(args, "dry_run", False):
        print("Previewing revisions to sync (dry run)...")
        run_p4(sync_cmd, capture=False)
        return

    print("Syncing workspace from depot...")
    run_p4(sync_cmd, capture=False)
    print("Resolving non-conflicting changes...")
    resolve_cmd = ["resolve", "-am"]
    if target_paths:
        resolve_cmd.extend(target_paths)
    resolve_out = run_p4(resolve_cmd, capture=True, check=False)
    if resolve_out:
        print(resolve_out)

    # Detect files that could not be auto-merged
    unresolved = []
    if resolve_out:
        for line in resolve_out.splitlines():
            line_lower = line.lower()
            if "resolve skipped" in line_lower or "unresolved" in line_lower:
                # Extract the depot path from lines like:
                # //depot/path/file - resolve skipped
                parts = line.split(" - ", 1)
                if parts[0].strip():
                    unresolved.append(parts[0].strip())
    if unresolved:
        sys.stderr.write("\nwarning: the following files could not be auto-resolved and require manual resolution:\n")
        for f in unresolved:
            sys.stderr.write(f"  {f}\n")
        sys.stderr.write("Run 'gfp resolve' to resolve conflicts interactively.\n")
