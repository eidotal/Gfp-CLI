import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from utils import get_p4port, get_user

TEXT_MODE: Dict[str, Any] = {"text": True} if sys.version_info >= (3, 7) else {"universal_newlines": True}

COMMAND_NAME = "clone"
HELP = "Clone a repository/stream into a new directory and create client workspace"


def setup_parser(parser):
    parser.add_argument(
        "repository",
        help="Depot path or stream to clone (e.g. //stream/main or //depot/...)",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Target directory to create and clone into (optional positional fallback for -d/--dir)",
    )
    parser.add_argument(
        "-c",
        "--client",
        default=None,
        help="Name of the client workspace to create",
    )
    parser.add_argument(
        "-d",
        "--dir",
        default=None,
        help="Directory to create and clone into",
    )


def derive_default_dir(repository):
    """Derives a clean directory name by stripping trailing wildcards and slashes."""
    clean = repository.strip().rstrip("/")
    while clean.endswith("/...") or clean.endswith("..."):
        clean = clean[:-3].rstrip("/")
    parts = [p for p in clean.split("/") if p]
    return parts[-1] if parts else "workspace"


def is_stream_depot(repo, run_p4):
    """Accurately checks whether the target path points to a Perforce stream."""
    clean = repo.rstrip("/")
    while clean.endswith("/...") or clean.endswith("..."):
        clean = clean[:-3].rstrip("/")
    try:
        out = run_p4(["stream", "-o", clean], capture=True, check=False)
        return bool(out and "Stream:" in out and "doesn't exist" not in out and "not a stream depot" not in out)
    except Exception:
        return False


def execute(args, run_p4, run_cmd=None, **kwargs):
    repo = args.repository.strip()
    if not repo.startswith("//"):
        repo = f"//{repo}"

    # 1. Directory resolution
    target_name = args.dir or args.directory or derive_default_dir(repo)
    target_dir = Path(target_name).resolve()
    print(f"Cloning repository '{repo}' into '{target_dir.name}'...")

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        # Note: os.chdir() mutates the process-global working directory. This is executed
        # to ensure that .p4config is automatically discovered by standard Perforce command
        # invocations within this workspace. Downstream operations also explicitly pass
        # the workspace directory where applicable to avoid relying solely on process CWD.
        os.chdir(str(target_dir))
    except Exception as ex:
        sys.stderr.write(f"fatal: could not prepare directory '{target_dir}': {ex}\n")
        raise SystemExit(1)

    # 2. User and workspace client name resolution
    user = get_user(run_p4)
    clean_dir = re.sub(r"[^a-zA-Z0-9_\-.]", "_", target_dir.name)
    client_name = args.client.strip() if args.client else f"{user}_{clean_dir}_ws"

    # 3. Build client spec with unlocked, allwrite, and clobber options
    clean_repo = repo.rstrip("/")
    while clean_repo.endswith("/...") or clean_repo.endswith("..."):
        clean_repo = clean_repo[:-3].rstrip("/")

    options_value = "allwrite clobber nocompress unlocked"

    o_cmd = [
        "--field",
        f"Root={target_dir}",
        "--field",
        "Host=",
        "--field",
        f"Owner={user}",
        "--field",
        f"Description=Created by gfp clone for {repo}",
        "--field",
        f"Options={options_value}",
    ]

    if is_stream_depot(repo, run_p4):
        o_cmd.extend(["client", "-o", "-S", clean_repo, client_name])
    else:
        view_path = repo if repo.endswith("...") else f"{clean_repo}/..."
        o_cmd.extend(
            [
                "--field",
                f"View={view_path} //{client_name}/...",
                "client",
                "-o",
                client_name,
            ]
        )

    try:
        spec = run_p4(o_cmd, capture=True, check=True)

        # Enforce Options in a single regex pass
        spec, count = re.subn(
            r"^Options:.*$",
            f"Options:\t{options_value}",
            spec,
            flags=re.MULTILINE,
        )
        if count == 0:
            spec += f"\nOptions:\t{options_value}\n"

        subprocess.run(
            ["p4", "client", "-i"],
            input=spec + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            env=os.environ.copy(),
            **TEXT_MODE,
        )
        print(f"Created client workspace '{client_name}' (Options: {options_value}).")
    except subprocess.CalledProcessError as err:
        err_msg = err.stderr.strip() if err.stderr else str(err)
        sys.stderr.write(f"fatal: failed to create workspace '{client_name}': {err_msg}\n")
        raise SystemExit(err.returncode)

    # 4. Generate local .p4config and .gfp workspace marker
    config_lines = []
    p4port = get_p4port(run_p4)
    if p4port:
        config_lines.append(f"P4PORT={p4port}")
    if user:
        config_lines.append(f"P4USER={user}")
    config_lines.append(f"P4CLIENT={client_name}")
    config_lines.append("P4IGNORE=.p4ignore")

    try:
        (target_dir / ".p4config").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
        (target_dir / ".gfp").mkdir(exist_ok=True)

        p4ignore_file = target_dir / ".p4ignore"
        if not p4ignore_file.exists():
            default_ignores = [
                "# Perforce Ignore Rules",
                ".p4config",
                ".gfp/",
                "__pycache__/",
                "*.py[cod]",
                "*$py.class",
                ".DS_Store",
                "*.swp",
                "*.swo",
                "*~",
            ]
            p4ignore_file.write_text("\n".join(default_ignores) + "\n", encoding="utf-8")
    except Exception as ex:
        sys.stderr.write(f"warning: failed to write .p4config, .p4ignore, or .gfp: {ex}\n")

    # 5. Sync workspace files with unbuffered terminal progress
    print(f"Syncing workspace files from {repo}...")
    sync_env = os.environ.copy()
    sync_env["P4CLIENT"] = client_name

    try:
        sync_cmd = ["p4", "-c", client_name, "-d", str(target_dir), "sync"]
        if run_cmd:
            run_cmd(
                sync_cmd,
                capture=False,
                check=True,
                env=sync_env,
            )
        else:
            subprocess.run(
                sync_cmd,
                check=True,
                env=sync_env,
            )
    except SystemExit:
        raise
    except Exception as ex:
        sys.stderr.write(f"fatal: error during sync: {ex}\n")
        raise SystemExit(1)
