import os
from pathlib import Path

COMMAND_NAME = "clean"
HELP = "Remove untracked and unreconciled files from the workspace"


def setup_parser(parser):
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force deletion/cleaning of untracked files",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Dry run: preview files to remove without actually modifying workspace",
    )
    parser.add_argument(
        "-d",
        action="store_true",
        help="Remove untracked directories in addition to untracked files",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="Optional files or directory paths to clean (defaults to '...')",
    )


def execute(args, run_p4, run_cmd=None, **kwargs):
    converter = kwargs.get("to_p4_path") or (lambda p: p)
    cmd = ["clean"]
    if args.dry_run or not args.force:
        cmd.append("-n")
    # Note: Do NOT append "-d" to p4 clean. In Perforce, p4 clean -d means
    # "reconcile deleted files" (restoring missing files from depot), NOT directories!

    targets = [converter(p) for p in args.paths] if args.paths else ["..."]
    cmd.extend(targets)

    if not args.force and not args.dry_run:
        print("Dry run preview (use -f / --force to execute clean):")

    run_p4(cmd, capture=False)

    # If -d (remove untracked directories) is requested with -f (force) and not dry-run:
    if args.d and args.force and not args.dry_run:
        root_dir = kwargs.get("workspace_root") or Path.cwd()
        target_dirs = [Path(p).resolve() for p in args.paths if Path(p).is_dir()] if args.paths else [Path(root_dir).resolve()]
        for base in target_dirs:
            if not base.exists():
                continue
            for root, dirs, files in os.walk(str(base), topdown=False):
                p_root = Path(root)
                if p_root == Path(root_dir).resolve():
                    continue
                if any(part in (".gfp", ".git") for part in p_root.parts):
                    continue
                try:
                    if not any(p_root.iterdir()):
                        p_root.rmdir()
                except OSError:
                    pass
