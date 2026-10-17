#!/usr/bin/env python3
"""
Unit tests for advanced gfp-cli commands:
diff, commit, status, branch, switch, stash, rebase, reopen, resolve, restore, pull, push.
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

from commands import (
    branch,
    commit,
    diff,
    pull,
    push,
    rebase,
    reopen,
    resolve,
    restore,
    stash,
    status,
    switch,
)


class TestCommandDiff(unittest.TestCase):
    """Tests for commands/diff.py helper functions and execution."""

    def test_parse_opened_line(self):
        line = "//stream/main/src/app.py#2 - edit default change (text)"
        depot_path, action, rev = diff.parse_opened_line(line)
        self.assertEqual(depot_path, "//stream/main/src/app.py")
        self.assertEqual(action, "edit")
        self.assertEqual(rev, "2")

        line_add = "... //stream/main/new_file.txt#1 - add change 10 (text)"
        depot_path, action, rev = diff.parse_opened_line(line_add)
        self.assertEqual(depot_path, "//stream/main/new_file.txt")
        self.assertEqual(action, "add")
        self.assertEqual(rev, "1")

        self.assertEqual(diff.parse_opened_line("invalid line"), (None, None, None))

    def test_generate_diffstat(self):
        sample_diff = """==== //stream/main/file1.py#1 (text) ====
--- file1.py.orig
+++ file1.py
@@ -1,2 +1,4 @@
 line 1
