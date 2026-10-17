import re
import sys
from pathlib import Path

try:
    from utils import run_pager
except ImportError:
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from utils import run_pager

COMMAND_NAME = "blame"
HELP = "Show revision and author for each line of a file (p4 annotate)"


def setup_parser(parser):
    parser.add_argument("file", help="File to annotate/blame")
    parser.add_argument(
        "-c",
        "--cl",
        "--rev",
        dest="cl",
        default=None,
        help="Changelist or revision to annotate at (e.g. 12345 or #3)",
    )
    parser.add_argument(
        "-u",
        "--user",
        action="store_true",
        default=True,
        help="Display author name (default: True)",
    )
    parser.add_argument(
        "-d",
        "--date",
        action="store_true",
        default=True,
        help="Display date (default: True)",
    )
    parser.add_argument(
        "-L",
        "--line-range",
        dest="line_range",
        default=None,
        help="Annotate only specified line range (e.g. 10,25 or 10:+15)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress file headers",
    )


def parse_line_range(range_str, total_lines):
    """
    Parses git-style line range specifications:
      - '10,25'   -> lines 10 to 25
      - '10:+15'  -> 15 lines starting at line 10 (lines 10 to 24)
      - '10,+15'  -> 15 lines starting at line 10
      - '10:-5'   -> 5 lines ending at line 10 (lines 6 to 10)
      - '10,-5'   -> 5 lines ending at line 10
      - '10'      -> line 10
      - '10,'     -> lines 10 to end of file
      - ',25'     -> lines 1 to 25
    Returns 0-based slice indices (start_idx, end_idx).
    """
    range_str = range_str.strip()
    if not range_str:
        return 0, total_lines

    # Match 'start:+count' or 'start:-count'
    match_offset = re.match(r"^(\d+)\s*[:]\s*([+-]?\d+)$", range_str)
    if match_offset:
        start_val = int(match_offset.group(1))
        offset_val = int(match_offset.group(2))
        if offset_val >= 0:
            start_line = max(1, start_val)
            end_line = start_line + offset_val - 1
        else:
            end_line = max(1, start_val)
            start_line = max(1, end_line + offset_val + 1)
        start_idx = max(0, start_line - 1)
        end_idx = min(total_lines, max(start_idx, end_line))
        return start_idx, end_idx

    # Match comma-separated ranges: 'start,end', 'start,+count', 'start,-count'
    if "," in range_str:
        parts = range_str.split(",", 1)
        start_part = parts[0].strip()
        end_part = parts[1].strip()

        if end_part.startswith("+"):
            start_val = int(start_part) if start_part else 1
            count = int(end_part[1:])
            start_line = max(1, start_val)
            end_line = start_line + count - 1
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, max(start_idx, end_line))
            return start_idx, end_idx
        elif end_part.startswith("-"):
            start_val = int(start_part) if start_part else 1
            count = int(end_part[1:])
            end_line = max(1, start_val)
            start_line = max(1, end_line - count + 1)
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, max(start_idx, end_line))
            return start_idx, end_idx

        start_val = int(start_part) if start_part else 1
        end_val = int(end_part) if end_part else total_lines
        start_idx = max(0, start_val - 1)
        end_idx = min(total_lines, max(start_idx, end_val))
        return start_idx, end_idx

    # Single line number
    val = int(range_str)
    start_idx = max(0, val - 1)
    end_idx = min(total_lines, val)
    return start_idx, end_idx


def execute(args, run_p4, run_cmd=None, **kwargs):
    # Escape the file path first, then append revision specifier
    _escape = kwargs.get("to_p4_path") or (lambda p: p)
    target = _escape(args.file)
    if getattr(args, "cl", None):
        cl_str = str(args.cl).strip()
        # Revision specifiers (@, #) must be appended AFTER escaping the base path
        if cl_str.startswith("@") or cl_str.startswith("#"):
            target = f"{target}{cl_str}"
        else:
            target = f"{target}@{cl_str}"

    cmd = ["annotate", "-c"]
    if getattr(args, "user", False):
        cmd.append("-u")
    if getattr(args, "quiet", False):
        cmd.append("-q")

    output = run_p4(cmd + [target], capture=True, check=True)
    if not output:
        return

    lines = output.splitlines()
    if not lines:
        return

    # Check if first line is a p4 file header (when quiet is False)
    header = None
    content_lines = lines
    if not getattr(args, "quiet", False):
        # Perforce annotation lines begin with <cl/rev> followed by ':' or '('
        if lines and not re.match(r"^\s*(#?\d+)(\s*\(.*?\))?:", lines[0]):
            header = lines[0]
            content_lines = lines[1:]

    if getattr(args, "line_range", None):
        try:
            start_idx, end_idx = parse_line_range(args.line_range, len(content_lines))
            content_lines = content_lines[start_idx:end_idx]
        except Exception:
            sys.stderr.write(
                f"Error: Invalid line range format '{args.line_range}'. Expected formats: 'start,end', 'start:+count', or 'line_num'.\n"
            )
            raise SystemExit(1)

    result_lines = []
    if header and not getattr(args, "quiet", False):
        result_lines.append(header)
    result_lines.extend(content_lines)

    if result_lines:
        run_pager("\n".join(result_lines))
