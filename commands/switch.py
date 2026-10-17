import re
import subprocess
import sys
from pathlib import Path

try:
    from utils import TEXT_MODE, get_active_stream, resolve_stream_path
except ImportError:
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from utils import TEXT_MODE, get_active_stream, resolve_stream_path

COMMAND_NAME = "switch"
HELP = "Switch workspace to a different stream (p4 switch)"


def setup_parser(parser):
    parser.add_argument(
        "stream",
        nargs="?",
        default=None,
        help="Stream name or depot path to switch to",
    )
    parser.add_argument(
        "-c",
        "--create",
        action="store_true",
        help="Create new stream before switching",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List streams available for switching",
    )
    parser.add_argument(
        "-P",
        "--parent",
        default=None,
        help="Parent stream path when creating",
    )
    parser.add_argument(
        "-t",
        "--type",
        default="development",
        help="Stream type when creating",
    )
    parser.add_argument(
        "-s",
        "--stash",
        action="store_true",
        help="Automatically stash open changes before switching streams and restore them after",
    )


def execute(args, run_p4, run_cmd=None, **kwargs):
    active_stream = kwargs.get("get_active_stream", get_active_stream)(run_p4)
    stream_resolver = kwargs.get("resolve_stream_path", resolve_stream_path)

    if getattr(args, "list", False) or not getattr(args, "stream", None):
        run_p4(["switch", "-l"], capture=False)
        return

    target_stream = stream_resolver(args.stream, active_stream)

    if args.create:
        cmd = ["switch", "-c"]
        if args.parent:
            cmd.extend(["-P", stream_resolver(args.parent, active_stream)])
        if args.type:
            cmd.extend(["-t", args.type])
        cmd.append(target_stream)
    else:
        cmd = ["switch", target_stream]

    if getattr(args, "stash", False) and not getattr(args, "list", False):
        opened = run_p4(["opened"], capture=True, check=False)
        if opened and opened.strip():
            # 1. Create a pending changelist via p4 change -i
            spec_template = run_p4(["change", "-o"], capture=True, check=True)
            desc = f"Auto-stash before switch to {target_stream}"
            lines = spec_template.splitlines()
            new_spec = []
            skip_desc = False
            for line in lines:
                if line.startswith("Description:"):
                    new_spec.append("Description:")
                    new_spec.append(f"\t{desc}")
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
            except subprocess.CalledProcessError as err:
                if err.stderr:
                    sys.stderr.write(err.stderr)
                raise SystemExit(err.returncode)

            match = re.search(r"Change\s+(\d+)", res.stdout)
            if not match:
                sys.stderr.write(f"Error: Failed to create changelist for auto-stash:\n{res.stdout}\n")
                raise SystemExit(1)
            cl_id = match.group(1)

            # Reopen any opened files into cl_id to guarantee all open files across the workspace are captured
            run_p4(["reopen", "-c", cl_id, "//..."], capture=True, check=False)

            # 2. Shelve the changelist
            run_p4(["shelve", "-c", cl_id], capture=False)

            # 3. Revert local changes
            run_p4(["revert", "-c", cl_id, "//..."], capture=False)
            opened_rem = run_p4(["opened", "-c", cl_id], capture=True, check=False)
            if opened_rem:
                rem_files = [line.split("#")[0].strip() for line in opened_rem.splitlines() if "#" in line]
                if rem_files:
                    run_p4(["revert", "-c", cl_id] + rem_files, capture=False, check=False)

            # 4. Execute stream switch
            switch_ok = False
            try:
                run_p4(cmd, capture=False, check=True)
                switch_ok = True
            except SystemExit as err:
                if err.code == 0:
                    switch_ok = True
                else:
                    switch_ok = False
            except Exception:
                switch_ok = False

            # 5. Outcome handling
            if switch_ok:
                unshelve_out = None
                candidates = []
                if target_stream and target_stream != active_stream:
                    candidates.append(target_stream)
                if active_stream and active_stream != target_stream and active_stream not in candidates:
                    candidates.append(active_stream)

                for cand in candidates:
                    res = run_p4(
                        ["unshelve", "-f", "-s", cl_id, "-S", cand],
                        capture=True,
                        check=False,
                    )
                    if (
                        res
                        and "not in client view" not in res.lower()
                        and "can't branch" not in res.lower()
                        and "has no parent" not in res.lower()
                        and "error:" not in res.lower()
                    ):
                        unshelve_out = res
                        break

                if not unshelve_out:
                    unshelve_out = run_p4(["unshelve", "-f", "-s", cl_id], capture=True, check=False)

                if unshelve_out:
                    print(unshelve_out)

                # Finalize any scheduled integration resolves created during cross-stream unshelving
                run_p4(["resolve", "-am"], capture=True, check=False)
                run_p4(["resolve", "-ay"], capture=True, check=False)

                opened_after = run_p4(["opened"], capture=True, check=False)
                if opened_after and opened_after.strip():
                    run_p4(["shelve", "-d", "-c", cl_id], capture=False, check=False)
                    run_p4(["change", "-d", cl_id], capture=True, check=False)
                    print("Restored auto-stashed changes into working tree.")
                else:
                    sys.stderr.write(
                        f"warning: Could not automatically unshelve changes into stream '{target_stream}'.\n"
                        f"Your changes remain safely shelved in changelist {cl_id}.\n"
                        f"You can manually unshelve with: gfp stash pop -c {cl_id}\n"
                    )
            else:
                sys.stderr.write(f"Stream switch failed. Your changes remain safely shelved in changelist {cl_id}.\n")
                raise SystemExit(1)
            return

    # Normal switch (no stash requested or no opened files)
    run_p4(cmd, capture=False)