+line 2
+line 3
-old line
==== //stream/main/file2.py#1 (add) ====
--- /dev/null
+++ file2.py
@@ -0,0 +1,2 @@
+new 1
+new 2
"""
        diffstat = diff.generate_diffstat(sample_diff)
        self.assertIn("file1.py", diffstat)
        self.assertIn("file2.py", diffstat)
        self.assertIn("2 files changed", diffstat)
        self.assertIn("4 insertions(+)", diffstat)
        self.assertIn("1 deletion(-)", diffstat)

    def test_generate_diffstat_empty(self):
        self.assertEqual(diff.generate_diffstat(""), "")
        self.assertEqual(diff.generate_diffstat("   "), "")

    def test_get_synthetic_diff_for_add(self):
        mock_run_p4 = MagicMock(return_value="... clientFile /tmp/test_file.py\n")
        with patch("os.path.isfile", return_value=True):
            with patch("builtins.open", unittest.mock.mock_open(read_data="print('hello')\n")):
                syn = diff.get_synthetic_diff_for_add(mock_run_p4, "//stream/main/test_file.py", rev="1")
                self.assertIn("==== //stream/main/test_file.py#1 (add) ====", syn)
                self.assertIn("--- /dev/null", syn)
                self.assertIn("+print('hello')", syn)

    def test_diff_dot_path_does_not_filter_out_opened_entries(self):
        mock_run_p4 = MagicMock()
        mock_run_p4.side_effect = [
            # opened
            "//stream/main/app.py#1 - edit default change (text)\n",
            # diff -du
            "--- app.py\n+++ app.py\n@@ -1 +1 @@\n-old\n+new\n",
        ]
        args = argparse.Namespace(path=".", cl=None, stat=False, cached=False)
        with patch("commands.diff.run_pager") as mock_pager:
            diff.execute(args, run_p4=mock_run_p4)
            mock_pager.assert_called_once()
            self.assertIn("+new", mock_pager.call_args[0][0])

    def test_diff_unopened_file(self):
        mock_run_p4 = MagicMock()
        mock_run_p4.side_effect = [
            # opened (no matching files)
            "",
            # diff -du -f unopened.txt
            "==== //stream/main/unopened.txt#1 (text) ====\n--- unopened.txt\n+++ unopened.txt\n@@ -1 +1 @@\n-old\n+new\n",
        ]
        args = argparse.Namespace(path="unopened.txt", cl=None, stat=False)
        with patch("commands.diff.run_pager") as mock_pager:
            diff.execute(args, run_p4=mock_run_p4)
            self.assertEqual(mock_run_p4.call_args_list[0][0][0], ["opened"])
            self.assertEqual(mock_run_p4.call_args_list[1][0][0], ["diff", "-du", "-f", "unopened.txt"])
            mock_pager.assert_called_once()
            self.assertIn("+new", mock_pager.call_args[0][0])

    def test_diff_no_opened_files_fallback_to_force(self):
        mock_run_p4 = MagicMock()
        mock_run_p4.side_effect = [
            # opened
            "",
            # diff -du -f ...
            "==== //stream/main/unopened.txt#1 (text) ====\n--- unopened.txt\n+++ unopened.txt\n@@ -1 +1 @@\n-old\n+new\n",
        ]
        args = argparse.Namespace(path=None, cl=None, stat=False)
        with patch("commands.diff.run_pager") as mock_pager:
            diff.execute(args, run_p4=mock_run_p4)
            self.assertEqual(mock_run_p4.call_args_list[0][0][0], ["opened"])
            self.assertEqual(mock_run_p4.call_args_list[1][0][0], ["diff", "-du", "-f", "..."])
            mock_pager.assert_called_once()
            self.assertIn("+new", mock_pager.call_args[0][0])

    def test_colorize_diff(self):
        raw_diff = (
            "Change 100 by user@ws\n"
            "==== //stream/main/file.py#1 (text) ====\n"
            "--- file.py\n"
            "+++ file.py\n"
            "@@ -1,2 +1,3 @@\n"
            " context line\n"
            "-deleted line\n"
            "+added line\n"
            "\\ No newline at end of file\n"
        )
        colored = diff.colorize_diff(raw_diff)
        self.assertIn("\033[33mChange 100 by user@ws\033[0m", colored)
        self.assertIn("\033[1m==== //stream/main/file.py#1 (text) ====\033[0m", colored)
        self.assertIn("\033[1m--- file.py\033[0m", colored)
        self.assertIn("\033[1m+++ file.py\033[0m", colored)
        self.assertIn("\033[36m@@ -1,2 +1,3 @@\033[0m", colored)
        self.assertIn(" context line", colored)
        self.assertIn("\033[31m-deleted line\033[0m", colored)
        self.assertIn("\033[32m+added line\033[0m", colored)
        self.assertIn("\033[1m\\ No newline at end of file\033[0m", colored)

    def test_colorize_diff_empty(self):
        self.assertEqual(diff.colorize_diff(""), "")
        self.assertIsNone(diff.colorize_diff(None))

    def test_generate_diffstat_colored(self):
        sample_diff = """==== //stream/main/file1.py#1 (text) ====
--- file1.py.orig
+++ file1.py
@@ -1,2 +1,4 @@
 line 1
