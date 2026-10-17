#!/usr/bin/env python3
"""
Unit tests for utils.py - Centralized Perforce, path, and system utilities.
Compatible with Python >= 3.6.4.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import utils


class TestPathUtilities(unittest.TestCase):
    """Tests for path escaping, path conversion, and stream resolution."""

    def test_escape_p4_path_none_and_empty(self):
        self.assertIsNone(utils.escape_p4_path(None))
        self.assertEqual(utils.escape_p4_path(""), "")

    def test_escape_p4_path_individual_special_chars(self):
        self.assertEqual(utils.escape_p4_path("file@1.txt"), "file%401.txt")
        self.assertEqual(utils.escape_p4_path("file#2.txt"), "file%232.txt")
        self.assertEqual(utils.escape_p4_path("file%3.txt"), "file%253.txt")
        self.assertEqual(utils.escape_p4_path("file*4.txt"), "file%2A4.txt")

    def test_escape_p4_path_compound_order_prevents_double_encoding(self):
        # % must be escaped first, so %40 becomes %2540 rather than re-escaping %40 to @
        raw = "percent%_at@_hash#_star*.txt"
        expected = "percent%25_at%40_hash%23_star%2A.txt"
        self.assertEqual(utils.escape_p4_path(raw), expected)

    def test_to_p4_path_wildcards_and_dots(self):
        self.assertEqual(utils.to_p4_path(None), "...")
        self.assertEqual(utils.to_p4_path(""), "...")
        self.assertEqual(utils.to_p4_path("."), "...")
        self.assertEqual(utils.to_p4_path("./"), "...")
        self.assertEqual(utils.to_p4_path("..."), "...")
        self.assertEqual(utils.to_p4_path("dir/..."), "dir/...")
        self.assertEqual(utils.to_p4_path("dir/..."), utils.translate_path("dir/..."))

    def test_to_p4_path_directories_and_files(self):
        # Trailing slash indicates directory -> dir/...
        self.assertEqual(utils.to_p4_path("src/"), "src/...")
        self.assertEqual(utils.to_p4_path("src/sub/"), "src/sub/...")
        self.assertEqual(utils.to_p4_path("main.py"), "main.py")

    def test_to_p4_path_with_special_characters(self):
        self.assertEqual(utils.to_p4_path("test@file.py"), "test%40file.py")
        self.assertEqual(utils.to_p4_path("dir#1/"), "dir%231/...")
        self.assertEqual(utils.to_p4_path("dir%2/..."), "dir%252/...")

    def test_unescape_p4_path(self):
        self.assertEqual(utils.unescape_p4_path("test%40file.py"), "test@file.py")
        self.assertEqual(utils.unescape_p4_path("dir%231/..."), "dir#1/...")
        self.assertEqual(utils.unescape_p4_path("dir%252/..."), "dir%2/...")
        self.assertEqual(utils.unescape_p4_path("file%2A.txt"), "file*.txt")
        self.assertEqual(utils.unescape_p4_path("test_%25percent_%23hash_%40at.txt"), "test_%percent_#hash_@at.txt")
        self.assertIsNone(utils.unescape_p4_path(None))

    def test_resolve_stream_path_already_absolute(self):
        self.assertEqual(utils.resolve_stream_path("//stream/main"), "//stream/main")
        self.assertEqual(utils.resolve_stream_path("//depot/custom"), "//depot/custom")

    def test_resolve_stream_path_relative_with_active_stream(self):
        self.assertEqual(
            utils.resolve_stream_path("dev", active_stream="//stream/main"),
            "//stream/dev",
        )
        self.assertEqual(
            utils.resolve_stream_path("feature-x", active_stream="//my_depot/main"),
            "//my_depot/feature-x",
        )

    def test_resolve_stream_path_none_or_no_active_stream(self):
        self.assertIsNone(utils.resolve_stream_path(None))
        self.assertEqual(utils.resolve_stream_path(""), "")
        self.assertEqual(utils.resolve_stream_path("dev", active_stream=None), "dev")


class TestPerforceResolvers(unittest.TestCase):
    """Tests for get_active_client, get_user, get_p4port, get_active_stream."""

    def setUp(self):
        self._orig_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_get_active_client_from_env(self):
        os.environ["P4CLIENT"] = "env_client_ws"
        run_p4_mock = MagicMock()
        client = utils.get_active_client(run_p4_mock)
        self.assertEqual(client, "env_client_ws")
        run_p4_mock.assert_not_called()

    def test_get_active_client_from_p4_set(self):
        os.environ.pop("P4CLIENT", None)
        run_p4_mock = MagicMock(return_value="P4CLIENT=my_set_ws (set)\nP4PORT=server:1666")
        client = utils.get_active_client(run_p4_mock)
        self.assertEqual(client, "my_set_ws")
        run_p4_mock.assert_called_with(["set", "P4CLIENT"], capture=True, check=False)

    def test_get_active_client_from_p4_info_fallback(self):
        os.environ.pop("P4CLIENT", None)

        def mock_run_p4(args, **kwargs):
            if args[0] == "set":
                return ""
            if args[0] == "info":
                return "User name: devuser\nClient name: ws_from_info\nServer date: 2026/09/11"
            return ""

        client = utils.get_active_client(mock_run_p4)
        self.assertEqual(client, "ws_from_info")

    def test_get_active_client_unresolvable(self):
        os.environ.pop("P4CLIENT", None)
        mock_run_p4 = MagicMock(return_value="")
        client = utils.get_active_client(mock_run_p4)
        self.assertIsNone(client)

    def test_get_user_from_env(self):
        os.environ["P4USER"] = "alice"
        mock_run_p4 = MagicMock()
        self.assertEqual(utils.get_user(mock_run_p4), "alice")
        mock_run_p4.assert_not_called()

    def test_get_user_from_p4_set(self):
        os.environ.pop("P4USER", None)
        mock_run_p4 = MagicMock(return_value="P4USER=bob (config)\n")
        self.assertEqual(utils.get_user(mock_run_p4), "bob")

    def test_get_user_from_p4_info(self):
        os.environ.pop("P4USER", None)

        def mock_run_p4(args, **kwargs):
            if args[0] == "set":
                return ""
            if args[0] == "info":
                return "User name: charlie\n"
            return ""

        self.assertEqual(utils.get_user(mock_run_p4), "charlie")

    def test_get_user_fallback(self):
        os.environ.pop("P4USER", None)
        os.environ["USER"] = "sysuser"
        mock_run_p4 = MagicMock(return_value="")
        self.assertEqual(utils.get_user(mock_run_p4), "sysuser")

    def test_get_p4port_from_env(self):
        os.environ["P4PORT"] = "p4server:1666"
        mock_run_p4 = MagicMock()
        self.assertEqual(utils.get_p4port(mock_run_p4), "p4server:1666")
        mock_run_p4.assert_not_called()

    def test_get_p4port_from_p4_set(self):
        os.environ.pop("P4PORT", None)
        mock_run_p4 = MagicMock(return_value="P4PORT=p4sethost:2666 (set)\n")
        self.assertEqual(utils.get_p4port(mock_run_p4), "p4sethost:2666")

    def test_get_p4port_from_p4_info(self):
        os.environ.pop("P4PORT", None)

        def mock_run_p4(args, **kwargs):
            if args[0] == "set":
                return ""
            if args[0] == "info":
                return "Server address: p4infohost:3666\n"
            return ""

        self.assertEqual(utils.get_p4port(mock_run_p4), "p4infohost:3666")

    def test_get_active_stream(self):
        client_out = "Client: devuser_ws\nOwner: devuser\nStream: //stream/main\n"
        mock_run_p4 = MagicMock(return_value=client_out)
        self.assertEqual(utils.get_active_stream(mock_run_p4), "//stream/main")

    def test_get_active_stream_none_or_null(self):
        client_out = "Client: devuser_ws\nStream: none\n"
        mock_run_p4 = MagicMock(return_value=client_out)
        self.assertIsNone(utils.get_active_stream(mock_run_p4))

        client_out = "Client: devuser_ws\nStream: null\n"
        mock_run_p4 = MagicMock(return_value=client_out)
        self.assertIsNone(utils.get_active_stream(mock_run_p4))


class TestWorkspaceRootResolution(unittest.TestCase):
    """Tests for find_workspace_root."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_workspace_root_with_gfp_marker_in_parent(self):
        root = Path(self.temp_dir)
        gfp_marker = root / ".gfp"
        gfp_marker.mkdir()
        sub_child = root / "src" / "pkg"
        sub_child.mkdir(parents=True)

        with patch("pathlib.Path.cwd", return_value=sub_child):
            resolved = utils.find_workspace_root()
            self.assertEqual(resolved, root.resolve())

    def test_find_workspace_root_fallback_to_cwd(self):
        empty_dir = Path(self.temp_dir) / "no_gfp"
        empty_dir.mkdir()

        with patch("pathlib.Path.cwd", return_value=empty_dir):
            with patch("subprocess.run", side_effect=Exception("p4 not found")):
                resolved = utils.find_workspace_root()
                self.assertEqual(resolved, empty_dir)


