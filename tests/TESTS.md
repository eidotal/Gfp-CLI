# `gfp-cli` Test Specifications & Test Cases

This document provides a comprehensive test-by-test breakdown of all unit tests and end-to-end (E2E) integration test suites for `gfp-cli`.

---

## Navigation & Cross-References

- **Parent Landing Hub:** [`./../README.md`](./../README.md)
- **Subsystem Gateway (Tests):** [`./README.md`](./README.md)
- **Subsystem Gateway (Commands):** [`./../commands/README.md`](./../commands/README.md)
- **Defect Registry:** [`./../BUG-TICKETS.md`](./../BUG-TICKETS.md)
- **Operational Invariants:** [`./../AGENTS.md`](./../AGENTS.md)

---

## Unit Suite: Centralized Utilities (`test_utils.py`)

### `test_escape_p4_path_none_and_empty`

**Goal**:

- Verify graceful handling of empty or `None` inputs in Perforce path escaping.

**Description**:

- Ensures `escape_p4_path` returns `None` when given `None` and an empty string when given `""` without throwing exceptions.

**Test-Flow**:

1. Call `escape_p4_path(None)`.
2. Call `escape_p4_path("")`.

**Check**:

- `escape_p4_path(None)` is `None`.
- `escape_p4_path("")` equals `""`.

---

### `test_escape_p4_path_individual_special_chars`

**Goal**:

- Verify individual Perforce special characters (`@`, `#`, `%`, `*`) are encoded into hexadecimal representations.

**Description**:

- Tests that `@` is converted to `%40`, `#` to `%23`, `%` to `%25`, and `*` to `%2A`.

**Test-Flow**:

1. Pass filenames containing `@`, `#`, `%`, and `*` individually to `escape_p4_path()`.

**Check**:

- `file@1.txt` &rarr; `file%401.txt`.
- `file#2.txt` &rarr; `file%232.txt`.
- `file%3.txt` &rarr; `file%253.txt`.
- `file*4.txt` &rarr; `file%2A4.txt`.

---

### `test_escape_p4_path_compound_order_prevents_double_encoding`

**Goal**:

- Validate the critical substitution ordering of `%` before `@`, `#`, and `*` to prevent double-encoding.

**Description**:

- Ensures that a string containing multiple special characters encodes `%` first so that downstream encodings (e.g., `%40`) are not erroneously re-escaped.

**Test-Flow**:

1. Define a raw path containing all special characters: `percent%_at@_hash#_star*.txt`.
2. Pass string through `escape_p4_path()`.

**Check**:

- Result matches `percent%25_at%40_hash%23_star%2A.txt`.

---

### `test_to_p4_path_wildcards_and_dots`

**Goal**:

- Verify conversion of Git-style current directory shortcuts (`.`, `./`, empty, `None`) to Perforce wildcard syntax (`...`).

**Description**:

- Ensures workspace-wide operations match Perforce's recursive ellipsis wildcard.

**Test-Flow**:

1. Pass `None`, `""`, `"."`, `"./"`, `"..."`, and `"dir/..."` to `to_p4_path()`.

**Check**:

- All root/empty/dot inputs evaluate to `"..."`.
- `"dir/..."` evaluates to `"dir/..."`.

---

### `test_to_p4_path_directories_and_files`

**Goal**:

- Validate directory trailing slashes map to recursive Perforce wildcards (`dir/...`).

**Description**:

- Confirms trailing directory slashes append `...` while regular filenames are preserved.

**Test-Flow**:

1. Pass `"src/"`, `"src/sub/"`, and `"main.py"` to `to_p4_path()`.

**Check**:

- `"src/"` &rarr; `"src/..."`.
- `"src/sub/"` &rarr; `"src/sub/..."`.
- `"main.py"` &rarr; `"main.py"`.

---

### `test_unescape_p4_path`

**Goal**:

- Verify reversible unescaping of Perforce hexadecimal sequences back to ASCII special characters.

**Description**:

- Ensures `%40`, `%23`, `%25`, and `%2A` correctly convert back to `@`, `#`, `%`, and `*`.

**Test-Flow**:

1. Call `unescape_p4_path()` on encoded filenames and compound strings.

**Check**:

- `%40` converts to `@`.
- `%23` converts to `#`.
- `%25` converts to `%`.
- `%2A` converts to `*`.
- `None` input returns `None`.

---

### `test_resolve_stream_path`

**Goal**:

- Test relative stream name resolution against the active stream depot.

**Description**:

- Verifies relative branch names (e.g., `dev`) resolve to fully-qualified stream paths (e.g., `//stream/dev`) based on active stream context.

**Test-Flow**:

1. Resolve an already absolute stream path `//stream/main`.
2. Resolve relative name `dev` with active stream `//stream/main`.
3. Resolve relative name `feature-x` with active stream `//my_depot/main`.
4. Resolve with empty or `None` active stream.

**Check**:

- Absolute streams remain unchanged (`//stream/main`).
- Relative streams inherit active depot prefix (`//stream/dev`, `//my_depot/feature-x`).

---

### `test_get_active_client_user_port_stream`

**Goal**:

- Verify Perforce environment and metadata resolvers.

**Description**:

- Tests resolution of active client workspace, user, port, and stream from environment variables and `p4 info` fallbacks.

**Test-Flow**:

