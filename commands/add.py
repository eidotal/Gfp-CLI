import os

COMMAND_NAME = "add"
HELP = "Stage/open files for add, edit, or delete"


def setup_parser(parser):
    parser.add_argument(
        "files",
        nargs="*",
        default=[],
        help="Files or directories to add/reconcile",
    )
    parser.add_argument(
        "-A",
        "--all",
        action="store_true",
        help="Stage all changes across the entire workspace (reconcile ...)",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="Stage modified and deleted files (reconcile -e -d)",
    )


def execute(args, run_p4, run_cmd=None, to_p4_path=None, **kwargs):
    def _default_to_p4_path(path_str):
        if path_str in (".", "./"):
            return "..."
        if os.path.isdir(path_str) or path_str.endswith("/"):
            return f"{path_str.rstrip('/')}/..."
        return path_str

    path_converter = to_p4_path or kwargs.get("to_p4_path") or _default_to_p4_path

    if getattr(args, "all", False):
        target_paths = ["..."]
    elif args.files:
        target_paths = [path_converter(f) for f in args.files]
    elif getattr(args, "update", False):
        target_paths = ["..."]
    else:
        print("Nothing specified, nothing added.\nMaybe you wanted to say 'gfp add .' or 'gfp add -A'?")
        return

    cmd = ["reconcile", "-f"]
    if getattr(args, "update", False):
        cmd.extend(["-e", "-d"])
    cmd.extend(target_paths)

    run_p4(cmd, capture=False)

    if args.files and not getattr(args, "update", False):
        special_files = [f for f in args.files if any(c in f for c in ("@", "#", "%", "*")) and os.path.isfile(f)]
        if special_files:
            run_p4(["add", "-f"] + special_files, capture=True, check=False)
