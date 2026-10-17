import sys
from pathlib import Path

COMMAND_NAME = "completion"
HELP = "Generate shell autocompletion script (bash, zsh, tcsh)"


def setup_parser(parser):
    parser.add_argument(
        "shell",
        choices=["bash", "zsh", "tcsh"],
        help="Target shell for autocompletion (bash, zsh, tcsh)",
    )


def execute(args, run_p4, run_cmd=None, **kwargs):
    pkg_dir = Path(__file__).resolve().parent.parent
    completions_dir = pkg_dir / "completions"

    script_map = {
        "bash": completions_dir / "gfp.bash",
        "zsh": completions_dir / "_gfp",
        "tcsh": completions_dir / "gfp.tcsh",
    }

    target_file = script_map.get(args.shell)
    if not target_file or not target_file.is_file():
        sys.stderr.write(f"Error: Completion script for '{args.shell}' not found at {target_file}.\n")
        raise SystemExit(1)

    with open(target_file, "r", encoding="utf-8") as f:
        print(f.read().rstrip())
