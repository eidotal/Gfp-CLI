import os
import re
import subprocess
import sys
from typing import Any, Dict

TEXT_MODE: Dict[str, Any] = {"text": True} if sys.version_info >= (3, 7) else {"universal_newlines": True}

COMMAND_NAME = "commit"
HELP = "Create a numbered changelist with a commit message"


def setup_parser(parser):
    parser.add_argument(
        "files",
        nargs="*",
        default=[],
        help="Optional specific files to include in the commit",
    )
    parser.add_argument("-m", "--message", default=None, help="Commit/changelist description")
    parser.add_argument(
        "--amend",
        action="store_true",
        help="Amend existing pending changelist description or include newly opened files",
    )
    parser.add_argument("-c", "--cl", default=None, help="Specific pending changelist ID to amend")
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Stage all changes before commit (p4 reconcile ...)",
    )


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


def apply_description_and_save(spec_template, message, strip_files=False):
    """Replaces the Description field in a change spec (optionally stripping Files) and submits via p4 change -i."""
    lines = spec_template.splitlines()
    new_spec = []
    skip_desc = False
    skip_files = False
    for line in lines:
        if strip_files and line.startswith("Files:"):
            skip_files = True
            continue
        elif skip_files:
            if line.startswith("\t") or line.strip() == "":
                continue
            else:
                skip_files = False

        if line.startswith("Description:"):
            new_spec.append("Description:")
            desc_lines = [f"\t{msg_line}" for msg_line in message.splitlines()] if message.splitlines() else ["\t"]
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
    try:
        res = subprocess.run(
            ["p4", "change", "-i"],
            input=final_spec,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            **TEXT_MODE,
        )
        return res.stdout.strip()
    except subprocess.CalledProcessError as err:
        if err.stderr:
            sys.stderr.write(err.stderr)
        elif err.stdout:
            sys.stderr.write(err.stdout)
        raise SystemExit(err.returncode)


def execute(args, run_p4, run_cmd=None, to_p4_path=None, **kwargs):
    def _default_to_p4_path(p):
        if not p or p in (".", "./"):
            return "..."
        # Escape Perforce special characters before path expansion
        escaped = p.replace("%", "%25").replace("@", "%40").replace("#", "%23").replace("*", "%2A")
        if os.path.isdir(p) or p.endswith("/"):
            return f"{escaped.rstrip('/')}/..."
        return escaped

    converter = to_p4_path or kwargs.get("to_p4_path") or _default_to_p4_path
    selected_targets = [converter(f) for f in args.files] if getattr(args, "files", None) else None

    if getattr(args, "all", False):
        run_p4(["reconcile", "-f", "..."], capture=False)
    elif selected_targets:
        run_p4(["reconcile", "-f"] + selected_targets, capture=True, check=False)
        if args.files:
            special_files = [f for f in args.files if any(c in f for c in ("@", "#", "%", "*")) and os.path.isfile(f)]
            if special_files:
                run_p4(["add", "-f"] + special_files, capture=True, check=False)

    if getattr(args, "amend", False):
        cl_id = str(args.cl) if getattr(args, "cl", None) else None
        if not cl_id:
            changes_args = ["changes", "-s", "pending"]
            client = get_active_client(run_p4)
            if client:
                changes_args.extend(["-c", client])
            changes_args.extend(["-m", "1"])
            changes_out = run_p4(changes_args, capture=True, check=False)
            if changes_out:
                match = re.search(r"Change\s+(\d+)", changes_out.strip().splitlines()[0])
                if match:
                    cl_id = match.group(1)

        if not cl_id:
            sys.stderr.write("Error: No pending changelist found to amend.\n")
            sys.exit(1)

        reopen_targets = selected_targets if selected_targets else ["..."]
        run_p4(["reopen", "-c", str(cl_id)] + reopen_targets, capture=False, check=False)

        if getattr(args, "message", None):
            spec_template = run_p4(["change", "-o", str(cl_id)])
            apply_description_and_save(spec_template, args.message)

        print(f"Amended pending changelist {cl_id}.")
        return

    if not getattr(args, "message", None):
        sys.stderr.write("Error: -m / --message is required for new commits.\n")
        sys.exit(1)

    if selected_targets:
        # Pre-validate: ensure all target files are opened before creating a CL
        opened_all = run_p4(["opened"], capture=True, check=False)
        opened_depot_paths = set()
        if opened_all:
            for _line in opened_all.splitlines():
                if "#" in _line:
                    opened_depot_paths.add(_line.split("#", 1)[0].strip())

        invalid_targets = []
        for t in selected_targets:
            # Accept wildcards (...) without validation
            if t.endswith("..."):
                continue
            norm_t = os.path.normpath(t).replace("\\", "/")
            while norm_t.startswith("./"):
                norm_t = norm_t[2:]
            clean_suffix = "/" + norm_t.lstrip("/")

            is_open = any(dp == norm_t or dp == t or dp.endswith(clean_suffix) for dp in opened_depot_paths)
            if not is_open:
                # Fallback: query p4 opened directly for complex client views or symlinks
                single_check = run_p4(["opened", t], capture=True, check=False)
                if single_check and "#" in single_check and "not opened" not in single_check:
                    is_open = True

            if not is_open:
                invalid_targets.append(t)

        if invalid_targets:
            sys.stderr.write("error: the following files are not opened in any changelist:\n")
            for _t in invalid_targets:
                sys.stderr.write(f"  {_t}\n")
            sys.stderr.write("Run 'gfp add <file>' or 'gfp status' to see opened files.\n")
            raise SystemExit(1)

        spec_template = run_p4(["change", "-o"])
        out = apply_description_and_save(spec_template, args.message, strip_files=True)
        match = re.search(r"Change\s+(\d+)", out)
        if match:
            cl_id = match.group(1)
            try:
                run_p4(
                    ["reopen", "-c", str(cl_id)] + selected_targets,
                    capture=False,
                    check=True,
                )
                print(f"Created pending changelist {cl_id} with specified files.")
            except (SystemExit, Exception):
                # Clean up dangling empty changelist on reopen failure
                run_p4(["change", "-d", str(cl_id)], capture=True, check=False)
                raise
        print(out)
        return

    opened = run_p4(["opened"])
    if not opened:
        print("Nothing to commit (working tree clean, no files opened).")
        return

    spec_template = run_p4(["change", "-o"])
    out = apply_description_and_save(spec_template, args.message, strip_files=False)

    match = re.search(r"Change\s+(\d+)", out)
    if match:
        cl_id = match.group(1)
        print(f"Created pending changelist {cl_id}.")
    print(out)
