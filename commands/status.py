import re
from collections import defaultdict
from pathlib import Path

from utils import get_active_client, get_active_stream

COMMAND_NAME = "status"
HELP = "Show workspace status and opened changes"


def setup_parser(parser):
    parser.add_argument(
        "-c",
        "--cl",
        "--pending",
        dest="pending_cl",
        action="store_true",
        help="Display all workspace pending changelists with their opened and shelved files",
    )


def parse_opened_line(line):
    """Parses changelist identifier from a p4 opened line."""
    cl_match = re.search(r"\bchange\s+(\d+)\b", line)
    cl_id = cl_match.group(1) if cl_match else "default"
    return cl_id, line


def parse_reconcile_line(line):
    """
    Categorizes a preview line from 'p4 reconcile -n' or 'p4 status' into
    ('modified' | 'new' | 'deleted' | 'other', line) or (None, None) if ignorable.
    """
    if not line:
        return None, None
    stripped = line.strip()
    if not stripped or "no file(s) to reconcile" in stripped.lower():
        return None, None

    # Match 'p4 reconcile -n' output: '//depot/path#rev - opened for <action>'
    # or 'p4 status' output: 'local/path - reconcile to <action> //depot/path#rev'
    match = re.search(r"-\s+(?:opened for|reconcile to)\s+(\S+)", stripped)
    if match:
        action = match.group(1).lower()
        if action in ("edit", "integrate", "branch"):
            return "modified", stripped
        if action in ("add", "move/add"):
            return "new", stripped
        if action in ("delete", "move/delete"):
            return "deleted", stripped

    return "other", stripped


def get_shelved_files(cl_id, run_p4):
    """Extracts list of shelved files in a changelist."""
    out = run_p4(["describe", "-s", "-S", str(cl_id)], capture=True, check=False)
    shelved = []
    if out:
        in_shelved = False
        for line in out.splitlines():
            line_s = line.strip()
            if line_s.startswith("Shelved files"):
                in_shelved = True
                continue
            if in_shelved:
                if line_s.startswith("... //"):
                    shelved.append(line_s[4:].strip())
                elif line_s and not line_s.startswith("..."):
                    break
    return shelved


def execute(args, run_p4, **kwargs):
    client = get_active_client(run_p4)
    print(f"On Perforce workspace: {client}")
    stream = get_active_stream(run_p4)
    if stream:
        print(f"On stream: {stream}")
    else:
        print("Stream: none")

    show_detailed_pending = getattr(args, "pending_cl", False)

    if show_detailed_pending:
        # Detailed pending changelists view with opened and shelved files
        pending_cmd = ["changes", "-s", "pending"]
        if client and client != "default":
            pending_cmd.extend(["-c", client])

        pending_out = run_p4(pending_cmd, capture=True, check=False)
        if pending_out and pending_out.strip():
            print(f"\nPending changelists for workspace '{client}':")
            for line in pending_out.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                match = re.search(r"\bChange\s+(\d+)\b", line)
                cl_id = match.group(1) if match else None
                print(f"  {line}")

                if cl_id:
                    # Opened files in this changelist
                    opened_cl = run_p4(["opened", "-c", cl_id], capture=True, check=False)
                    has_files = False
                    if opened_cl and opened_cl.strip():
                        has_files = True
                        print("    Opened files:")
                        for o_line in opened_cl.strip().splitlines():
                            print(f"      (opened)  {o_line.strip()}")

                    # Shelved files in this changelist
                    shelved_files = get_shelved_files(cl_id, run_p4)
                    if shelved_files:
                        has_files = True
                        print("    Shelved files:")
                        for s_file in shelved_files:
                            print(f"      (shelved) {s_file}")

                    if not has_files:
                        print("    (no opened or shelved files)")
        else:
            print(f"\nNo pending changelists for workspace '{client}'.")
    else:
        opened = run_p4(["opened"], capture=True, check=False)
        if opened and opened.strip():
            opened_groups = defaultdict(list)
            for line in opened.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                cl_id, raw_line = parse_opened_line(line)
                opened_groups[cl_id].append(raw_line)

            print("\nChanges opened for commit:")
            if "default" in opened_groups:
                print("  Default Changelist:")
                for item in opened_groups["default"]:
                    print(f"    (opened)  {item}")

            numbered_keys = sorted(
                [k for k in opened_groups if k != "default"],
                key=lambda x: int(x) if x.isdigit() else x,
            )
            for cl_id in numbered_keys:
                print(f"  Changelist {cl_id}:")
                for item in opened_groups[cl_id]:
                    print(f"    (opened)  {item}")
        else:
            print("\nNo files currently opened.")

        # Pending changelists for current client
        pending_cmd = ["changes", "-s", "pending"]
        if client and client != "default":
            pending_cmd.extend(["-c", client])

        pending_out = run_p4(pending_cmd, capture=True, check=False)
        if pending_out and pending_out.strip():
            print(f"\nPending changelists for workspace '{client}':")
            for line in pending_out.strip().splitlines():
                print(f"  {line}")

    # Untracked / un-reconciled local changes across the entire workspace
    reconcile_target = "..."
    workspace_root = kwargs.get("workspace_root")
    if workspace_root:
        try:
            ws_path = Path(workspace_root).resolve()
            if ws_path != Path.cwd().resolve():
                reconcile_target = f"{ws_path}/..."
        except Exception:
            pass

    status_out = run_p4(
        ["reconcile", "-n", "-e", "-a", "-d", "-f", reconcile_target],
        capture=True,
        check=False,
    )
    if not status_out or not status_out.strip():
        status_out = run_p4(
            ["status", "-e", "-a", "-d", "-f", reconcile_target],
            capture=True,
            check=False,
        )

    if status_out and status_out.strip():
        modified_files = []
        new_files = []
        deleted_files = []
        other_files = []

        for line in status_out.strip().splitlines():
            category, formatted = parse_reconcile_line(line)
            if not category:
                continue
            if category == "modified":
                modified_files.append(formatted)
            elif category == "new":
                new_files.append(formatted)
            elif category == "deleted":
                deleted_files.append(formatted)
            else:
                other_files.append(formatted)

        if modified_files or new_files or deleted_files or other_files:
            print("\nUntracked / Un-reconciled local changes (use 'gfp add' to stage):")
            if modified_files:
                print("  Modified files:")
                for item in modified_files:
                    print(f"    (modified)  {item}")
            if new_files:
                print("  New / Untracked files:")
                for item in new_files:
                    print(f"    (new file)  {item}")
            if deleted_files:
                print("  Deleted files:")
                for item in deleted_files:
                    print(f"    (deleted)   {item}")
            if other_files:
                for item in other_files:
                    print(f"    {item}")
