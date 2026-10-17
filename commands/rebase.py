import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict

TEXT_MODE: Dict[str, Any] = {"text": True} if sys.version_info >= (3, 7) else {"universal_newlines": True}

COMMAND_NAME = "rebase"
HELP = "Rebase, squash, or interactively manipulate pending changelists"


def get_active_client(run_p4):
    """Resolves active Perforce client workspace name via env, p4 set, or p4 info."""
    p4client = os.environ.get("P4CLIENT")
    if p4client:
        return p4client.strip()

    try:
        p4_set_out = run_p4(["set", "P4CLIENT"], capture=True, check=False)
        if p4_set_out:
            for line in p4_set_out.splitlines():
                if line.startswith("P4CLIENT="):
                    val = line.split("=", 1)[1].split()[0].strip()
                    if val:
                        return val
    except Exception:
        pass

    try:
        p4_info_out = run_p4(["info"], capture=True, check=False)
        if p4_info_out:
            for line in p4_info_out.splitlines():
                if line.startswith("Client name:"):
                    val = line.split(":", 1)[1].strip()
                    if val:
                        return val
    except Exception:
        pass

    return None


def get_cl_description(cl_id, run_p4):
    """Extracts description text from a changelist specification."""
    spec = run_p4(["change", "-o", str(cl_id)], capture=True, check=False)
    if not spec:
        return ""
    lines = spec.splitlines()
    in_desc = False
    desc_lines = []
    for line in lines:
        if line.startswith("Description:"):
            in_desc = True
            continue
        if in_desc:
            if line.startswith("\t"):
                desc_lines.append(line[1:])
            elif line.startswith("Files:") or (line and not line.startswith(" ") and not line.startswith("\t")):
                break
    return "\n".join(desc_lines).strip()


def set_cl_description(cl_id, description, run_p4):
    """Updates description of a changelist spec via p4 change -i."""
    spec = run_p4(["change", "-o", str(cl_id)], capture=True, check=True)
    lines = spec.splitlines()
    new_spec = []
    skip_desc = False
    for line in lines:
        if line.startswith("Description:"):
            new_spec.append("Description:")
            desc_lines = [f"\t{desc_line}" for desc_line in description.splitlines()] if description.splitlines() else ["\t"]
            new_spec.extend(desc_lines)
            skip_desc = True
        elif skip_desc:
            if line.startswith("\t") or line.strip() == "":
                continue
            else:
                skip_desc = False
                new_spec.append(line)
        else:
            new_spec.append(line)

    final_spec = "\n".join(new_spec) + "\n"
    res = subprocess.run(
        ["p4", "change", "-i"],
        input=final_spec,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        **TEXT_MODE,
    )
    return res.stdout.strip()


def squash_cl(source_cl, target_cl, message, run_p4):
    """Squashes source pending changelist into target changelist."""
    source_cl = str(source_cl)
    target_cl = str(target_cl)

    if source_cl == target_cl:
        sys.stderr.write("Error: Source and target changelists cannot be the same.\n")
        sys.exit(1)

    source_desc = get_cl_description(source_cl, run_p4)
    target_desc = get_cl_description(target_cl, run_p4)

    # 1. Query opened files in source_cl
    opened_out = run_p4(["opened", "-c", source_cl], capture=True, check=False)
    if opened_out and opened_out.strip():
        source_files = []
        for line in opened_out.strip().splitlines():
            if "#" in line:
                source_files.append(line.split("#", 1)[0].strip())
        if source_files:
            run_p4(["reopen", "-c", target_cl] + source_files, capture=False, check=True)

    # 2. Delete any shelved revisions in source_cl
    run_p4(["shelve", "-d", "-c", source_cl], capture=True, check=False)

    # 3. Update target_cl description
    if message:
        combined_desc = message.strip()
    else:
        combined_desc = f"{target_desc}\n\n[Squashed CL {source_cl}]: {source_desc}".strip()
    set_cl_description(target_cl, combined_desc, run_p4)

    # 4. Delete source_cl
    run_p4(["change", "-d", source_cl], capture=False, check=True)
    print(f"Successfully squashed pending changelist {source_cl} onto {target_cl}.")


def get_pending_cls(client, run_p4):
    """Retrieves list of pending changelist tuples (cl_id, desc_summary)."""
    cmd = ["changes", "-s", "pending"]
    if client and client != "default":
        cmd.extend(["-c", client])
    out = run_p4(cmd, capture=True, check=False)
    cls = []
    if out and out.strip():
        for line in out.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.search(r"\bChange\s+(\d+)\b(.*)$", line)
            if match:
                cl_id = match.group(1)
                summary = match.group(2).strip()
                cls.append((cl_id, summary))
    return cls


