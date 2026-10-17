#!/usr/bin/env python3
"""
Unit tests for gfp.py - Core CLI engine, workspace resolution, hook dispatcher, and plugin loader.
Compatible with Python >= 3.6.4.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import gfp


class TestCommandRunners(unittest.TestCase):
    """Tests for run_cmd and run_p4."""

    def test_run_cmd_success_capture(self):
        output = gfp.run_cmd([sys.executable, "-c", "print('hello_gfp')"], capture=True)
        self.assertEqual(output, "hello_gfp")

    def test_run_cmd_custom_env(self):
        output = gfp.run_cmd(
            [sys.executable, "-c", "import os; print(os.environ.get('CUSTOM_GFP_VAR'))"],
            capture=True,
            env={"CUSTOM_GFP_VAR": "custom_val_123"},
        )
        self.assertEqual(output, "custom_val_123")

    def test_run_cmd_failure_raises_system_exit(self):
        with self.assertRaises(SystemExit) as ctx:
            gfp.run_cmd([sys.executable, "-c", "import sys; sys.exit(42)"], capture=True, quiet=True)
        self.assertEqual(ctx.exception.code, 42)

    def test_run_cmd_executable_not_found(self):
        with self.assertRaises(SystemExit) as ctx:
            gfp.run_cmd(["non_existent_executable_12345"], capture=True, quiet=True)
        self.assertEqual(ctx.exception.code, 1)

    @patch("gfp.run_cmd")
    def test_run_p4_delegates_to_run_cmd(self, mock_run_cmd):
        gfp.run_p4(["info"], capture=True, check=True)
        mock_run_cmd.assert_called_once_with(["p4", "info"], capture=True, check=True, quiet=False)


class TestHookLifecycleEngine(unittest.TestCase):
    """Tests for find_hook and execute_hook."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws_dir = Path(self.temp_dir)
        self.hooks_dir = self.ws_dir / ".gfp" / "hooks"
        self.hooks_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_hook_hyphenated(self):
        hook_file = self.hooks_dir / "pre-commit"
        hook_file.write_text("#!/bin/sh\nexit 0\n")
        hook_file.chmod(0o755)

        with patch.object(gfp, "WORKSPACE_ROOT", self.ws_dir):
            found = gfp.find_hook("pre", "commit")
            self.assertIsNotNone(found)
            self.assertEqual(found, hook_file)

    def test_find_hook_underscored(self):
        hook_file = self.hooks_dir / "post_commit"
        hook_file.write_text("#!/bin/sh\nexit 0\n")
        hook_file.chmod(0o755)

        with patch.object(gfp, "WORKSPACE_ROOT", self.ws_dir):
            found = gfp.find_hook("post", "commit")
            self.assertIsNotNone(found)
            self.assertEqual(found, hook_file)

    def test_find_hook_ignores_non_executable(self):
        hook_file = self.hooks_dir / "pre-push"
        hook_file.write_text("#!/bin/sh\nexit 0\n")
        hook_file.chmod(0o644)  # Not executable

        with patch.object(gfp, "WORKSPACE_ROOT", self.ws_dir):
            found = gfp.find_hook("pre", "push")
            self.assertIsNone(found)

    def test_execute_hook_passes_environment_variables(self):
        hook_file = self.hooks_dir / "pre-status"
        # Hook script will dump its environment variables to a temp log file
        log_file = self.ws_dir / "hook_env.log"
        script = f"""#!/bin/sh
echo "$GFP_COMMAND $GFP_HOOK_STAGE $GFP_WORKSPACE_ROOT $GFP_ARGS" > "{log_file}"
exit 0
"""
        hook_file.write_text(script)
        hook_file.chmod(0o755)

        with patch.object(gfp, "WORKSPACE_ROOT", self.ws_dir):
            gfp.execute_hook("pre", "status", ["-c", "--detail"])

        self.assertTrue(log_file.is_file())
        logged = log_file.read_text().strip()
        expected = f"status pre {self.ws_dir} -c --detail"
        self.assertEqual(logged, expected)

    def test_execute_hook_aborts_on_non_zero_exit(self):
        hook_file = self.hooks_dir / "pre-commit"
        hook_file.write_text("#!/bin/sh\nexit 3\n")
        hook_file.chmod(0o755)

        with patch.object(gfp, "WORKSPACE_ROOT", self.ws_dir):
            with self.assertRaises(SystemExit) as ctx:
                gfp.execute_hook("pre", "commit", [])
            self.assertEqual(ctx.exception.code, 3)


class TestAliasEngine(unittest.TestCase):
    """Tests for load_aliases and alias expansion."""

    def test_default_aliases_present(self):
        aliases = gfp.load_aliases()
        self.assertIn("st", aliases)
        self.assertEqual(aliases["st"], "status")
        self.assertIn("ci", aliases)
        self.assertEqual(aliases["ci"], "commit")
        self.assertIn("co", aliases)
        self.assertEqual(aliases["co"], "checkout")
        self.assertIn("br", aliases)
        self.assertEqual(aliases["br"], "branch")
        self.assertIn("di", aliases)
        self.assertEqual(aliases["di"], "diff")
        self.assertIn("sw", aliases)
        self.assertEqual(aliases["sw"], "switch")

    def test_load_aliases_from_workspace_config(self):
        temp_dir = tempfile.mkdtemp()
        try:
            ws = Path(temp_dir)
            gfp_dir = ws / ".gfp"
            gfp_dir.mkdir()
            config_file = gfp_dir / "config.json"
            config_file.write_text(json.dumps({"aliases": {"custom-log": "log -n 5"}}))

            with patch.object(gfp, "WORKSPACE_ROOT", ws):
                aliases = gfp.load_aliases()
                self.assertEqual(aliases.get("custom-log"), "log -n 5")
                # Default aliases should still be preserved
                self.assertEqual(aliases.get("st"), "status")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestPluginDiscovery(unittest.TestCase):
    """Tests for discover_plugins."""

    def test_discover_built_in_python_plugins(self):
        plugins = gfp.discover_plugins()
        # All 20 built-in commands should be discovered
        expected_commands = [
            "add",
            "blame",
            "branch",
            "checkout",
            "clean",
            "clone",
            "commit",
            "completion",
            "diff",
            "log",
            "pull",
            "push",
            "rebase",
            "reopen",
            "resolve",
            "restore",
            "show",
            "stash",
            "status",
            "switch",
        ]
        for cmd in expected_commands:
            self.assertIn(cmd, plugins, f"Command '{cmd}' not found in discovered plugins")
            self.assertEqual(plugins[cmd]["type"], "python")
            self.assertTrue(hasattr(plugins[cmd]["module"], "execute"))

    def test_declarative_json_plugin(self):
        temp_dir = tempfile.mkdtemp()
        try:
            ws = Path(temp_dir)
            gfp_dir = ws / ".gfp"
            gfp_dir.mkdir()
            plugins_json = gfp_dir / "plugins.json"
            plugins_json.write_text(json.dumps({"my-tool": {"exec": "echo custom-tool", "help": "Custom external tool"}}))

            with patch.object(gfp, "WORKSPACE_ROOT", ws):
                plugins = gfp.discover_plugins()
                self.assertIn("my-tool", plugins)
                self.assertEqual(plugins["my-tool"]["type"], "external")
                self.assertEqual(plugins["my-tool"]["exec"], "echo custom-tool")
                self.assertEqual(plugins["my-tool"]["help"], "Custom external tool")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
