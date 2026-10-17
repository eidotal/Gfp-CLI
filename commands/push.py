import json
import os
import re
import sys
from pathlib import Path

try:
    from utils import get_active_client, get_user
except ImportError:
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from utils import get_active_client, get_user

COMMAND_NAME = "push"
HELP = "Submit changelist to the depot (gated via submit queue, or direct submit)"


def get_push_mode():
    """
    Resolves submit mode ('direct' or 'gated') in order of priority:
      1. Environment variable GFP_PUSH_MODE
      2. Hierarchical parent directory search for .gfp/config.json
      3. Global user config ~/.gfp/config.json
    Default is 'gated'.
    """
    env_mode = os.environ.get("GFP_PUSH_MODE")
    if env_mode:
        val = env_mode.strip().lower()
        if val in ("direct", "gated"):
            return val

    curr = Path.cwd().resolve()
    for parent in [curr] + list(curr.parents):
        cfg_file = parent / ".gfp" / "config.json"
        if cfg_file.is_file():
            try:
                with open(str(cfg_file), "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if isinstance(cfg, dict) and "push_mode" in cfg:
                        val = str(cfg["push_mode"]).strip().lower()
                        if val in ("direct", "gated"):
                            return val
            except Exception:
                pass

    user_cfg = Path.home() / ".gfp" / "config.json"
    if user_cfg.is_file():
        try:
            with open(str(user_cfg), "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if isinstance(cfg, dict) and "push_mode" in cfg:
                    val = str(cfg["push_mode"]).strip().lower()
                    if val in ("direct", "gated"):
                        return val
        except Exception:
            pass

    return "gated"


def get_submit_queue_url():
    """Resolves submit queue URL from GFP_SUBMIT_QUEUE_URL, .gfp/config.json, or ~/.gfp/config.json."""
    env_url = os.environ.get("GFP_SUBMIT_QUEUE_URL")
    if env_url:
        return env_url.strip()

    curr = Path.cwd().resolve()
    for parent in [curr] + list(curr.parents):
        cfg_file = parent / ".gfp" / "config.json"
        if cfg_file.is_file():
            try:
                with open(str(cfg_file), "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if isinstance(cfg, dict) and cfg.get("submit_queue_url"):
                        return cfg["submit_queue_url"]
            except Exception:
                pass

    user_cfg = Path.home() / ".gfp" / "config.json"
    if user_cfg.is_file():
        try:
            with open(str(user_cfg), "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if isinstance(cfg, dict) and cfg.get("submit_queue_url"):
                    return cfg["submit_queue_url"]
        except Exception:
            pass

    return None


def setup_parser(parser):
    parser.add_argument("-c", "--cl", default=None, help="Specific changelist ID to submit")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force direct submit to depot (bypassing the Jenkins gated submit queue)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Perform a dry run without submitting or shelving",
    )
    parser.add_argument(
        "--gated",
        action="store_true",
        help="Force submission through Jenkins gated submit queue",
    )


def execute(args, run_p4, **kwargs):
    client_resolver = kwargs.get("get_active_client", get_active_client)
    user_resolver = kwargs.get("get_user", get_user)

    cl_id = str(args.cl) if getattr(args, "cl", None) else None

    if not cl_id:
        changes_args = ["changes", "-s", "pending"]
        client = client_resolver(run_p4)
        user = user_resolver(run_p4)
        if client:
            changes_args.extend(["-c", client])
        if user:
            changes_args.extend(["-u", user])
        changes_args.extend(["-m", "1"])

        changes_out = run_p4(changes_args)
        if changes_out:
            first_line = changes_out.strip().splitlines()[0]
            match = re.search(r"Change\s+(\d+)", first_line)
            if match:
                cl_id = match.group(1)

    force = getattr(args, "force", False)
    gated = getattr(args, "gated", False)
    push_mode = get_push_mode()

    if force:
        is_direct = True
    elif gated:
        is_direct = False
    elif push_mode == "direct":
        is_direct = True
    else:
        is_direct = False

    # Handle dry-run inspection
    if getattr(args, "dry_run", False):
        if is_direct:
            action_desc = "force submit" if force else "submit"
            if cl_id:
                print(f"[dry-run] Would {action_desc} pending changelist {cl_id} directly to depot.")
            else:
                print(f"[dry-run] Would {action_desc} default changelist directly to depot.")
        else:
            if cl_id:
                print(f"[dry-run] Would shelve pending changelist {cl_id} for Jenkins submit queue.")
            else:
                print("[dry-run] Gated queue requires a numbered changelist. Would abort or create CL.")

        target_cl = cl_id if cl_id else "default"
        try:
            opened = run_p4(["opened", "-c", str(target_cl)], quiet=True)
            if opened:
                print(f"Files in changelist ({target_cl}):")
                for line in opened.splitlines():
                    print(f"  {line}")
        except Exception:
            pass
        return

    # Direct submit: direct submission to depot bypassing gated queue
    if is_direct:
        prefix = "[gfp push -f]" if force else "[gfp push]"
        action = "Force submitting" if force else "Submitting"
        if cl_id:
            # Purge any existing shelf on this changelist to allow direct submit to succeed
            # (Perforce forbids p4 submit on changes with active shelves)
            try:
                opened_in_cl = run_p4(["opened", "-c", str(cl_id)], capture=True, check=False)
                if opened_in_cl and opened_in_cl.strip():
                    run_p4(["shelve", "-d", "-c", str(cl_id)], capture=True, check=False)
            except Exception:
                pass
            print(f"{prefix} {action} changelist {cl_id} directly to depot...")
            run_p4(["submit", "-c", cl_id], capture=False)
            print(f"Submitted change {cl_id}.")
        else:
            print(f"{prefix} {action} default changelist directly to depot...")
            run_p4(["submit"], capture=False)
            print("Submitted change.")
        return

    # Default: Gated Submit Queue (shelve change to trigger Jenkins CI verification)
    if not cl_id:
        sys.stderr.write(
            "fatal: Gated submit queue requires a numbered changelist.\n"
            "Please run 'gfp commit -m \"<message>\"' first, or use 'gfp push -f' to force direct submit.\n"
        )
        raise SystemExit(1)

    print(f"Shelving changelist {cl_id} for Jenkins CI submit queue verification...")
    run_p4(["shelve", "-r", "-c", cl_id], capture=False)
    print(f"\nChangelist {cl_id} queued for CI verification.")
    submit_queue_url = get_submit_queue_url()
    if submit_queue_url:
        print("Monitor progress at: " + submit_queue_url)

    print("(Use 'gfp push -f' if you need to bypass CI and submit directly to depot)")
