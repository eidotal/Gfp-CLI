import argparse
import fnmatch
import os
import sys
from pathlib import Path

try:
    from utils import (
        COLOR_BOLD,
        COLOR_CYAN,
        COLOR_GREEN,
        COLOR_RED,
        COLOR_RESET,
        COLOR_YELLOW,
        run_pager,
        unescape_p4_path,
    )
except ImportError:
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from utils import (
        COLOR_BOLD,
        COLOR_CYAN,
        COLOR_GREEN,
        COLOR_RED,
        COLOR_RESET,
        COLOR_YELLOW,
        run_pager,
        unescape_p4_path,
    )

COMMAND_NAME = "diff"
HELP = "Show unified diff of modified files against depot"


def translate_path(path_str):
    """Translates git-style paths (., ./, dir, dir/) into Perforce wildcards (dir/...)."""
    if not path_str or path_str in (".", "./"):
        return "..."
    if path_str == "..." or path_str.endswith("/...") or path_str.endswith("..."):
        return path_str
    if path_str.endswith("/") or os.path.isdir(path_str):
        clean = path_str.rstrip("/")
        return f"{clean}/..." if clean else "..."
    return path_str


def parse_opened_line(line):
    """
    Parses a 'p4 opened' line into (depot_path, action, rev).
    Example: '//depot/main/file.py#1 - add default change (text)'
             -> ('//depot/main/file.py', 'add', '1')
    """
    if not line:
        return None, None, None
    line = line.strip()
    if line.startswith("... "):
        line = line[4:].strip()
    if "#" not in line or " - " not in line:
        return None, None, None
    try:
        file_rev, rest = line.split(" - ", 1)
        depot_path, rev = file_rev.rsplit("#", 1)
        depot_path = depot_path.strip()
        rev = rev.strip()
        action_parts = rest.strip().split()
        action = action_parts[0].strip() if action_parts else ""
        return depot_path, action, rev
    except Exception:
        return None, None, None


def resolve_local_path(run_p4, depot_path, candidate_path=None):
    """Resolves the local workspace filesystem path for a depot path."""
    unescaped_depot = unescape_p4_path(depot_path)
    if candidate_path and os.path.isfile(candidate_path):
        fname = unescaped_depot.split("/")[-1]
        cand_fname = Path(candidate_path).name
        if fname == cand_fname:
            return str(Path(candidate_path).resolve())

    # 1. Try p4 fstat
    try:
        fstat_out = run_p4(["fstat", depot_path], capture=True, check=False)
        if fstat_out:
            for line in fstat_out.splitlines():
                line = line.strip()
                if line.startswith("... clientFile "):
                    p = line[len("... clientFile ") :].strip()
                    if p:
                        unesc_p = unescape_p4_path(p)
                        if os.path.isfile(unesc_p):
                            return unesc_p
                        return p
    except Exception:
        pass

    # 2. Try p4 where
    try:
        where_out = run_p4(["where", depot_path], capture=True, check=False)
        if where_out:
            for line in where_out.splitlines():
                line = line.strip()
                if line.startswith("-"):
                    continue
                parts = line.split()
                if len(parts) >= 3 and parts[0].startswith("//") and parts[1].startswith("//"):
                    p = line[len(parts[0]) :].strip()
                    p = p[len(parts[1]) :].strip()
                    if p:
                        unesc_p = unescape_p4_path(p)
                        if os.path.isfile(unesc_p):
                            return unesc_p
                        return p
    except Exception:
        pass

    # 3. Fallback to cwd check
    fname = unescaped_depot.split("/")[-1]
    if os.path.isfile(fname):
        return str(Path(fname).resolve())

    return None


