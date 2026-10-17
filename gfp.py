#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

# Ensure root directory of gfp is at the front of sys.path for plugin imports
_root_dir = str(Path(__file__).resolve().parent)
if not sys.path or sys.path[0] != _root_dir:
    if _root_dir in sys.path:
        sys.path.remove(_root_dir)
    sys.path.insert(0, _root_dir)

import utils
from utils import (
    TEXT_MODE,
    find_workspace_root,
    to_p4_path,
)

# --- Workspace & Root Resolution ---

WORKSPACE_ROOT = find_workspace_root()


# --- Shared Command Runners ---


def run_cmd(cmd_list, capture=True, check=True, env=None, quiet=False):
    """Executes a subprocess command."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        res = subprocess.run(
            cmd_list,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            check=check,
            env=run_env,
            **TEXT_MODE,
        )
        return res.stdout.strip() if capture and res.stdout else ""
    except subprocess.CalledProcessError as err:
        if capture and err.stderr and not quiet:
            sys.stderr.write(err.stderr)
        raise SystemExit(err.returncode)
    except FileNotFoundError:
        if not quiet:
            sys.stderr.write(f"Error: Executable '{cmd_list[0]}' not found.\n")
        raise SystemExit(1)


def run_p4(cmd_args, capture=True, check=True, quiet=False):
    """Executes a Perforce command."""
    return run_cmd(["p4"] + cmd_args, capture=capture, check=check, quiet=quiet)


# --- Hook Engine ---


def find_hook(stage, command_name):
    """
    Looks for hooks in:
      1. <workspace_root>/.gfp/hooks/<stage>-<command>
      2. ~/.gfp/hooks/<stage>-<command>
    Supports both hyphenated and underscored names (e.g. pre-commit or pre_commit).
    """
    candidates = [f"{stage}-{command_name}", f"{stage}_{command_name}"]
    hook_dirs = [WORKSPACE_ROOT / ".gfp" / "hooks", Path.home() / ".gfp" / "hooks"]

    for hdir in hook_dirs:
        if hdir.is_dir():
            for name in candidates:
                hook_path = hdir / name
                if hook_path.is_file() and os.access(hook_path, os.X_OK):
                    return hook_path
    return None


def execute_hook(stage, command_name, raw_args):
    """Runs a pre or post hook if present. Aborts execution if a pre-hook fails."""
    hook_path = find_hook(stage, command_name)
    if not hook_path:
        return

    hook_env = {
        "GFP_COMMAND": command_name,
        "GFP_HOOK_STAGE": stage,
        "GFP_WORKSPACE_ROOT": str(WORKSPACE_ROOT),
        "GFP_ARGS": " ".join(raw_args),
    }

    try:
        # Hooks run interactively with inherited standard descriptors
        subprocess.run([str(hook_path)] + raw_args, check=True, env={**os.environ, **hook_env})
    except subprocess.CalledProcessError as err:
        sys.stderr.write(f"\n[gfp hook error] '{hook_path.name}' exited with code {err.returncode}. Aborting.\n")
        raise SystemExit(err.returncode)


# --- Plugin Discovery ---


def load_python_plugin(filepath):
    mod_name = f"gfp_plugin_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_plugins():
    plugins = {}
    search_dirs = [
        Path(__file__).resolve().parent / "commands",
        WORKSPACE_ROOT / ".gfp" / "commands",
        Path.home() / ".gfp" / "commands",
    ]

    # Python module plugins
    for directory in search_dirs:
        if directory.is_dir():
            for file_path in directory.glob("*.py"):
                if file_path.name.startswith("__"):
                    continue
                try:
                    mod = load_python_plugin(file_path)
                    if hasattr(mod, "COMMAND_NAME") and hasattr(mod, "execute"):
                        plugins[mod.COMMAND_NAME] = {
                            "type": "python",
                            "module": mod,
                            "help": getattr(mod, "HELP", ""),
                            "setup_parser": getattr(mod, "setup_parser", None),
                        }
                except Exception as ex:
                    sys.stderr.write(f"Warning: Failed to load plugin '{file_path}': {ex}\n")

    # Declarative JSON plugins
    json_paths = [
        Path(__file__).resolve().parent / "plugins.json",
        WORKSPACE_ROOT / ".gfp" / "plugins.json",
        Path.home() / ".gfp" / "plugins.json",
    ]
    for jpath in json_paths:
        if jpath.is_file():
            try:
                with open(jpath, "r", encoding="utf-8") as f:
                    declarative = json.load(f)
                    for cmd_name, cfg in declarative.items():
                        plugins[cmd_name] = {
                            "type": "external",
                            "exec": cfg.get("exec"),
                            "help": cfg.get("help", "External command mapping"),
                        }
            except Exception as ex:
                sys.stderr.write(f"Warning: Failed to parse JSON config '{jpath}': {ex}\n")

    return plugins


DEFAULT_ALIASES = {
    "st": "status",
    "ci": "commit",
    "co": "checkout",
    "br": "branch",
    "di": "diff",
    "sw": "switch",
}


def load_aliases():
    """Loads default and user/workspace-configured command aliases."""
    aliases = dict(DEFAULT_ALIASES)
    config_paths = [
        Path.home() / ".gfp" / "config.json",
        Path.home() / ".gfp" / "aliases.json",
        WORKSPACE_ROOT / ".gfp" / "config.json",
        WORKSPACE_ROOT / ".gfp" / "aliases.json",
    ]
    for cpath in config_paths:
        if cpath.is_file():
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if isinstance(cfg, dict):
                        alias_dict = cfg.get("aliases", cfg)
                        if isinstance(alias_dict, dict):
                            for k, v in alias_dict.items():
                                if isinstance(v, str):
                                    aliases[k] = v
            except Exception as ex:
                sys.stderr.write(f"Warning: Failed to parse alias config '{cpath}': {ex}\n")

    return aliases


# --- Main CLI Flow ---


def main():
    aliases = load_aliases()

    # Transparently resolve command aliases before parsing
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        invoked = sys.argv[1]
        if invoked in aliases:
            expanded = shlex.split(aliases[invoked])
            if expanded:
                sys.argv = [sys.argv[0]] + expanded + sys.argv[2:]

    plugins = discover_plugins()

    parser = argparse.ArgumentParser(
        prog="gfp",
        description="Extensible Git-like CLI interface for Perforce with lifecycle hooks",
    )
    if sys.version_info >= (3, 7):
        subparsers = parser.add_subparsers(dest="subcommand", required=True)
    else:
        subparsers = parser.add_subparsers(dest="subcommand")
        subparsers.required = True

    for name, info in plugins.items():
        sub = subparsers.add_parser(name, help=info["help"])
        if info["type"] == "python" and info.get("setup_parser"):
            info["setup_parser"](sub)
        elif info["type"] == "external":
            sub.add_argument("extra_args", nargs=argparse.REMAINDER, help="Arguments passed through")

    args = parser.parse_args()
    raw_forward_args = sys.argv[2:]

    target = plugins.get(args.subcommand)
    if not target:
        sys.stderr.write(f"Unknown command: {args.subcommand}\n")
        sys.exit(1)

    # 1. Trigger PRE-hook
    execute_hook("pre", args.subcommand, raw_forward_args)

    # 2. Execute command
    try:
        if target["type"] == "python":
            target["module"].execute(
                args,
                run_p4=run_p4,
                run_cmd=run_cmd,
                to_p4_path=to_p4_path,
                get_active_client=utils.get_active_client,
                get_user=utils.get_user,
                get_active_stream=utils.get_active_stream,
                resolve_stream_path=utils.resolve_stream_path,
                run_pager=utils.run_pager,
                unescape_p4_path=utils.unescape_p4_path,
                workspace_root=WORKSPACE_ROOT,
            )
        elif target["type"] == "external":
            base_cmd = target["exec"] if isinstance(target["exec"], list) else target["exec"].split()
            extra = getattr(args, "extra_args", [])
            run_cmd(base_cmd + extra, capture=False, check=True)
    except SystemExit as e:
        if e.code != 0:
            raise

    # 3. Trigger POST-hook
    execute_hook("post", args.subcommand, raw_forward_args)


if __name__ == "__main__":
    main()
