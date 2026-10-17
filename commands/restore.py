import os

COMMAND_NAME = "restore"
HELP = "Restore working tree files or discard/delete pending changelists"


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
        "files",
        nargs="*",
        default=[],
        help="Files or directories to restore (default: ...)",
    )
    parser.add_argument(
        "-s",
        "--staged",
        action="store_true",
        help="Unstage files while keeping disk modifications (p4 revert -k)",
    )
    parser.add_argument(
        "-c",
        "--cl",
        default=None,
        help="Pending changelist ID to revert and delete",
    )
    parser.add_argument(
        "-k",
        "--keep",
        action="store_true",
        help="Keep disk modifications when reverting changelist files",
    )
    parser.add_argument(
        "-W",
        "--worktree",
        action="store_true",
        help="Discard working tree modifications (default when --staged is not set)",
    )


def execute(args, run_p4, run_cmd=None, to_p4_path=None, **kwargs):
    converter = to_p4_path or translate_path

    # Scenario 1: Restore / delete pending changelist
    if args.cl:
        cl_id = str(args.cl)
        # 1. Revert opened files in the changelist
        revert_args = ["revert"]
        if args.keep or args.staged:
            revert_args.append("-k")
        revert_args.extend(["-c", cl_id, "..."])
        run_p4(revert_args, capture=False, check=False)

        # 2. Delete any shelved files in this changelist
        run_p4(["shelve", "-d", "-c", cl_id], capture=True, check=False)

        # 3. Delete the changelist itself
        run_p4(["change", "-d", cl_id], capture=False, check=True)
        print(f"Deleted pending changelist {cl_id}.")
        return

    # Scenario 2: Restore files
    targets = [converter(f) for f in args.files] if args.files else ["..."]

    if args.staged:
        # Unstage files while keeping disk modifications
        run_p4(["revert", "-k"] + targets, capture=False)
    else:
        # Discard working tree modifications
        # 1. Restore unopened modified (-e) and missing (-d) files from depot
        run_p4(["clean", "-e", "-d"] + targets, capture=False, check=False)
        # 2. Revert opened files back to depot state
        run_p4(["revert"] + targets, capture=False, check=False)