1. Set `P4CLIENT`, `P4USER`, `P4PORT` in `os.environ` and verify immediate resolution.
2. Unset environment variables and mock `run_p4(["info"], capture=True)` output.
3. Query `get_active_client()`, `get_user()`, `get_p4port()`, and `get_active_stream()`.

**Check**:

- Environment variables take precedence when present.
- `p4 info` parsed values are returned correctly when environment variables are unset.

---

### `test_find_workspace_root`

**Goal**:

- Test workspace root resolution hierarchy.

**Description**:

- Tests resolution order: `.gfp` directory in parent tree &rarr; `Client root:` from `p4 info` &rarr; current working directory (`cwd`).

**Test-Flow**:

1. Create temporary directory structure with a `.gfp` marker in a parent directory.
2. Call `find_workspace_root()` from a nested subdirectory.
3. Test fallback to mocked `p4 info` Client root when no `.gfp` marker exists.
4. Test fallback to `Path.cwd()` when `p4 info` fails.

**Check**:

- Parent directory containing `.gfp` is identified as root.
- Client root from `p4 info` is used if `.gfp` is absent.
- `Path.cwd()` is returned as ultimate fallback.

---

### `test_run_pager`

**Goal**:

- Validate terminal pager execution, TTY detection, and signal handling.

**Description**:

- Ensures large command outputs are piped to `$PAGER` or `less -FRX` when stdout is a TTY, and handles early termination signals cleanly.

**Test-Flow**:

1. Test non-TTY environment (`isatty() == False`): prints text directly.
2. Test TTY environment: launches pager subprocess and writes content to stdin.
3. Simulate `BrokenPipeError` (user quits pager early) and `KeyboardInterrupt`.

**Check**:

- Output routes through pager when TTY is active.
- `BrokenPipeError` and `KeyboardInterrupt` are handled silently without stack traces.

---

## Unit Suite: Core CLI Engine & Hooks (`test_gfp_core.py`)

### `test_run_cmd_and_run_p4`

**Goal**:

- Test subprocess execution wrapper and `p4` command delegation.

**Description**:

- Validates stdout capture, environment injection, exit code checks, and error raising in `run_cmd` and `run_p4`.

**Test-Flow**:

1. Run successful command with `capture=True` and verify output.
2. Pass custom environment dict to `run_cmd`.
3. Run failing command and verify `SystemExit` is raised with the process exit code.
4. Verify non-existent binary raises `SystemExit(1)`.
5. Verify `run_p4` prepends `"p4"` to arguments and delegates to `run_cmd`.

**Check**:

- Stdout is captured correctly.
- Custom environment variables are passed to child processes.
- Non-zero process exits raise `SystemExit` with matching code.

---

### `test_find_hook`

**Goal**:

- Test discovery of pre- and post-command lifecycle hook scripts.

**Description**:

- Tests searching for executable hook files supporting both hyphenated (`pre-commit`) and underscored (`pre_commit`) naming conventions in `.gfp/hooks/`.

**Test-Flow**:

1. Create executable `pre-commit` hook and query `find_hook("pre", "commit")`.
2. Create executable `post_commit` hook and query `find_hook("post", "commit")`.
3. Create non-executable hook file (`chmod 0644`) and query `find_hook`.

**Check**:

- Both hyphenated and underscored executable hooks are discovered.
- Non-executable files are ignored.

---

### `test_execute_hook`

**Goal**:

- Validate hook environment variable propagation and abort enforcement.

**Description**:

- Ensures `GFP_COMMAND`, `GFP_HOOK_STAGE`, `GFP_WORKSPACE_ROOT`, and `GFP_ARGS` are exported to hook scripts, and non-zero exit codes abort command execution.

**Test-Flow**:

1. Create a `pre-status` hook that logs environment variables to a temporary file.
2. Execute hook via `execute_hook("pre", "status", ["-s"])`.
3. Create a hook that exits with code `3` and execute it.

**Check**:

- Logged environment contains all expected `GFP_*` variables.
- Hook with exit code `3` raises `SystemExit(3)` to abort execution.

---

### `test_alias_expansion`

**Goal**:

- Test built-in command alias resolution.

**Description**:

- Verifies that Git-compatible shorthands expand to their full command equivalents.

**Test-Flow**:

1. Test default aliases: `ci` &rarr; `commit`, `st` &rarr; `status`, `co` &rarr; `checkout`, `br` &rarr; `branch`, `di` &rarr; `diff`, `sw` &rarr; `switch`.
2. Test unknown alias passes through unchanged.

**Check**:

- All registered alias keys map to correct target command names.

---

### `test_plugin_loader`

**Goal**:

- Test discovery and loading of external declarative plugins from `plugins.json`.

**Description**:

- Ensures custom commands declared in `.gfp/plugins.json` or `~/.gfp/plugins.json` are dynamically registered into the CLI engine.

**Test-Flow**:

1. Create `.gfp/plugins.json` defining custom plugin `"custom-tool"`.
2. Call plugin loader and verify registered commands.

**Check**:

- Plugin command name, help string, and execution target are loaded into the command table.

---

## Unit Suite: Basic Commands (`test_commands_basic.py`)

### `test_command_add`

**Goal**:

- Validate argument parsing and `p4 reconcile` translation for `gfp add`.

**Description**:

- Tests staging files, staging all files (`--all`), updating modified/deleted files (`--update`), and path escaping.

**Test-Flow**:

1. Parse CLI arguments for specific files, `-A`, and `-u`.
2. Execute command with mocked `run_p4`.

**Check**:

- Specific files invoke `p4 reconcile -f <escaped_path>`.
- `--all` invokes `p4 reconcile -f ...`.
- `--update` invokes `p4 reconcile -f -e -d ...`.

---

### `test_command_checkout`

**Goal**:

- Validate `p4 revert` translation for `gfp checkout`.

**Description**:

- Tests reverting local file modifications in the workspace.

**Test-Flow**:

1. Parse args for `gfp checkout foo.txt` and `gfp checkout -f foo.txt`.
2. Execute with mocked `run_p4`.

**Check**:

- Invokes `p4 revert <escaped_path>`.

---

### `test_command_clean`

**Goal**:

- Validate untracked file removal via `p4 clean`.

**Description**:

- Tests dry-run preview (`-n`) and force clean (`-f`, `-d`).

**Test-Flow**:

1. Parse args for dry-run (`-n`) and force clean (`-f -d`).
2. Execute with mocked `run_p4`.

**Check**:

- Dry-run translates to `p4 clean -n -d ...`.
- Force clean translates to `p4 clean -d ...`.

---

### `test_command_clone`

**Goal**:

- Validate stream cloning, client workspace creation, and file syncing.

**Description**:

- Tests workspace configuration (`allwrite clobber nocompress unlocked`), directory creation, and initial sync.

**Test-Flow**:

1. Parse args for `gfp clone //stream/main my_dir -c my_client`.
2. Execute with mocked `run_p4` and filesystem calls.

**Check**:

- Creates client workspace spec with stream mapping and Git-friendly options.
- Creates `.p4config` in target directory with `P4CLIENT` and `P4PORT`.
- Runs `p4 sync`.

---

### `test_command_blame`

**Goal**:

- Validate `p4 annotate` line history translation for `gfp blame`.

**Description**:

- Tests line-by-line file attribution history.

**Test-Flow**:

1. Parse args for `gfp blame file.py`.
2. Execute with mocked `run_p4`.

**Check**:

- Invokes `p4 annotate -u -c -q <escaped_path>` routed through pager.

---

### `test_command_log`

**Goal**:

- Validate `p4 changes` history listing for `gfp log`.

**Description**:

- Tests commit log display, count limits (`-n`), and multi-stream scope (`-a`).

**Test-Flow**:

1. Parse args for default log, `-n 5`, and `-a`.
2. Execute with mocked `run_p4`.

**Check**:

- Default log queries active stream path with `-m 20 -l`.
- `-a` queries all depot streams (`//...`).

---

### `test_command_show`

**Goal**:

- Validate `p4 describe` changelist inspection for `gfp show`.

**Description**:

- Tests viewing metadata and unified diff for specific changelist or latest submitted change.

**Test-Flow**:

1. Parse args for `gfp show` (latest) and `gfp show 1234` (specific CL).
2. Execute with mocked `run_p4`.

**Check**:

- Invokes `p4 describe -du <CL>` and routes output through pager.

---

### `test_command_completion`

**Goal**:

- Validate shell completion script generation.

**Description**:

- Tests output of completion scripts for Bash, Zsh, and TCSH.

**Test-Flow**:

1. Parse args for `gfp completion bash`, `zsh`, `tcsh`.
2. Execute command and capture output.

**Check**:

- Generates valid completion script syntax for the requested shell.

---

## Unit Suite: Advanced Commands (`test_commands_advanced.py`)

### `test_command_diff`

**Goal**:

- Validate unified diff generation, opened file parsing, and diffstat histogram calculations.

**Description**:

- Tests parsing `p4 opened` output, generating unified diffs against depot head or pending changelists (`-c`), and computing `--stat` summaries.

**Test-Flow**:

1. Parse opened file spec strings (`//stream/main/app.py#2 - edit default change (text)`).
2. Generate diffstat histogram from unified diff chunks.
3. Test pending changelist diff (`gfp diff -c <CL>`).
4. Test unopened file diffing (`p4 diff -du -f`).

**Check**:

- Correctly extracts depot path, action, and revision.
- Diffstat calculates added/deleted line counts and formatted histogram bars.
- Diff targets correct pending changelist files.
- Diff invokes `p4 diff -du -f` for unopened files.

---

### `test_command_commit`

**Goal**:

- Validate numbered pending changelist creation and modification.

**Description**:

- Tests creating new changelist with description, amending existing pending changelist (`--amend`), auto-reconcile (`-a`), and selective file commits.

**Test-Flow**:

1. Execute `gfp commit -m "msg"`.
2. Execute `gfp commit --amend -m "new msg"`.
3. Execute `gfp commit -a -m "msg"`.
4. Execute `gfp commit file1.py -m "msg"`.

**Check**:

- Uses `p4 change -i` to create or update changelist spec.
- Reopens files into target changelist via `p4 reopen -c <CL>`.
- Auto-reconcile triggers `p4 reconcile` before changelist creation.

---

### `test_command_status`

**Goal**:

- Validate workspace status reporting, Read-Write (`allwrite`) reconcile preview categorization, and pending changelist breakdown.

**Description**:

