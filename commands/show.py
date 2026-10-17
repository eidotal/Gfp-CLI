import re
import sys
from pathlib import Path

try:
    from utils import get_active_client, get_user, run_pager
except ImportError:
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from utils import get_active_client, get_user, run_pager

COMMAND_NAME = "show"
HELP = "Show changelist details and unified diff (p4 describe -du)"


def setup_parser(parser):
    parser.add_argument(
        "cl",
        nargs="?",
        default=None,
        help="Changelist number (defaults to latest changelist)",
    )
    parser.add_argument(
        "--stat",
        "-s",
        action="store_true",
        help="Show summary of affected files without full diff (p4 describe -s)",
    )


def execute(args, run_p4, run_cmd=None, **kwargs):
    cl_id = args.cl
    if not cl_id:
        pending_cl = None
        try:
            client = kwargs.get("client") or kwargs.get("get_active_client", get_active_client)(run_p4)
            changes_args = ["changes", "-s", "pending"]
            if client:
                changes_args.extend(["-c", client])
            else:
                user = kwargs.get("user") or kwargs.get("get_user", get_user)(run_p4)
                if user:
                    changes_args.extend(["-u", user])
            changes_args.extend(["-m", "1"])
            pending_out = run_p4(changes_args, capture=True, check=False)
            if pending_out:
                p_match = re.search(r"Change\s+(\d+)", pending_out.strip().splitlines()[0])
                if p_match:
                    pending_cl = int(p_match.group(1))
        except Exception:
            pass

        submitted_cl = None
        try:
            sub_out = run_p4(
                ["changes", "-m", "1", "-s", "submitted", "..."],
                capture=True,
                check=False,
            )
            if sub_out:
                s_match = re.search(r"Change\s+(\d+)", sub_out.strip().splitlines()[0])
                if s_match:
                    submitted_cl = int(s_match.group(1))
        except Exception:
            pass

        if pending_cl is not None and submitted_cl is not None:
            cl_id = str(max(pending_cl, submitted_cl))
        elif pending_cl is not None:
            cl_id = str(pending_cl)
        elif submitted_cl is not None:
            cl_id = str(submitted_cl)

    if not cl_id:
        sys.stderr.write("Error: No changelist specified and unable to determine latest changelist.\n")
        raise SystemExit(1)

    cl_id = str(cl_id)

    # Detect shelved files so we can pass -S to p4 describe for pending shelved CLs.
    shelf_probe = run_p4(["describe", "-s", "-S", cl_id], capture=True, check=False)
    has_shelf = bool(re.search(r"^Shelved files", shelf_probe or "", re.MULTILINE))

    stat_flags = ["-s", "-S"] if has_shelf else ["-s"]
    diff_flags = ["-du", "-S"] if has_shelf else ["-du"]

    if args.stat:
        out = run_p4(["describe"] + stat_flags + [cl_id], capture=True, check=False)
    else:
        out = run_p4(["describe"] + diff_flags + [cl_id], capture=True, check=False)

    if out:
        run_pager(out)