class TestPagerUtilities(unittest.TestCase):
    """Tests for run_pager."""

    def test_run_pager_none_text(self):
        # Should return silently
        utils.run_pager(None)

    @patch("sys.stdout.isatty", return_value=False)
    @patch("builtins.print")
    def test_run_pager_non_tty(self, mock_print, mock_isatty):
        utils.run_pager("Sample Diff Content")
        mock_print.assert_called_once_with("Sample Diff Content")

    @patch("sys.stdout.isatty", return_value=True)
    @patch("subprocess.run")
    def test_run_pager_interactive_tty(self, mock_subproc, mock_isatty):
        with patch.dict(os.environ, {"PAGER": "less -FRX"}):
            utils.run_pager("Paged Output")
            mock_subproc.assert_called_once()
            args, kwargs = mock_subproc.call_args
            self.assertEqual(args[0], ["less", "-FRX"])
            self.assertEqual(kwargs.get("input"), "Paged Output")

    @patch("sys.stdout.isatty", return_value=True)
    @patch("subprocess.run", side_effect=BrokenPipeError())
    def test_run_pager_catches_broken_pipe(self, mock_subproc, mock_isatty):
        # BrokenPipeError should be caught cleanly without raising
        utils.run_pager("Broken Pipe Test")


class TestVersionCompatibility(unittest.TestCase):
    """Tests for Python 3.6.4+ invariant."""

    def test_text_mode_flag(self):
        if sys.version_info >= (3, 7):
            self.assertEqual(utils.TEXT_MODE, {"text": True})
        else:
            self.assertEqual(utils.TEXT_MODE, {"universal_newlines": True})


class TestColorConstants(unittest.TestCase):
    """Tests for ANSI color constants."""

    def test_color_constants_defined(self):
        self.assertEqual(utils.COLOR_RESET, "\033[0m")
        self.assertEqual(utils.COLOR_BOLD, "\033[1m")
        self.assertEqual(utils.COLOR_RED, "\033[31m")
        self.assertEqual(utils.COLOR_GREEN, "\033[32m")
        self.assertEqual(utils.COLOR_YELLOW, "\033[33m")
        self.assertEqual(utils.COLOR_BLUE, "\033[34m")
        self.assertEqual(utils.COLOR_MAGENTA, "\033[35m")
        self.assertEqual(utils.COLOR_CYAN, "\033[36m")
        self.assertEqual(utils.COLOR_WHITE, "\033[37m")


if __name__ == "__main__":
    unittest.main()