- Tests parsing opened lines (`parse_opened_line`), categorizing `p4 reconcile -n` / `p4 status` preview lines (`parse_reconcile_line`), executing `gfp status` (`p4 opened` grouped by changelist + `p4 reconcile -n -e -a -d -f` grouped into modified, new/untracked, and deleted files), and auditing shelved/pending changelists (`-c`).

**Test-Flow**:

1. Test `parse_opened_line` and `parse_reconcile_line` with edit, add, delete, and empty reconcile lines.
2. Execute `gfp status` with mocked `p4 opened`, `p4 changes -s pending`, and `p4 reconcile -n -e -a -d -f` outputs.
3. Execute `gfp status -c` (`get_shelved_files`) with mocked pending changelists.

**Check**:

- Displays opened changes grouped by default and numbered changelists.
- Invokes `p4 reconcile -n -e -a -d -f` across the workspace without `-s` directory collapsing and categorizes unreconciled files into `Modified files:`, `New / Untracked files:`, and `Deleted files:`.
- `-c` displays grouped pending changelists with opened and shelved file lists.

---

### `test_command_branch`

**Goal**:

- Validate stream branch listing, creation, and deletion.

**Description**:

- Tests listing streams with active stream indicator (`*`), verbose details (`-v`), stream creation (`-c`), and deletion (`-d`).

**Test-Flow**:

1. Execute `gfp branch` to list streams.
2. Execute `gfp branch //stream/dev -t development -P //stream/main` to create stream.
3. Execute `gfp branch -d //stream/dev` to delete stream.

**Check**:

- Marks current active stream with asterisk.
- Stream creation builds valid `p4 stream -i` specification.
- Deletion invokes `p4 stream -d <stream>`.

---

### `test_command_switch`

**Goal**:

- Validate stream switching and cross-stream auto-stashing.

**Description**:

- Tests switching active workspace stream and auto-stashing modified files (`-s`) with cross-stream unshelving.

**Test-Flow**:

1. Execute `gfp switch //stream/dev`.
2. Execute `gfp switch -s //stream/dev` with open workspace changes.

**Check**:

- Invokes `p4 client -s -S <target_stream>`.
- Auto-stash shelves changes (`//...`), switches stream, and unshelves via `p4 unshelve -s <CL> -S <from_stream>`.

---

### `test_command_stash`

**Goal**:

- Validate shelf management (`save`, `list`, `pop`, `show`, `drop`).

**Description**:

- Tests stashing modified files into Perforce shelves and restoring or discarding them.

**Test-Flow**:

1. Execute `gfp stash save -m "wip"`.
2. Execute `gfp stash list`.
3. Execute `gfp stash show stash@{0}`.
4. Execute `gfp stash pop`.
5. Execute `gfp stash drop stash@{0}`.

**Check**:

- `save` creates pending changelist and runs `p4 shelve`.
- `list` queries `p4 changes -s shelved`.
- `pop` runs `p4 unshelve`, reverts shelf, and deletes changelist.
- `drop` purges shelf (`p4 shelve -d`) and deletes changelist (`p4 change -d`).

---

### `test_command_rebase`

**Goal**:

- Validate pending changelist squashing.

**Description**:

- Tests combining source pending changelist into target changelist (`--squash <src> --onto <tgt>`).

**Test-Flow**:

1. Execute `gfp rebase --squash 20 --onto 10 -m "Combined message"`.

**Check**:

- Reopens all files from source changelist into target changelist (`p4 reopen -c 10`).
- Merges changelist descriptions.
- Deletes empty source changelist (`p4 change -d 20`).

---

### `test_command_reopen`

**Goal**:

- Validate moving opened files between changelists.

**Description**:

- Tests relocating files between numbered pending changelists and the default changelist.

**Test-Flow**:

1. Execute `gfp reopen -c default file1.py`.
2. Execute `gfp reopen -c 1234 file1.py`.

**Check**:

- Translates to `p4 reopen -c <target_cl> <files...>`.

---

### `test_command_resolve`

**Goal**:

- Validate conflict resolution options.

**Description**:

- Tests conflict resolution strategies: `--ours` (`-ay`), `--theirs` (`-at`), and dry-run preview (`-n`).

**Test-Flow**:

1. Execute `gfp resolve --ours file.py`.
2. Execute `gfp resolve --theirs file.py`.
3. Execute `gfp resolve -n`.

**Check**:

- Translates `--ours` to `p4 resolve -ay <file>`.
- Translates `--theirs` to `p4 resolve -at <file>`.
- Translates `-n` to `p4 resolve -n`.

---

### `test_command_restore`

**Goal**:

- Validate restoring working tree files, unstaging, and purging changelists.

**Description**:

- Tests reverting local modifications, unstaging files (`--staged`), and deleting pending changelists with shelves (`--cl`).

**Test-Flow**:

1. Execute `gfp restore file.py` (discard modifications).
2. Execute `gfp restore --staged file.py` (unstage keeping modifications).
3. Execute `gfp restore --cl 1234` (purge changelist and shelf).

**Check**:

- File restore translates to `p4 clean -e -d <file>` (for unopened files) and `p4 revert <file>` (for opened files).
- `--staged` translates to `p4 revert -k <file>`.
- `--cl` deletes shelf (`p4 shelve -d -c <CL>`) and deletes changelist (`p4 change -d <CL>`).