+line 2
+line 3
-old line
"""
        stat_plain = diff.generate_diffstat(sample_diff, color=False)
        stat_color = diff.generate_diffstat(sample_diff, color=True)
        self.assertNotIn("\033[", stat_plain)
        self.assertIn("\033[32m++\033[31m-\033[0m", stat_color)
        self.assertIn("1 file changed", stat_color)

    def test_should_colorize(self):
        self.assertTrue(diff.should_colorize("always"))
        self.assertFalse(diff.should_colorize("never"))

        with patch("sys.stdout.isatty", return_value=True):
            with patch.dict("os.environ", {}, clear=True):
                self.assertTrue(diff.should_colorize("auto"))

        with patch("sys.stdout.isatty", return_value=False):
            with patch.dict("os.environ", {}, clear=True):
                self.assertFalse(diff.should_colorize("auto"))

        with patch("sys.stdout.isatty", return_value=True):
            with patch.dict("os.environ", {"NO_COLOR": "1"}):
                self.assertFalse(diff.should_colorize("auto"))
                # "always" overrides NO_COLOR
                self.assertTrue(diff.should_colorize("always"))

    def test_diff_color_flags_parsing(self):
        parser = argparse.ArgumentParser()
        diff.setup_parser(parser)

        args = parser.parse_args([])
        self.assertEqual(args.color, "auto")

        args = parser.parse_args(["--color"])
        self.assertEqual(args.color, "always")

        args = parser.parse_args(["--color=always"])
        self.assertEqual(args.color, "always")

        args = parser.parse_args(["--color=never"])
        self.assertEqual(args.color, "never")

        args = parser.parse_args(["--color=auto"])
        self.assertEqual(args.color, "auto")

        args = parser.parse_args(["--no-color"])
        self.assertEqual(args.color, "never")

        args = parser.parse_args(["--color", "my_file.py"])
        self.assertEqual(args.color, "always")
        if args.path is None and getattr(args, "_swallowed_path", None):
            args.path = args._swallowed_path
        self.assertEqual(args.path, "my_file.py")

        with patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--color=invalid_choice"])

    def test_diff_execute_color_modes(self):
        mock_run_p4 = MagicMock()
        mock_run_p4.side_effect = [
            # opened
            "",
            # diff -du -f ...
            "==== //stream/main/app.py#1 (text) ====\n--- app.py\n+++ app.py\n@@ -1 +1 @@\n-old\n+new\n",
            # opened
            "",
            # diff -du -f ...
            "==== //stream/main/app.py#1 (text) ====\n--- app.py\n+++ app.py\n@@ -1 +1 @@\n-old\n+new\n",
        ]
        args_color = argparse.Namespace(path=None, cl=None, stat=False, color="always")
        with patch("commands.diff.run_pager") as mock_pager:
            diff.execute(args_color, run_p4=mock_run_p4)
            output = mock_pager.call_args[0][0]
            self.assertIn("\033[32m+new\033[0m", output)
            self.assertIn("\033[31m-old\033[0m", output)

        args_nocolor = argparse.Namespace(path=None, cl=None, stat=False, color="never")
        with patch("commands.diff.run_pager") as mock_pager:
            diff.execute(args_nocolor, run_p4=mock_run_p4)
            output = mock_pager.call_args[0][0]
            self.assertNotIn("\033[", output)
            self.assertIn("+new", output)


class TestCommandStatus(unittest.TestCase):
    """Tests for commands/status.py."""

    def test_parse_opened_line(self):
        self.assertEqual(
            status.parse_opened_line("//stream/main/f.py#1 - edit default change (text)")[0],
            "default",
        )
        self.assertEqual(
            status.parse_opened_line("//stream/main/f.py#1 - edit change 42 (text)")[0],
            "42",
        )

    def test_parse_reconcile_line(self):
        self.assertEqual(
            status.parse_reconcile_line("//stream/main/a.py#2 - opened for edit"),
            ("modified", "//stream/main/a.py#2 - opened for edit"),
        )
        self.assertEqual(
            status.parse_reconcile_line("//stream/main/b.py#1 - opened for add"),
            ("new", "//stream/main/b.py#1 - opened for add"),
        )
        self.assertEqual(
            status.parse_reconcile_line("//stream/main/c.py#1 - opened for delete"),
            ("deleted", "//stream/main/c.py#1 - opened for delete"),
        )
        self.assertEqual(
            status.parse_reconcile_line("src/a.py - reconcile to edit //stream/main/src/a.py#1"),
            ("modified", "src/a.py - reconcile to edit //stream/main/src/a.py#1"),
        )
        self.assertEqual(
            status.parse_reconcile_line("... - no file(s) to reconcile."),
            (None, None),
        )

    def test_get_shelved_files(self):
        describe_out = """Change 100 by devuser@client