def run_interactive_rebase(client, run_p4):
    """Runs interactive pending changelist manipulation."""
    pending = get_pending_cls(client, run_p4)
    if not pending:
        print(f"No pending changelists found for workspace '{client}'.")
        return

    # Sort oldest to newest (ascending)
    pending.reverse()

    todo_lines = [
        "# GFP Interactive Rebase",
        "#",
        "# Commands:",
        "# p, pick <CL>   = keep changelist as is",
        "# r, reword <CL> = edit changelist message",
        "# s, squash <CL> = squash into previous changelist",
        "# d, drop <CL>   = revert files and delete changelist",
        "#",
    ]
    for cl_id, summary in pending:
        todo_lines.append(f"pick {cl_id} {summary}")

    with tempfile.NamedTemporaryFile(mode="w+", suffix="_rebase_todo.txt", delete=False, encoding="utf-8") as tf:
        tf.write("\n".join(todo_lines) + "\n")
        temp_path = tf.name

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))
    # If in non-interactive environment and editor not explicitly set to valid binary
    if not sys.stdin.isatty():
        print("Non-interactive terminal detected; pending changelists:")
        for cl_id, summary in pending:
            print(f"  CL {cl_id}: {summary}")
        os.unlink(temp_path)
        return

    try:
        subprocess.run([editor, temp_path], check=True)
    except Exception as ex:
        sys.stderr.write(f"Error launching editor '{editor}': {ex}\n")
        os.unlink(temp_path)
        sys.exit(1)

    with open(temp_path, "r", encoding="utf-8") as f:
        edited_content = f.read()
    os.unlink(temp_path)

    # Process instructions
    instructions = []
    for line in edited_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        action = parts[0].lower()
        cl_id = parts[1] if len(parts) > 1 else None
        if action and cl_id:
            instructions.append((action, cl_id))

    prev_cl = None
    for action, cl_id in instructions:
        if action in ("p", "pick"):
            print(f"Keeping CL {cl_id}.")
            prev_cl = cl_id
        elif action in ("r", "reword"):
            cur_desc = get_cl_description(cl_id, run_p4)
            with tempfile.NamedTemporaryFile(mode="w+", suffix="_reword.txt", delete=False, encoding="utf-8") as rf:
                rf.write(cur_desc + "\n")
                reword_path = rf.name
            try:
                subprocess.run([editor, reword_path], check=True)
                with open(reword_path, "r", encoding="utf-8") as f:
                    new_desc = f.read().strip()
                if new_desc:
                    set_cl_description(cl_id, new_desc, run_p4)
                    print(f"Reworded CL {cl_id}.")
            finally:
                if os.path.exists(reword_path):
                    os.unlink(reword_path)
            prev_cl = cl_id
        elif action in ("s", "squash"):
            if not prev_cl:
                sys.stderr.write(f"Error: Cannot squash first changelist {cl_id}.\n")
                continue
            squash_cl(cl_id, prev_cl, None, run_p4)
        elif action in ("d", "drop"):
            run_p4(["revert", "-c", cl_id, "..."], capture=False, check=False)
            run_p4(["shelve", "-d", "-c", cl_id], capture=True, check=False)
            run_p4(["change", "-d", cl_id], capture=False, check=True)
            print(f"Dropped changelist {cl_id}.")


def setup_parser(parser):
    parser.add_argument(
        "-s",
        "--squash",
        default=None,
        help="Source pending changelist ID to squash",
    )
    parser.add_argument(
        "--onto",
        default=None,
        help="Target pending changelist ID to receive squashed files and description",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactively inspect, reorder, reword, squash, or drop pending changelists",
    )
    parser.add_argument(
        "-m",
        "--message",
        default=None,
        help="New commit description when squashing changelists",
    )


def execute(args, run_p4, **kwargs):
    client = get_active_client(run_p4)

    if args.squash:
        if not args.onto:
            sys.stderr.write("Error: --onto <target_cl> is required when using --squash.\n")
            sys.exit(1)
        squash_cl(args.squash, args.onto, args.message, run_p4)
    elif args.interactive:
        run_interactive_rebase(client, run_p4)
    else:
        sys.stderr.write("Usage: gfp rebase --squash <source_cl> --onto <target_cl> [-m msg]\n   or: gfp rebase -i\n")
        sys.exit(1)