---

### `test_command_pull`

**Goal**:

- Validate depot revision syncing and safe auto-resolving.

**Description**:

- Tests syncing latest files, path filtering, force re-sync (`-f`), dry-run preview (`-n`), and auto-resolving non-conflicting changes (`p4 resolve -am`).

**Test-Flow**:

1. Execute `gfp pull -n`.
2. Execute `gfp pull`.
3. Execute `gfp pull -f`.

**Check**:

- Runs `p4 sync -n` for dry-run preview.
- Runs `p4 sync` followed by `p4 resolve -am` for standard pull.
- Runs `p4 sync -f` for force sync.

---

### `test_command_push`

**Goal**:

- Validate changelist submission workflows (gated submit queue vs force submit).

**Description**:

- Tests shelving changelist for Jenkins gated validation vs direct submit (`-f`).

**Test-Flow**:

1. Execute `gfp push` (gated mode).
2. Execute `gfp push -f` (direct mode).

**Check**:

- Gated mode creates numbered changelist, runs `p4 shelve`, and reports CI queuing.
- Force mode submits directly via `p4 submit -c <CL>`.

---

## Live Perforce E2E Integration Suite (`test_gfp.sh`)

### `Test 1: CLI Engine and Help Output`

**Goal**:

- Verify top-level CLI entry point discovery and help banner output.

**Description**:

- Confirms `gfp --help` returns exit code 0 and lists all core commands and aliases.

**Test-Flow**:

1. Execute `gfp --help`.

**Check**:

- Output contains `"Extensible Git-like CLI interface"`.
- Process exits with code 0.

---

### `Test 2: Status on Clean Workspace`

**Goal**:

- Verify status output when workspace has no modifications.

**Description**:

- Ensures `gfp status` reports clean state on an unmodified client workspace.

**Test-Flow**:

1. Reset workspace to pristine state.
2. Execute `gfp status`.

**Check**:

- Output contains `"working tree clean"` or `"no files currently opened"`.

---

### `Test 3: Add and Status with Isolated Test Files`

**Goal**:

- Verify file reconciliation and staging workflow.

**Description**:

- Creates a new isolated test file, stages it with `gfp add`, and verifies status detection.

**Test-Flow**:

1. Create new file `test_add_<RUN_ID>.py`.
2. Execute `gfp add test_add_<RUN_ID>.py`.
3. Execute `gfp status`.

**Check**:

- `gfp add` succeeds.
- `gfp status` outputs the newly staged test file.

---

### `Test 4: Unified Diff`

**Goal**:

- Verify unified diff generation against depot head.

**Description**:

- Submits baseline file to depot, modifies file locally, and asserts `gfp diff` emits standard unified diff chunks.

**Test-Flow**:

1. Create `test_diff_<RUN_ID>.txt` with baseline content and submit to depot.
2. Open file for edit and append modified line.
3. Execute `gfp diff test_diff_<RUN_ID>.txt`.
4. Execute `gfp diff --color test_diff_<RUN_ID>.txt` and `gfp diff --no-color test_diff_<RUN_ID>.txt`.
5. Create unopened file, submit baseline, modify on disk without `p4 edit`, and execute `gfp diff <unopened_file>`.

**Check**:

- Diff output contains added line `"+Line 2 modified <RUN_ID>"`.
- Diff output with `--color` contains ANSI green highlight codes for added lines.
- Diff output with `--no-color` contains raw text with no ANSI escape sequences.
- Unopened file diff outputs unified diff chunk against depot head.

---

### `Test 5: Commit (Create Pending Changelist)`

**Goal**:

- Verify pending changelist creation with commit message.

**Description**:

- Stages a new file and commits it to a numbered pending changelist.

**Test-Flow**:

1. Create `test_commit_<RUN_ID>.py`.
2. Execute `gfp add test_commit_<RUN_ID>.py`.
3. Execute `gfp commit -m "Add commit test module <RUN_ID>"`.

**Check**:

- Output reports `"Created pending changelist"` with a valid changelist number.

---

### `Test 6: Commit Amend (Amend Description & Reopen)`

**Goal**:

- Verify updating existing pending changelist description and adding newly staged files.

**Description**:

- Creates initial pending changelist, modifies file, and amends changelist with `--amend`.

**Test-Flow**:

1. Create `test_amend_<RUN_ID>.py`, add, and commit as pending changelist.
2. Append new lines to file and run `gfp add`.
3. Execute `gfp commit --amend -m "Amended description <RUN_ID>"`.

**Check**:

- Output confirms `"Amended pending changelist"`.
- Changelist description is updated.

---

### `Test 7: Show Changelist Details`

**Goal**:

- Verify inspection of pending changelist metadata and diff.

**Description**:

- Creates a pending changelist and validates `gfp show` outputs metadata and diff content.

**Test-Flow**:

1. Create and stage `test_show_<RUN_ID>.py`.
2. Commit to pending changelist with description `"Show test CL <RUN_ID>"`.
3. Execute `gfp show`.

**Check**:

- Output displays changelist description and metadata.

---

### `Test 8: Push (Gated Shelve Submit & Force Direct Submit)`

**Goal**:

- Verify gated submit queue shelving and force direct submit workflows.

**Description**:

- Tests standard `gfp push` (shelves change for Jenkins CI queue) followed by `gfp push -f` (direct atomic submission to depot).

