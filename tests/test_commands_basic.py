#!/usr/bin/env python3
"""
Unit tests for basic gfp-cli commands:
add, blame, checkout, clean, clone, completion, log, show.
Compatible with Python >= 3.6.4.
"""

import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from commands import add, blame, checkout, clean, clone, completion, log, show


class TestCommandAdd(unittest.TestCase):
    """Tests for commands/add.py."""

    def test_setup_parser(self):
        parser = argparse.ArgumentParser()
        add.setup_parser(parser)
        args = parser.parse_args(["file1.py", "file2.py"])
        self.assertEqual(args.files, ["file1.py", "file2.py"])
        self.assertFalse(args.all)
        self.assertFalse(args.update)

    def test_execute_default_target(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=[], all=True, update=False)
        add.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["reconcile", "-f", "..."], capture=False)

    def test_execute_specific_files(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=["src/main.py"], all=False, update=False)
        add.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: f"escaped_{p}")
        mock_run_p4.assert_called_once_with(["reconcile", "-f", "escaped_src/main.py"], capture=False)

    def test_execute_update(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=[], all=False, update=True)
        add.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["reconcile", "-f", "-e", "-d", "..."], capture=False)


class TestCommandCheckout(unittest.TestCase):
    """Tests for commands/checkout.py."""

    def test_setup_parser(self):
        parser = argparse.ArgumentParser()
        checkout.setup_parser(parser)
        args = parser.parse_args(["foo.txt"])
        self.assertEqual(args.files, ["foo.txt"])
        self.assertFalse(args.force)

    def test_execute_revert_default(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=[], force=False)
        checkout.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["revert", "..."], capture=False)

    def test_execute_revert_specific_files(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=["test.py"], force=False)
        checkout.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["revert", "test.py"], capture=False)


class TestCommandClean(unittest.TestCase):
    """Tests for commands/clean.py."""

    def test_setup_parser(self):
        parser = argparse.ArgumentParser()
        clean.setup_parser(parser)
        args = parser.parse_args(["-f", "-d"])
        self.assertTrue(args.force)
        self.assertTrue(args.d)
        self.assertFalse(args.dry_run)

    def test_execute_clean_without_force_defaults_to_dry_run(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(force=False, dry_run=False, d=False, paths=[])
        clean.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["clean", "-n", "..."], capture=False)

    def test_execute_clean_with_force_and_directory(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(force=True, dry_run=False, d=True, paths=["sub/"])
        clean.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: f"{p}...")
        mock_run_p4.assert_called_once_with(["clean", "sub/..."], capture=False)


class TestCommandClone(unittest.TestCase):
    """Tests for commands/clone.py."""

    def test_derive_default_dir(self):
        self.assertEqual(clone.derive_default_dir("//stream/main"), "main")
        self.assertEqual(clone.derive_default_dir("//stream/main/..."), "main")
        self.assertEqual(clone.derive_default_dir("//depot/project/feature"), "feature")
        self.assertEqual(clone.derive_default_dir("//"), "workspace")

    def test_setup_parser(self):
        parser = argparse.ArgumentParser()
        clone.setup_parser(parser)
        args = parser.parse_args(["//stream/main", "-c", "my_client", "-d", "target_dir"])
        self.assertEqual(args.repository, "//stream/main")
        self.assertEqual(args.client, "my_client")
        self.assertEqual(args.dir, "target_dir")


class TestCommandCompletion(unittest.TestCase):
    """Tests for commands/completion.py."""

    def test_completion_generation(self):
        for shell in ["bash", "zsh", "tcsh"]:
            args = argparse.Namespace(shell=shell)
            with patch("builtins.print") as mock_print:
                completion.execute(args, run_p4=MagicMock())
                mock_print.assert_called()
                output = mock_print.call_args[0][0]
                self.assertIn("gfp", output)


class TestCommandLog(unittest.TestCase):
    """Tests for commands/log.py."""

    def test_setup_parser(self):
        parser = argparse.ArgumentParser()
        log.setup_parser(parser)
        args = parser.parse_args(["-n", "10", "-a"])
        self.assertEqual(args.max_count, 10)
        self.assertTrue(args.all)

    @patch("commands.log.run_pager")
    def test_execute_log_default(self, mock_run_pager):
        mock_run_p4 = MagicMock(return_value="Change 100 on 2026/09/11 by devuser 'Test'")
        args = argparse.Namespace(max_count=5, all=False, patch=False, oneline=False, user=None, path=None)
        log.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["changes", "-m", "5", "-l", "..."], capture=True, check=False)
        mock_run_pager.assert_called_once()

    @patch("commands.log.run_pager")
    def test_execute_log_all(self, mock_run_pager):
        mock_run_p4 = MagicMock(return_value="Change 100 on 2026/09/11\nChange 99")
        args = argparse.Namespace(max_count=None, all=True, patch=False, oneline=False, user=None, path=None)
        log.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["changes", "-L", "..."], capture=True, check=False)
        mock_run_pager.assert_called_once()


class TestCommandBlameAndShow(unittest.TestCase):
    """Tests for commands/blame.py and commands/show.py."""

    @patch("commands.blame.run_pager")
    def test_blame_execute(self, mock_run_pager):
        mock_run_p4 = MagicMock(return_value="1: line 1 content\n2: line 2 content")
        args = argparse.Namespace(file="hello.py", cl=None, user=False, date=False, quiet=False, line_range=None)
        blame.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["annotate", "-c", "hello.py"], capture=True, check=True)
        mock_run_pager.assert_called_once_with("1: line 1 content\n2: line 2 content")

    @patch("commands.show.run_pager")
    def test_show_execute(self, mock_run_pager):
        mock_run_p4 = MagicMock(return_value="Change 10 by devuser@client\n\n\tInitial description")
        args = argparse.Namespace(cl="10", stat=False)
        show.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_any_call(["describe", "-du", "10"], capture=True, check=False)
        mock_run_pager.assert_called_once()


if __name__ == "__main__":
    unittest.main()
