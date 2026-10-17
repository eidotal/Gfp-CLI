import os

COMMAND_NAME = "resolve"
HELP = "Resolve conflicts between workspace and depot revisions (p4 resolve)"


def translate_path(path_str):
    """Translates git-style paths and escapes Perforce special characters."""
    if not path_str or path_str in (".", "./"):
        return "..."
    if path_str == "..." or path_str.endswith("/...") or path_str.endswith("..."):
        return path_str
    escaped = path_str.replace("%", "%25").replace("@", "%40").replace("#", "%23").replace("*", "%2A")
    if path_str.endswith("/") or os.path.isdir(path_str):
        clean = escaped.rstrip("/")
        return f"{clean}/..." if clean else "..."
    return escaped


def setup_parser(parser):
    parser.add_argument(
        "files",
        nargs="*",
        default=[],
        help="Optional files or directories to resolve (default: ...)",
    )
    parser.add_argument(
        "--ours",
        action="store_true",
        help="Accept workspace version and ignore depot changes (p4 resolve -ay)",
    )
    parser.add_argument(
        "--theirs",
        action="store_true",
        help="Accept depot version and overwrite workspace changes (p4 resolve -at)",
    )
    parser.add_argument(
        "--am",
        action="store_true",
        help="Automatically resolve safe changes without conflicts (p4 resolve -am)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Preview what would be resolved without making changes (p4 resolve -n)",
    )


def execute(args, run_p4, run_cmd=None, to_p4_path=None, **kwargs):
    converter = to_p4_path or translate_path
    targets = [converter(f) for f in args.files] if args.files else ["..."]

    cmd = ["resolve"]

    if getattr(args, "dry_run", False):
        cmd.append("-n")

    if args.ours:
        cmd.append("-ay")
    elif args.theirs:
        cmd.append("-at")
    elif getattr(args, "am", False):
        cmd.append("-am")

    cmd.extend(targets)

    run_p4(cmd, capture=False, check=False)