def get_synthetic_diff_for_add(run_p4, depot_path, rev="1", candidate_path=None):
    """
    Generates a synthetic unified diff for a file opened for add against /dev/null.
    Format:
      ==== {depot_path}#1 (add) ====
      --- /dev/null
      +++ {local_or_depot_path}
      @@ -0,0 +1,{num_lines} @@
      +{line_1}
      +{line_2}
    """
    resolved_path = resolve_local_path(run_p4, depot_path, candidate_path=candidate_path)

    content = ""
    if resolved_path and os.path.isfile(resolved_path):
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            content = ""

    display_path = None
    if resolved_path:
        try:
            rel = os.path.relpath(resolved_path, os.getcwd())
            if not rel.startswith(".."):
                display_path = rel
            else:
                display_path = resolved_path
        except Exception:
            display_path = resolved_path

    if not display_path:
        display_path = depot_path

    lines = content.splitlines()
    num_lines = len(lines)
    rev_str = str(rev) if rev else "1"

    chunk = [
        f"==== {depot_path}#{rev_str} (add) ====",
        "--- /dev/null",
        f"+++ {display_path}",
    ]
    if num_lines > 0:
        chunk.append(f"@@ -0,0 +1,{num_lines} @@")
        for line in lines:
            chunk.append(f"+{line}")

    return "\n".join(chunk)


