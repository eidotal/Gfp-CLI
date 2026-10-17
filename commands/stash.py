import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict

TEXT_MODE: Dict[str, Any] = {"text": True} if sys.version_info >= (3, 7) else {"universal_newlines": True}

COMMAND_NAME = "stash"
HELP = "Shelve or unshelve working changes"


def get_client_name(run_p4):
    """Returns the Perforce client/workspace name via env, p4 set, or p4 info."""
    client = os.environ.get("P4CLIENT")
    if client:
        return client.strip()
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
        info = run_p4(["info"], capture=True, check=False)
        if info:
            for line in info.splitlines():
                if line.startswith("Client name:"):
                    val = line.split(":", 1)[1].strip()
                    if val:
                        return val
    except Exception:
        pass
    return None


def get_latest_shelved_cl(run_p4, client=None):
    """Finds the most recent shelved changelist ID for the client."""
    cmd = ["changes", "-s", "shelved", "-m", "1"]
    if client:
        cmd.extend(["-c", client])
    try:
        out = run_p4(cmd, capture=True, check=True)
        match = re.search(r"Change\s+(\d+)", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def setup_parser(parser):
    parser.add_argument(
        "action",
        nargs="?",
        choices=["save", "pop", "list", "drop", "show"],
        default="save",
        help="Stash action: save (default), pop, list, drop, show",
    )
    parser.add_argument(
        "-m",
        "--message",
        default=None,
        help="Stash description message",
    )
    parser.add_argument(
        "-c",
        "--cl",
        default=None,
        help="Specific changelist ID to operate on",
    )
    parser.add_argument(
        "-k",
        "--keep",
        action="store_true",
        help="Keep opened files in workspace after shelving (do not revert)",
    )


def execute(args, run_p4, run_cmd=None, **kwargs):
    if args.action == "save":
        cl_id = args.cl
        if cl_id:
            cl_id = str(cl_id)
            print(f"Shelving changelist {cl_id}...")
            run_p4(["shelve", "-c", cl_id], capture=False)
            if args.keep:
                run_p4(["revert", "-k", "-c", cl_id, "..."], capture=False)
            else:
                run_p4(["revert", "-c", cl_id, "..."], capture=False)
            return

        opened = run_p4(["opened"], capture=True, check=False)
        if not opened:
            print("No local changes to stash (no files opened).")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if args.message:
            desc = f"Stash: {timestamp} [{args.message}]"
        else:
            desc = f"Stash: {timestamp}"

        spec_template = run_p4(["change", "-o"])
        lines = spec_template.splitlines()
        new_spec = []
        skip_desc = False
        for line in lines:
            if line.startswith("Description:"):
                new_spec.append("Description:")
                new_spec.append(f"\t{desc}")
                skip_desc = True
            elif skip_desc and line.startswith("\t"):
                continue
            else:
                skip_desc = False
                new_spec.append(line)

        final_spec = "\n".join(new_spec)
        proc = subprocess.Popen(
            ["p4", "change", "-i"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **TEXT_MODE,
        )
        out, err = proc.communicate(input=final_spec)
        if proc.returncode != 0:
            if err:
                sys.stderr.write(err)
            raise SystemExit(proc.returncode)

        match = re.search(r"Change\s+(\d+)\s+created", out)
        if not match:
            sys.stderr.write(f"Error: Failed to create changelist for stash:\n{out}\n")
            raise SystemExit(1)

        cl_id = match.group(1)
        print(f"Created pending changelist {cl_id} for stash.")

        # Shelve the changelist
        run_p4(["shelve", "-c", cl_id], capture=False)

        # Revert the local opened files
        if args.keep:
            run_p4(["revert", "-k", "-c", cl_id, "..."], capture=False)
        else:
            run_p4(["revert", "-c", cl_id, "..."], capture=False)

        print(f"Saved working directory and index state to stash {cl_id}.")

    elif args.action == "list":
        client = get_client_name(run_p4)
        cmd = ["changes", "-s", "shelved"]
        if client:
            cmd.extend(["-c", client])
        run_p4(cmd, capture=False)

    elif args.action == "pop":
        cl_id = args.cl
        if not cl_id:
            client = get_client_name(run_p4)
            cl_id = get_latest_shelved_cl(run_p4, client)
            if not cl_id:
                sys.stderr.write("Error: No shelved changelists found to pop.\n")
                raise SystemExit(1)

        cl_id = str(cl_id)
        print(f"Unshelving stash changelist {cl_id}...")
        run_p4(["unshelve", "-s", cl_id], capture=False)

        print(f"Deleting shelf for changelist {cl_id}...")
        run_p4(["shelve", "-d", "-c", cl_id], capture=False)

        # Reopen files in default changelist and delete empty pending changelist
        opened = run_p4(["opened", "-c", cl_id], capture=True, check=False)
        if opened:
            files = [line.split("#")[0].strip() for line in opened.splitlines() if "#" in line]
            if files:
                run_p4(["reopen", "-c", "default"] + files, capture=True, check=False)

        run_p4(["change", "-d", cl_id], capture=True, check=False)
        print(f"Restored stash {cl_id} into working tree.")

    elif args.action == "drop":
        cl_id = args.cl
        if not cl_id:
            client = get_client_name(run_p4)
            cl_id = get_latest_shelved_cl(run_p4, client)
            if not cl_id:
                sys.stderr.write("Error: Specify changelist ID with --cl or ensure a shelved changelist exists.\n")
                raise SystemExit(1)

        cl_id = str(cl_id)
        print(f"Deleting shelf for changelist {cl_id}...")
        run_p4(["shelve", "-d", "-c", cl_id], capture=False)
        print(f"Deleting pending changelist {cl_id}...")
        run_p4(["change", "-d", cl_id], capture=False)
        print(f"Dropped stash changelist {cl_id}.")

    elif args.action == "show":
        cl_id = args.cl
        if not cl_id:
            client = get_client_name(run_p4)
            cl_id = get_latest_shelved_cl(run_p4, client)
            if not cl_id:
                sys.stderr.write("Error: Specify changelist ID with --cl or ensure a shelved changelist exists.\n")
                raise SystemExit(1)

        cl_id = str(cl_id)
        run_p4(["describe", "-du", "-S", cl_id], capture=False, check=False)