**Test-Flow**:

1. Create, stage, and commit `test_push_<RUN_ID>.py`.
2. Execute `gfp push` (gated mode).
3. Verify changelist is shelved on Perforce server.
4. Execute `gfp push -f` (force submit).

**Check**:

- Gated push output confirms shelf creation and CI queue dispatch.
- Force push confirms `"Submitted change <CL>"`.

---

### `Test 9: Log (Changelist History)`

**Goal**:

- Verify changelist history listing.

**Description**:

- Queries changelist history using `gfp log -n 3`.

**Test-Flow**:

1. Execute `gfp log -n 3`.

**Check**:

- Output contains `"Change"` entries in reverse chronological order.

---

### `Test 10: Blame (Line Attribution)`

**Goal**:

- Verify file line attribution annotations.

**Description**:

- Submits file to depot and checks line attribution using `gfp blame`.

**Test-Flow**:

1. Create `test_blame_<RUN_ID>.txt`, submit to depot.
2. Execute `gfp blame test_blame_<RUN_ID>.txt`.

**Check**:

- Output contains author, changelist ID, and line text `"Blame Line 1"`.

---

### `Test 11: Stash Workflow (Save, List, Show, Pop)`

**Goal**:

- Verify complete shelf stash lifecycle.

**Description**:

- Stashes workspace modifications, lists active stashes, pops the stash, and verifies restored state.

**Test-Flow**:

1. Create and stage `test_stash_<RUN_ID>.txt`.
2. Execute `gfp stash save -m "WIP stash <RUN_ID>"`.
3. Execute `gfp stash list`.
4. Execute `gfp stash pop`.
5. Execute `gfp status`.

**Check**:

- `stash list` displays the saved shelf changelist.
- `stash pop` restores `test_stash_<RUN_ID>.txt` to the workspace.

---

### `Test 12: Branch (Stream Overview)`

**Goal**:

- Verify stream branch overview listing.

**Description**:

- Lists all Perforce streams in the depot.

**Test-Flow**:

1. Execute `gfp branch`.

**Check**:

- Output lists streams including `"//stream/main"`.

---

### `Test 13: Switch (Stream Switching)`

**Goal**:

- Verify switching client workspace stream.

**Description**:

- Switches client workspace from `//stream/main` to `//stream/dev` and back.

**Test-Flow**:

1. Execute `gfp switch //stream/dev`.
2. Check `gfp branch` output for active stream indicator `* //stream/dev`.
3. Execute `gfp switch //stream/main`.
4. Check `gfp branch` output for active stream indicator `* //stream/main`.

**Check**:

- Active stream switches cleanly between streams.

---

### `Test 14: Checkout and Clean`

**Goal**:

- Verify reverting modifications and cleaning untracked files.

**Description**:

- Reverts a dirty edit on a tracked file with `gfp checkout` and purges untracked scratch files with `gfp clean -f`.

**Test-Flow**:

1. Submit baseline file, open for edit, and add dirty modification.
2. Execute `gfp checkout <file>`.
3. Verify dirty modification is reverted.
4. Create untracked file `untracked_junk_<RUN_ID>.tmp`.
5. Execute `gfp clean -f`.

**Check**:

- Tracked file matches depot pristine content.
- Untracked file is removed from disk.

---

### `Test 15: Lifecycle Hooks (pre-commit & post-commit execution)`

**Goal**:

- Verify pre- and post-hook execution, environment variables, and abort enforcement.

**Description**:

- Installs `pre-commit` and `post-commit` hooks in `.gfp/hooks/`, tests execution, and verifies that a failing pre-hook aborts the commit.

**Test-Flow**:

1. Install passing `pre-commit` and `post-commit` scripts.
2. Commit a file and assert both hooks fired.
3. Install failing `pre-commit` hook (`exit 1`).
4. Attempt commit on a staged file.

**Check**:

- Both hooks execute during successful commit.
- Failing `pre-commit` hook aborts commit process and prevents changelist creation.

---

### `Test 16: Autocompletion Generation`

**Goal**:

- Verify shell completion generation for Bash.

**Description**:

- Executes `gfp completion bash` and verifies syntax.

**Test-Flow**:

1. Execute `gfp completion bash`.

**Check**:

- Output contains Bash completion directives (`complete -F ...`).

---

### `Test 17: Clone Workflow (Stream Clone to Directory)`

**Goal**:

- Verify stream cloning into a new directory with dedicated client workspace.

**Description**:

- Clones `//stream/main` into a subfolder, verifies `.p4config`, client options, and synced files.

**Test-Flow**:

1. Execute `gfp clone //stream/main -d test_clone_dir_<RUN_ID> -c test_clone_client_<RUN_ID>`.
2. Inspect target directory, `.p4config`, and client workspace options via `p4 client -o`.
3. Clean up client workspace and directory.

**Check**:

- `.p4config` contains `P4CLIENT=test_clone_client_<RUN_ID>`.
- Client spec has `allwrite` option enabled.

---

### `Test 18: Command Aliases`

**Goal**:

- Verify built-in shorthand aliases.

**Description**:

- Tests execution of `gfp st` and `gfp ci --help`.

**Test-Flow**:

1. Execute `gfp st`.
2. Execute `gfp ci --help`.

**Check**:

