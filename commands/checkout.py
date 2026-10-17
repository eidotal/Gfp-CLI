import os

COMMAND_NAME = "checkout"
HELP = "Discard local modifications (p4 revert)"


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
        "-f",
        "--force",
        action="store_true",
        help="Reconcile unopened local modifications first before reverting",
    )
    parser.add_argument(
        "files",
        nargs="*",
        default=[],
        help="Files or directories to revert back to depot state (default: ...)",
    )


def execute(args, run_p4, **kwargs):
    converter = kwargs.get("to_p4_path") or translate_path
    if not args.files:
        targets = ["..."]
    else:
        targets = [converter(f) for f in args.files]

    if args.force:
        # Reconcile first to capture unopened workspace modifications/deletions
        run_p4(["reconcile", "-w"] + targets, capture=False, check=False)

    run_p4(["revert"] + targets, capture=False)
