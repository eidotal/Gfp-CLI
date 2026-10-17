import os

COMMAND_NAME = "reopen"
HELP = "Move opened files between changelists (p4 reopen)"


def setup_parser(parser):
    parser.add_argument(
        "files",
        nargs="*",
        default=[],
        help="Files to move between changelists",
    )
    parser.add_argument(
        "-c",
        "--cl",
        default="default",
        help="Target changelist ID (default: default)",
    )


def execute(args, run_p4, run_cmd=None, to_p4_path=None, **kwargs):
    def _default_to_p4_path(path_str):
        if not path_str or path_str in (".", "./"):
            return "..."
        if path_str == "..." or path_str.endswith("/...") or path_str.endswith("..."):
            return path_str
        if os.path.isdir(path_str) or path_str.endswith("/"):
            return f"{path_str.rstrip('/')}/..."
        return path_str

    path_converter = to_p4_path or kwargs.get("to_p4_path") or _default_to_p4_path

    if not args.files:
        targets = ["..."]
    else:
        targets = [path_converter(f) for f in args.files]

    target_cl = str(args.cl) if args.cl is not None else "default"
    run_p4(["reopen", "-c", target_cl] + targets, capture=False)