Shelved files ...
... //stream/main/src/a.py#1 edit
... //stream/main/src/b.py#1 add
Differences ...
"""
        mock_run_p4 = MagicMock(return_value=describe_out)
        shelved = status.get_shelved_files(100, mock_run_p4)
        self.assertEqual(shelved, ["//stream/main/src/a.py#1 edit", "//stream/main/src/b.py#1 add"])

    @patch("commands.status.get_active_client", return_value="devuser_ws")
    @patch("commands.status.get_active_stream", return_value="//stream/main")
    def test_execute_categorizes_reconcile_and_preserves_opened(self, _mock_stream, _mock_client):
        def fake_run_p4(cmd, **kwargs):
            if cmd == ["opened"]:
                return "//stream/main/staged.py#1 - edit change 42 (text)\n"
            if cmd[:3] == ["changes", "-s", "pending"]:
                return "Change 42 on 2026/10/16 by devuser@devuser_ws *pending* 'WIP'\n"
            if cmd[:6] == ["reconcile", "-n", "-e", "-a", "-d", "-f"]:
                return (
                    "//stream/main/mod.py#2 - opened for edit\n"
                    "//stream/main/new.py#1 - opened for add\n"
                    "//stream/main/del.py#1 - opened for delete\n"
                )
            return ""

        mock_run_p4 = MagicMock(side_effect=fake_run_p4)
        args = argparse.Namespace(pending_cl=False)
        with patch("builtins.print") as mock_print:
            status.execute(args, run_p4=mock_run_p4)
            printed = "\n".join(call[0][0] for call in mock_print.call_args_list if call[0])

        mock_run_p4.assert_any_call(
            ["reconcile", "-n", "-e", "-a", "-d", "-f", "..."],
            capture=True,
            check=False,
        )
        self.assertIn("Changes opened for commit:", printed)
        self.assertIn("Changelist 42:", printed)
        self.assertIn("(opened)  //stream/main/staged.py#1 - edit change 42 (text)", printed)
        self.assertIn("Modified files:", printed)
        self.assertIn("(modified)  //stream/main/mod.py#2 - opened for edit", printed)
        self.assertIn("New / Untracked files:", printed)
        self.assertIn("(new file)  //stream/main/new.py#1 - opened for add", printed)
        self.assertIn("Deleted files:", printed)
        self.assertIn("(deleted)   //stream/main/del.py#1 - opened for delete", printed)


class TestCommandCommit(unittest.TestCase):
    """Tests for commands/commit.py."""

    def test_apply_description_and_save(self):
        spec_template = """Change:\tnew