- `gfp st` executes status command.
- `gfp ci --help` displays commit help message.

---

### `Test 19: Full Changelist History (gfp log -a)`

**Goal**:

- Verify global changelist history across all streams.

**Description**:

- Executes `gfp log -a` to query depot-wide changes without stream boundaries.

**Test-Flow**:

1. Execute `gfp log -a`.

**Check**:

- Output lists changelists across all depot paths.

---

### `Test 20: Pending Changelist Status Breakdown (gfp status -c)`

**Goal**:

- Verify pending changelist audit with opened file lists.

**Description**:

- Creates a pending changelist and audits status with `gfp status -c`.

**Test-Flow**:

1. Create and stage `test_status_cl_<RUN_ID>.py`.
2. Commit to pending changelist.
3. Execute `gfp status -c`.

**Check**:

- Output lists pending changelists and displays opened files under their respective changelist headers.

---

### `Test 21: Selective File Commit (gfp commit <file1> -m "...")`

**Goal**:

- Verify selective staging and committing of specific files.

**Description**:

- Stages multiple files but commits only one into the pending changelist, leaving the other in default.

**Test-Flow**:

1. Stage `file1` and `file2`.
2. Execute `gfp commit file1 -m "Selective commit <RUN_ID>"`.
3. Inspect files opened in the created changelist.

**Check**:

- `file1` is in the created changelist.
- `file2` is not included in the changelist.

---

### `Test 22: Restore Workflow (gfp restore --staged, --cl, and unopened files)`

**Goal**:

- Verify unstaging files, restoring unopened files, and purging pending changelists.

**Description**:

- Tests `gfp restore --staged` to unstage files, `gfp restore <file>` to restore unopened modifications, and `gfp restore --cl` to delete pending changelists.

**Test-Flow**:

1. Stage `test_restore_<RUN_ID>.txt` and run `gfp restore --staged`.
2. Verify file remains on disk but is no longer opened.
3. Create pending changelist and run `gfp restore --cl <CL>`.
4. Modify an unopened file on disk without `p4 edit` and run `gfp restore <unopened_file>`.

**Check**:

- File is unstaged without losing changes.
- Pending changelist is deleted from Perforce server.
- Unopened file is restored to baseline depot content.

---

### `Test 23: Diffing Locally Opened Files in Pending CL (gfp diff -c <CL>)`

**Goal**:

- Verify unified diff restricted to files in a specific pending changelist.

**Description**:

- Opens file into a pending changelist, modifies file, and runs `gfp diff -c <CL>`.

**Test-Flow**:

1. Create pending changelist containing `test_diff_cl_<RUN_ID>.txt`.
2. Modify local file.
3. Execute `gfp diff -c <CL>`.

**Check**:

- Diff output displays modifications for files in that specific changelist.

---

### `Test 24: Rebase Squash (gfp rebase --squash <cl2> --onto <cl1>)`

**Goal**:

- Verify squashing one pending changelist onto another.

**Description**:

- Creates two pending changelists, squashes CL2 onto CL1, and asserts all files consolidate into CL1.

**Test-Flow**:

1. Create CL1 with `file1`.
2. Create CL2 with `file2`.
3. Execute `gfp rebase --squash <CL2> --onto <CL1>`.
4. Inspect opened files in CL1 and verify CL2 deletion.

**Check**:

- CL1 contains both `file1` and `file2`.
- CL2 is deleted.

---

### `Test 25: Pull Workflow (Sync & Auto-Resolve)`

**Goal**:

- Verify pulling depot revisions with preview, standard, and force modes.

**Description**:

- Tests `gfp pull -n` (dry-run preview), `gfp pull` (sync & auto-resolve), and `gfp pull -f` (force re-sync).

**Test-Flow**:

1. Execute `gfp pull -n`.
2. Execute `gfp pull`.
3. Execute `gfp pull -f`.

**Check**:

- `pull -n` previews revisions without altering files.
- `pull` and `pull -f` sync workspace files and auto-resolve non-conflicting edits.

---

### `Test 26: Resolve Workflow (Conflict Resolution with --ours, --theirs, -n)`

**Goal**:

- Verify conflict resolution options (`--ours`, `--theirs`, `-n`).

**Description**:

- Generates conflicting workspace and depot revisions and resolves using `gfp resolve --ours`.

**Test-Flow**:

1. Submit baseline file to depot.
2. Submit new revision from external context.
3. Edit local file against baseline and sync to trigger conflict.
4. Execute `gfp resolve --ours <file>`.

**Check**:

- Local workspace content is preserved.
- Conflict is marked as resolved.

---

### `Test 27: Reopen Workflow (Relocating Opened Files Between Changelists)`

**Goal**:

- Verify moving opened files between default and numbered pending changelists.

**Description**:

- Moves file from pending changelist to default and back.

**Test-Flow**:

1. Open files into a numbered pending changelist.
2. Execute `gfp reopen -c default file1`.
3. Verify `file1` is in default changelist.
4. Execute `gfp reopen -c <CL> file1`.
5. Verify `file1` is back in numbered changelist.

**Check**:

- File relocation succeeds in both directions.

---

### `Test 28: Branch Full Lifecycle (Create, Query Verbose, and Delete)`

**Goal**:

- Verify complete stream branch lifecycle.

**Description**:

