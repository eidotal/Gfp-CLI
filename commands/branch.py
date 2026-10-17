import re
import subprocess
import sys
from typing import Any, Dict

TEXT_MODE: Dict[str, Any] = {"text": True} if sys.version_info >= (3, 7) else {"universal_newlines": True}

COMMAND_NAME = "branch"
HELP = "List, create, or delete Perforce streams (Git branch workflow)"


def get_active_stream(run_p4):
    """Resolves active stream from client spec (p4 client -o)."""
    try:
        client_out = run_p4(["client", "-o"], capture=True, check=False)
        if client_out:
            for line in client_out.splitlines():
                if line.startswith("Stream:"):
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        val = parts[1].strip()
                        if val and val.lower() not in ("none", "null"):
                            return val
    except Exception:
        pass
    return None


def resolve_stream_path(stream_name, active_stream=None):
    """Ensures a stream name has full Perforce depot syntax (//depot/stream)."""
    if not stream_name:
        return stream_name
    if stream_name.startswith("//"):
        return stream_name
    if active_stream and active_stream.startswith("//"):
        parts = active_stream.strip("/").split("/")
        if len(parts) >= 1:
            depot = parts[0]
            return f"//{depot}/{stream_name}"
    return stream_name


def setup_parser(parser):
    parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Stream name or path to create or query",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="List all depot streams",
    )
    parser.add_argument(
        "-d",
        "--delete",
        action="store_true",
        help="Delete specified stream",
    )
    parser.add_argument(
        "-P",
        "--parent",
        default=None,
        help="Parent stream path when creating a stream",
    )
    parser.add_argument(
        "-t",
        "--type",
        default="development",
        choices=["development", "release", "mainline", "virtual", "task"],
        help="Stream type",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show stream details and description",
    )


def execute(args, run_p4, run_cmd=None, **kwargs):
    active_stream = get_active_stream(run_p4)

    # 1. Delete stream
    if args.delete:
        if not args.name:
            sys.stderr.write("fatal: branch name required for deletion\n")
            raise SystemExit(1)
        target = resolve_stream_path(args.name, active_stream)
        run_p4(["stream", "-d", target], capture=False)
        return

    # 2. Create stream
    if args.name:
        stream_name = resolve_stream_path(args.name, active_stream)
        parent_stream = (
            resolve_stream_path(args.parent, active_stream) if args.parent else ("none" if args.type == "mainline" else active_stream)
        )

        o_cmd = ["stream", "-o", "-t", args.type]
        if parent_stream and parent_stream != "none":
            o_cmd.extend(["-P", parent_stream])
        o_cmd.append(stream_name)

        spec_template = run_p4(o_cmd, capture=True, check=True)

        try:
            res = subprocess.run(
                ["p4", "stream", "-i"],
                input=spec_template + "\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                **TEXT_MODE,
            )
            out = res.stdout.strip()
            if out:
                print(out)
            else:
                print(f"Created stream {stream_name}.")
        except subprocess.CalledProcessError as err:
            if err.stderr:
                sys.stderr.write(err.stderr)
            elif err.stdout:
                sys.stderr.write(err.stdout)
            raise SystemExit(err.returncode)
        return

    # 3. List streams
    cmd = ["streams"]
    if not args.all and active_stream and active_stream.startswith("//"):
        depot = active_stream.strip("/").split("/")[0]
        cmd.append(f"//{depot}/...")

    streams_out = run_p4(cmd, capture=True, check=False)
    if not streams_out and not args.all:
        streams_out = run_p4(["streams"], capture=True, check=False)

    if not streams_out or not streams_out.strip():
        print("No streams found.")
        return

    pattern = re.compile(r"^Stream\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$")
    for line in streams_out.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            stream_path, stream_type, parent, desc = match.groups()
            desc = desc.strip().strip("'")
            prefix = "* " if stream_path == active_stream else "  "
            if args.verbose:
                parent_info = f"parent: {parent}" if parent != "none" else "mainline"
                if desc:
                    print(f"{prefix}{stream_path:<30} [{stream_type}, {parent_info}] {desc}")
                else:
                    print(f"{prefix}{stream_path:<30} [{stream_type}, {parent_info}]")
            else:
                print(f"{prefix}{stream_path}")
        else:
            print(f"  {line}")