Client:\tdevuser_ws
User:\tdevuser
Status:\tnew
Description:
\t<enter description here>
Files:
\t//stream/main/foo.py\t# edit
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Change 200 created.", returncode=0)
            out = commit.apply_description_and_save(spec_template, "Feature XYZ", strip_files=False)
            self.assertEqual(out, "Change 200 created.")
            mock_run.assert_called_once()
            call_input = mock_run.call_args[1].get("input", "")
            self.assertIn("Description:\n\tFeature XYZ", call_input)
            self.assertIn("Files:\n\t//stream/main/foo.py", call_input)

    def test_apply_description_and_save_strip_files(self):
        spec_template = """Change:\tnew
Description:
\tInitial
Files:
\t//stream/main/foo.py\t# edit
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Change 201 created.", returncode=0)
            commit.apply_description_and_save(spec_template, "New Msg", strip_files=True)
            call_input = mock_run.call_args[1].get("input", "")
            self.assertNotIn("Files:", call_input)

    def test_commit_requires_message(self):
        mock_run_p4 = MagicMock(return_value="//stream/main/file.py#1 - edit default change")
        args = argparse.Namespace(files=[], message=None, amend=False, all=False, cl=None)
        with self.assertRaises(SystemExit) as ctx:
            commit.execute(args, run_p4=mock_run_p4)
        self.assertEqual(ctx.exception.code, 1)


class TestCommandRestore(unittest.TestCase):
    """Tests for commands/restore.py."""

    def test_restore_staged_calls_revert_k(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=["app.py"], staged=True, cl=None, keep=False, worktree=False)
        restore.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["revert", "-k", "app.py"], capture=False)

    def test_restore_worktree_calls_clean_and_revert(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=["app.py"], staged=False, cl=None, keep=False, worktree=True)
        restore.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        self.assertEqual(mock_run_p4.call_count, 2)
        self.assertEqual(mock_run_p4.call_args_list[0][0][0], ["clean", "-e", "-d", "app.py"])
        self.assertEqual(mock_run_p4.call_args_list[1][0][0], ["revert", "app.py"])

    def test_restore_default_targets_all_files(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=[], staged=False, cl=None, keep=False, worktree=False)
        restore.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        self.assertEqual(mock_run_p4.call_count, 2)
        self.assertEqual(mock_run_p4.call_args_list[0][0][0], ["clean", "-e", "-d", "..."])
        self.assertEqual(mock_run_p4.call_args_list[1][0][0], ["revert", "..."])

    def test_restore_cl_deletes_pending_cl(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=[], staged=False, cl="50", keep=False, worktree=False)
        restore.execute(args, run_p4=mock_run_p4)
        self.assertEqual(mock_run_p4.call_count, 3)
        # 1: revert -c 50 ...
        # 2: shelve -d -c 50
        # 3: change -d 50
        calls = mock_run_p4.call_args_list
        self.assertEqual(calls[0][0][0], ["revert", "-c", "50", "..."])
        self.assertEqual(calls[1][0][0], ["shelve", "-d", "-c", "50"])
        self.assertEqual(calls[2][0][0], ["change", "-d", "50"])


class TestCommandRebase(unittest.TestCase):
    """Tests for commands/rebase.py."""

    def test_rebase_missing_args(self):
        args = argparse.Namespace(squash=None, onto=None, interactive=False, message=None)
        with self.assertRaises(SystemExit) as ctx:
            rebase.execute(args, run_p4=MagicMock())
        self.assertEqual(ctx.exception.code, 1)

    def test_rebase_same_cl(self):
        args = argparse.Namespace(squash="10", onto="10", interactive=False, message=None)
        with self.assertRaises(SystemExit) as ctx:
            rebase.execute(args, run_p4=MagicMock())
        self.assertEqual(ctx.exception.code, 1)

    def test_rebase_squash_success(self):
        def mock_p4_call(cmd, **kwargs):
            if cmd == ["change", "-o", "20"]:
                return "Description:\n\tFeature B"
            if cmd == ["change", "-o", "10"]:
                return "Description:\n\tFeature A"
            if cmd == ["opened", "-c", "20"]:
                return "//stream/main/f1.txt#1 - edit change 20 (text)\n"
            return ""

        mock_run_p4 = MagicMock(side_effect=mock_p4_call)
        args = argparse.Namespace(squash="20", onto="10", interactive=False, message=None)

        with patch("subprocess.run") as mock_subproc:
            mock_subproc.return_value = MagicMock(returncode=0)
            rebase.execute(args, run_p4=mock_run_p4)

        # Should reopen files into target CL 10
        mock_run_p4.assert_any_call(["reopen", "-c", "10", "//stream/main/f1.txt"], capture=False, check=True)
        # Should delete source CL 20
        mock_run_p4.assert_any_call(["change", "-d", "20"], capture=False, check=True)


class TestCommandReopen(unittest.TestCase):
    """Tests for commands/reopen.py."""

    def test_reopen_default_target(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=["file1.py"], cl="default")
        reopen.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["reopen", "-c", "default", "file1.py"], capture=False)

    def test_reopen_numbered_cl(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=["file2.py"], cl="77")
        reopen.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["reopen", "-c", "77", "file2.py"], capture=False)


class TestCommandResolve(unittest.TestCase):
    """Tests for commands/resolve.py."""

    def test_resolve_ours_flag(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=[], ours=True, theirs=False, am=False, dry_run=False)
        resolve.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["resolve", "-ay", "..."], capture=False, check=False)

    def test_resolve_theirs_flag(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=["conflict.txt"], ours=False, theirs=True, am=False, dry_run=False)
        resolve.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: p)
        mock_run_p4.assert_called_once_with(["resolve", "-at", "conflict.txt"], capture=False, check=False)

    def test_resolve_dry_run(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(files=[], ours=False, theirs=False, am=True, dry_run=True)
        resolve.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["resolve", "-n", "-am", "..."], capture=False, check=False)


class TestCommandPull(unittest.TestCase):
    """Tests for commands/pull.py."""

    def test_pull_dry_run(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(paths=[], force=False, dry_run=True)
        pull.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["sync", "-n"], capture=False)

    def test_pull_force_and_resolve(self):
        mock_run_p4 = MagicMock()
        mock_run_p4.side_effect = [None, "//stream/main/file.py - merging //stream/main/file.py#2"]
        args = argparse.Namespace(paths=["src/"], force=True, dry_run=False)
        pull.execute(args, run_p4=mock_run_p4, to_p4_path=lambda p: f"{p}...")
        mock_run_p4.assert_any_call(["sync", "-f", "src/..."], capture=False)
        mock_run_p4.assert_any_call(["resolve", "-am", "src/..."], capture=True, check=False)


class TestCommandBranch(unittest.TestCase):
    """Tests for commands/branch.py."""

    def test_branch_delete(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(name="//stream/dev", delete=True, all=False, verbose=False, parent=None, type="development")
        branch.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_with(["stream", "-d", "//stream/dev"], capture=False)

    def test_branch_delete_requires_name(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(name=None, delete=True, all=False, verbose=False, parent=None, type="development")
        with self.assertRaises(SystemExit) as ctx:
            branch.execute(args, run_p4=mock_run_p4)
        self.assertEqual(ctx.exception.code, 1)


class TestCommandPush(unittest.TestCase):
    """Tests for commands/push.py."""

    def test_push_force_direct_submit(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(cl="123", force=True, dry_run=False, gated=False)
        push.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_any_call(["submit", "-c", "123"], capture=False)

    def test_push_gated_shelves_change(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(cl="123", force=False, dry_run=False, gated=True)
        push.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_called_once_with(["shelve", "-r", "-c", "123"], capture=False)

    def test_push_dry_run(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(cl="123", force=False, dry_run=True, gated=False)
        push.execute(args, run_p4=mock_run_p4)
        # Dry-run inspects opened files without shelving or submitting
        mock_run_p4.assert_called_with(["opened", "-c", "123"], quiet=True)


class TestCommandSwitch(unittest.TestCase):
    """Tests for commands/switch.py."""

    def test_switch_list(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(stream=None, list=True, create=False, parent=None, type=None, stash=False)
        switch.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_any_call(["switch", "-l"], capture=False)

    def test_switch_target_stream(self):
        mock_run_p4 = MagicMock()
        args = argparse.Namespace(stream="//stream/dev", list=False, create=False, parent=None, type=None, stash=False)
        switch.execute(
            args,
            run_p4=mock_run_p4,
            get_active_stream=lambda p: "//stream/main",
            resolve_stream_path=lambda s, a: s,
        )
        mock_run_p4.assert_any_call(["switch", "//stream/dev"], capture=False)


class TestCommandStash(unittest.TestCase):
    """Tests for commands/stash.py."""

    def test_stash_list(self):
        mock_run_p4 = MagicMock(return_value="Change 100 on 2026/09/13 by devuser@client *pending* 'Stash msg'")
        args = argparse.Namespace(action="list", message=None, cl=None)
        with patch("commands.stash.get_client_name", return_value="devuser_ws"):
            stash.execute(args, run_p4=mock_run_p4)
            mock_run_p4.assert_called_with(["changes", "-s", "shelved", "-c", "devuser_ws"], capture=False)

    def test_stash_drop(self):
        mock_run_p4 = MagicMock(return_value="")
        args = argparse.Namespace(action="drop", message=None, cl="100")
        stash.execute(args, run_p4=mock_run_p4)
        mock_run_p4.assert_any_call(["shelve", "-d", "-c", "100"], capture=False)
        mock_run_p4.assert_any_call(["change", "-d", "100"], capture=False)


if __name__ == "__main__":
    unittest.main()