class ColorAction(argparse.Action):
    """
    Handles git-compatible --color[=<when>] options.
    If passed without argument or with non-choice value (e.g. filename),
    treats --color as 'always' and captures any swallowed positional path.
    """

    def __init__(self, option_strings, dest, default="auto", **kwargs):
        super(ColorAction, self).__init__(option_strings, dest, nargs="?", default=default, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if values is None:
            setattr(namespace, self.dest, "always")
            return

        is_explicit = False
        try:
            import inspect

            f = inspect.currentframe()
            for _ in range(5):
                if f is None:
                    break
                if "explicit_arg" in f.f_locals:
                    is_explicit = f.f_locals["explicit_arg"] is not None
                    break
                f = f.f_back
        except Exception:
            pass

        if values in ("always", "never", "auto"):
            setattr(namespace, self.dest, values)
        elif is_explicit:
            parser.error(f"argument --color: invalid choice: '{values}' (choose from 'always', 'never', 'auto')")
        else:
            setattr(namespace, self.dest, "always")
            setattr(namespace, "_swallowed_path", values)


def should_colorize(color_choice="auto"):
    """Determines whether output should be colorized based on flag and environment."""
    if color_choice == "always":
        return True
    if color_choice == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def colorize_diff(diff_text):
    """
    Applies ANSI color highlighting to a unified diff text:
      - File headers (==== ... ====, diff --git, ---, +++) in bold
      - Hunk headers (@@ ... @@) in cyan
      - Added lines (+) in green
      - Deleted lines (-) in red
      - Context lines unchanged
    """
    if not diff_text:
        return diff_text

    colored_lines = []
    lines = diff_text.splitlines()
    in_hunk = False

    for idx, line in enumerate(lines):
        # File headers: ==== //depot/path#rev (action) ====
        if line.startswith("====") and ("====" in line[4:] or line.endswith("====")):
            in_hunk = False
            colored_lines.append(f"{COLOR_BOLD}{line}{COLOR_RESET}")
        elif line.startswith("diff --git ") or line.startswith("Index: ") or line.startswith("index "):
            in_hunk = False
            colored_lines.append(f"{COLOR_BOLD}{line}{COLOR_RESET}")
        elif line.startswith("--- ") or line.startswith("+++ "):
            # Check if this is file header or inside hunk
            is_file_header = not in_hunk or (line.startswith("--- ") and idx + 1 < len(lines) and lines[idx + 1].startswith("+++ "))
            if is_file_header:
                in_hunk = False
                colored_lines.append(f"{COLOR_BOLD}{line}{COLOR_RESET}")
            else:
                if line.startswith("+"):
                    colored_lines.append(f"{COLOR_GREEN}{line}{COLOR_RESET}")
                else:
                    colored_lines.append(f"{COLOR_RED}{line}{COLOR_RESET}")
        elif line.startswith("@@"):
            in_hunk = True
            colored_lines.append(f"{COLOR_CYAN}{line}{COLOR_RESET}")
        elif in_hunk:
            if line.startswith("+"):
                colored_lines.append(f"{COLOR_GREEN}{line}{COLOR_RESET}")
            elif line.startswith("-"):
                colored_lines.append(f"{COLOR_RED}{line}{COLOR_RESET}")
            elif line.startswith("\\"):
                colored_lines.append(f"{COLOR_BOLD}{line}{COLOR_RESET}")
            else:
                colored_lines.append(line)
        else:
            if line.startswith("Change "):
                colored_lines.append(f"{COLOR_YELLOW}{line}{COLOR_RESET}")
            else:
                colored_lines.append(line)

    res = "\n".join(colored_lines)
    if diff_text.endswith("\n"):
        res += "\n"
    return res


def generate_diffstat(diff_text, color=False):
    """Parses unified diff output and returns a git-style diffstat summary."""
    if not diff_text or not diff_text.strip():
        return ""

    file_stats = {}
    current_file = None
    in_diff_chunk = False
    saw_dev_null = False

    for line in diff_text.splitlines():
        if line.startswith("====") and "====" in line[4:]:
            parts = line.strip("=").strip().split()
            if parts:
                fname = parts[0].split("#")[0]
                current_file = fname
                if current_file not in file_stats:
                    file_stats[current_file] = {"add": 0, "del": 0}
            in_diff_chunk = False
            saw_dev_null = False
            continue
        elif line.startswith("--- ") or line.startswith("+++ "):
            if line.startswith("--- /dev/null"):
                saw_dev_null = True
            elif line.startswith("+++ "):
                target_path = line[4:].strip().split("\t")[0]
                if target_path and target_path != "/dev/null":
                    if (
                        saw_dev_null
                        and current_file in file_stats
                        and file_stats[current_file]["add"] == 0
                        and file_stats[current_file]["del"] == 0
                    ):
                        del file_stats[current_file]
                        current_file = target_path
                        file_stats[current_file] = {"add": 0, "del": 0}
                    elif not current_file:
                        current_file = target_path
                        if current_file not in file_stats:
                            file_stats[current_file] = {"add": 0, "del": 0}
                saw_dev_null = False
            continue
        elif line.startswith("@@"):
            in_diff_chunk = True
            continue

        if in_diff_chunk and current_file:
            if line.startswith("+"):
                file_stats[current_file]["add"] += 1
            elif line.startswith("-"):
                file_stats[current_file]["del"] += 1

    if not file_stats:
        return ""

    max_name_len = max(len(f) for f in file_stats.keys())
    max_change = max((stats["add"] + stats["del"]) for stats in file_stats.values())
    max_change_digits = max(1, len(str(max_change)))
    graph_width = 30

    total_files = len(file_stats)
    total_adds = sum(s["add"] for s in file_stats.values())
    total_dels = sum(s["del"] for s in file_stats.values())

    out_lines = []
    for fname, stats in file_stats.items():
        adds = stats["add"]
        dels = stats["del"]
        total = adds + dels
        if max_change > 0 and total > 0:
            if max_change <= graph_width:
                plus_count = adds
                minus_count = dels
            else:
                scale = graph_width / max_change
                plus_count = int(adds * scale)
                minus_count = int(dels * scale)
                if plus_count == 0 and adds > 0:
                    plus_count = 1
                if minus_count == 0 and dels > 0:
                    minus_count = 1
            if color:
                parts = []
                if plus_count > 0:
                    parts.append(f"{COLOR_GREEN}{'+' * plus_count}")
                if minus_count > 0:
                    parts.append(f"{COLOR_RED}{'-' * minus_count}")
                if parts:
                    parts.append(COLOR_RESET)
                graph = "".join(parts)
            else:
                graph = "+" * plus_count + "-" * minus_count
        else:
            graph = ""

        padding = " " * (max_name_len - len(fname))
        count_str = str(total).rjust(max_change_digits)
        out_lines.append(f" {fname}{padding} | {count_str} {graph}".rstrip())

    file_word = "file" if total_files == 1 else "files"
    insert_word = "insertion" if total_adds == 1 else "insertions"
    delete_word = "deletion" if total_dels == 1 else "deletions"

    summary_parts = [f"{total_files} {file_word} changed"]
    if total_adds > 0 or total_dels == 0:
        summary_parts.append(f"{total_adds} {insert_word}(+)")
    if total_dels > 0:
        summary_parts.append(f"{total_dels} {delete_word}(-)")

    out_lines.append(f" {', '.join(summary_parts)}")
    return "\n".join(out_lines)


def setup_parser(parser):
    parser.add_argument("path", nargs="?", default=None, help="Target file or directory path")
    parser.add_argument("-c", "--cl", default=None, help="Diff a specific changelist ID")
    parser.add_argument("--stat", action="store_true", help="Show summary of changes (diffstat style)")
    parser.add_argument(
        "--color",
        action=ColorAction,
        help="Show colored diff ('always', 'never', or 'auto')",
    )
    parser.add_argument(
        "--no-color",
        dest="color",
        action="store_const",
        const="never",
        help="Turn off colored diff (equivalent to --color=never)",
    )


def execute(args, run_p4, **kwargs):
    if getattr(args, "path", None) is None and getattr(args, "_swallowed_path", None) is not None:
        args.path = args._swallowed_path

    color_choice = getattr(args, "color", "auto")
    use_color = should_colorize(color_choice)

    # Use to_p4_path injected by gfp.py (escapes @, #, %, *) or fall back to
    # the local translate_path which handles . and directory expansion only.
    converter = kwargs.get("to_p4_path") or translate_path
    target = [converter(args.path)] if args.path else ["..."]

    if args.cl:
        cl_str = str(args.cl)
        # Check if changelist has locally opened files
        opened_out = run_p4(["opened", "-c", cl_str], capture=True, check=False)
        opened_entries = []
        if opened_out and opened_out.strip():
            for line in opened_out.strip().splitlines():
                dpath, act, rev = parse_opened_line(line)
                if dpath:
                    opened_entries.append((dpath, act, rev))
                elif "#" in line:
                    file_path = line.split("#", 1)[0].strip()
                    if file_path:
                        opened_entries.append((file_path, "edit", "1"))

        had_opened = bool(opened_entries)

        # Filter by path if provided; opened_entries paths are already P4-escaped
        # depot paths returned by Perforce — do NOT re-escape them.
        if args.path and args.path not in (".", "./") and opened_entries:
            path_filter = args.path.replace("\\", "/").strip("/")
            opened_entries = [
                entry
                for entry in opened_entries
                if entry[0].endswith("/" + path_filter)
                or entry[0].lstrip("/") == path_filter
                or unescape_p4_path(entry[0]).endswith("/" + path_filter)
                or unescape_p4_path(entry[0]).lstrip("/") == path_filter
                or fnmatch.fnmatch(entry[0], "*/" + path_filter)
                or fnmatch.fnmatch(entry[0], path_filter)
                or fnmatch.fnmatch(entry[0], "*/" + path_filter + "/*")
                or fnmatch.fnmatch(unescape_p4_path(entry[0]), "*/" + path_filter)
                or fnmatch.fnmatch(unescape_p4_path(entry[0]), path_filter)
                or fnmatch.fnmatch(unescape_p4_path(entry[0]), "*/" + path_filter + "/*")
            ]

        if opened_entries:
            diff_files = []
            add_entries = []
            for dpath, act, rev in opened_entries:
                if act in ("add", "move/add"):
                    add_entries.append((dpath, act, rev))
                else:
                    diff_files.append(dpath)

            diff_chunks = []
            if diff_files:
                regular_diff = run_p4(["diff", "-du"] + diff_files, capture=True, check=False)
                if regular_diff and regular_diff.strip():
                    diff_chunks.append(regular_diff.strip())

            for dpath, act, rev in add_entries:
                syn = get_synthetic_diff_for_add(run_p4, dpath, rev, candidate_path=args.path)
                if syn:
                    diff_chunks.append(syn)

            combined_diff = "\n".join(diff_chunks)
            if args.stat:
                stat_out = generate_diffstat(combined_diff, color=use_color)
                if stat_out:
                    run_pager(stat_out)
            else:
                if combined_diff:
                    run_pager(colorize_diff(combined_diff) if use_color else combined_diff)
        elif had_opened and args.path and args.path not in (".", "./"):
            # Files are opened in this changelist, but none matched the specified path
            return
        else:
            shelved_check = run_p4(["describe", "-s", "-S", cl_str], capture=True, check=False)
            has_shelf = any(line.startswith("Shelved files") for line in (shelved_check or "").splitlines())
            if has_shelf:
                cmd = ["describe", "-du", "-S", cl_str]
            else:
                cmd = ["describe", "-du", cl_str]

            diff_out = run_p4(cmd, capture=True, check=False)
            if args.stat:
                stat_out = generate_diffstat(diff_out, color=use_color)
                if stat_out:
                    run_pager(stat_out)
            else:
                if diff_out:
                    run_pager(colorize_diff(diff_out) if use_color else diff_out)

    else:
        # Query opened files
        opened_out = run_p4(["opened"], capture=True, check=False)
        opened_entries = []
        if opened_out and opened_out.strip():
            for line in opened_out.strip().splitlines():
                dpath, act, rev = parse_opened_line(line)
                if dpath:
                    opened_entries.append((dpath, act, rev))

        if args.path and args.path not in (".", "./") and opened_entries:
            path_filter = args.path.replace("\\", "/").strip("/")
            opened_entries = [
                entry
                for entry in opened_entries
                if entry[0].endswith("/" + path_filter)
                or entry[0].lstrip("/") == path_filter
                or unescape_p4_path(entry[0]).endswith("/" + path_filter)
                or unescape_p4_path(entry[0]).lstrip("/") == path_filter
                or fnmatch.fnmatch(entry[0], "*/" + path_filter)
                or fnmatch.fnmatch(entry[0], path_filter)
                or fnmatch.fnmatch(entry[0], "*/" + path_filter + "/*")
                or fnmatch.fnmatch(unescape_p4_path(entry[0]), "*/" + path_filter)
                or fnmatch.fnmatch(unescape_p4_path(entry[0]), path_filter)
                or fnmatch.fnmatch(unescape_p4_path(entry[0]), "*/" + path_filter + "/*")
            ]

        add_entries = []
        edit_files = []
        for dpath, act, rev in opened_entries:
            if act in ("add", "move/add"):
                add_entries.append((dpath, act, rev))
            elif act != "delete":
                edit_files.append(dpath)

        diff_chunks = []
        if edit_files:
            regular_diff = run_p4(["diff", "-du"] + edit_files, capture=True, check=False)
            if regular_diff and regular_diff.strip():
                diff_chunks.append(regular_diff.strip())
        elif not add_entries:
            # Fall back to diff -du -f on target directly if nothing was recognized in opened (e.g. unopened files)
            diff_cmd = ["diff", "-du", "-f"]
            regular_diff = run_p4(diff_cmd + target, capture=True, check=False)
            if regular_diff and regular_diff.strip():
                diff_chunks.append(regular_diff.strip())

            # regular_diff = run_p4(["diff", "-du", "-f"] + target, capture=True, check=False)
            # if regular_diff and regular_diff.strip() and "====" in regular_diff:
            # diff_chunks.append(regular_diff.strip())

        for dpath, act, rev in add_entries:
            syn = get_synthetic_diff_for_add(run_p4, dpath, rev, candidate_path=args.path)
            if syn:
                diff_chunks.append(syn)

        combined_diff = "\n".join(diff_chunks)
        if args.stat:
            stat_out = generate_diffstat(combined_diff, color=use_color)
            if stat_out:
                run_pager(stat_out)
        else:
            if combined_diff:
                run_pager(colorize_diff(combined_diff) if use_color else combined_diff)