- Creates a new development stream, inspects verbose stream details with `gfp branch -v`, and deletes the stream with `gfp branch -d`.

**Test-Flow**:

1. Execute `gfp branch //stream/test-stream-<RUN_ID> -t development -P //stream/main`.
2. Execute `gfp branch -v` and verify stream entry and parent mapping.
3. Execute `gfp branch -d //stream/test-stream-<RUN_ID>`.
4. Verify stream no longer appears in `gfp branch`.

**Check**:

- Stream is created, listed with parent, and cleanly deleted.

---

### `Test 29: Cross-Stream Auto-Stashing Invariant (gfp switch -s)`

**Goal**:

- Verify cross-stream auto-stashing and unshelving when switching streams.

**Description**:

- Modifies a file in `//stream/main`, executes `gfp switch -s //stream/dev`, verifies changes are stashed and restored in `//stream/dev`, then switches back.

**Test-Flow**:

1. Open and edit `README.md` in `//stream/main`.
2. Execute `gfp switch -s //stream/dev`.
3. Verify workspace stream is `//stream/dev` and `README.md` contains the modified content.
4. Execute `gfp switch -s //stream/main` and verify workspace stream is `//stream/main`.

**Check**:

- Uncommitted modifications follow the user across stream switches automatically.

---

### `Test 30: Diffstat Summary Output (gfp diff --stat)`

**Goal**:

- Verify diffstat summary histograms and line counts.

**Description**:

- Stages a file modification and runs `gfp diff --stat`.

**Test-Flow**:

1. Stage new file with content.
2. Execute `gfp diff --stat`.

**Check**:

- Output contains modified file histogram, insertion count, and summary line (`"1 file changed, 1 insertion(+)"`).

---

### `Test 31: Clean Dry-Run vs Force (-n vs -f -d)`

**Goal**:

- Verify dry-run safety and directory removal in `gfp clean`.

**Description**:

- Creates untracked directory and file, verifies `gfp clean -n -d` preserves them, and `gfp clean -f -d` deletes them.

**Test-Flow**:

1. Create untracked directory `test_junk_dir_<RUN_ID>` with files.
2. Execute `gfp clean -n -d` (dry-run).
3. Verify directory and files still exist.
4. Execute `gfp clean -f -d` (force clean).

**Check**:

- Dry-run does not delete any files.
- Force clean removes untracked directories and files.

---

### `Test 32: Commit with Auto-Reconcile (gfp commit -a -m "...")`

**Goal**:

- Verify automatic file reconciliation during commit without prior `gfp add`.

**Description**:

- Writes new content directly to working tree and runs `gfp commit -a -m "..."`.

**Test-Flow**:

1. Create new file `test_auto_<RUN_ID>.py` without calling `gfp add`.
2. Execute `gfp commit -a -m "Auto reconcile commit <RUN_ID>"`.
3. Verify pending changelist contains the newly created file.

**Check**:

- `gfp commit -a` automatically stages and sweeps the new file into the created changelist.

---

### `Test 33: Stash Drop and Show (gfp stash drop & gfp stash show)`

**Goal**:

- Verify inspecting and dropping specific stashes.

**Description**:

- Saves a stash, inspects its diff with `gfp stash show`, and purges it with `gfp stash drop`.

**Test-Flow**:

1. Stage modification and run `gfp stash save -m "Stash to drop <RUN_ID>"`.
2. Execute `gfp stash show -c <CL>`.
3. Execute `gfp stash drop -c <CL>`.
4. Verify changelist and shelf are deleted from Perforce server.

**Check**:

- `stash show` displays shelved unified diff.
- `stash drop` purges shelf and deletes pending changelist.

---

### `Test 34: Perforce Special Path Escaping (@, #, %, *)`

**Goal**:

- Verify end-to-end handling of files with special characters (`@`, `#`, `%`, `*`).

**Description**:

- Stages, diffs, and commits a file with special characters in its name (`test_%percent_#hash_@at_<RUN_ID>.txt`).

**Test-Flow**:

1. Create file `test_%percent_#hash_@at_<RUN_ID>.txt`.
2. Execute `gfp add`.
3. Execute `gfp status`.
4. Execute `gfp diff`.
5. Execute `gfp commit -m "Commit special path <RUN_ID>"`.

**Check**:

- All operations succeed without Perforce revision/wildcard syntax errors.

---

### `Test 35: Declarative JSON Plugins (.gfp/plugins.json)`

**Goal**:

- Verify execution of custom commands defined in `.gfp/plugins.json`.

**Description**:

- Creates `.gfp/plugins.json` mapping `server-info` to `p4 info` and executes `gfp server-info`.

**Test-Flow**:

1. Create `.gfp/plugins.json` with custom command `"server-info"`.
2. Execute `gfp server-info`.

**Check**:

- Custom plugin executes successfully and outputs Perforce server information.

---

### `Test 36: Workspace Resolution from Deep Subdirectory`

**Goal**:

- Verify workspace root resolution when executing `gfp` from deeply nested subdirectories.

**Description**:

- Creates deeply nested directory `deep/nested/sub/dir` and runs `gfp status` from inside it.

**Test-Flow**:

1. Create nested directory `deep/nested/sub/dir`.
2. `cd` into nested directory.
3. Execute `gfp status`.

**Check**:

- Command succeeds and detects workspace root properly without errors.
