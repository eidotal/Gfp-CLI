# Defect Registry & Bug Tickets (`BUG-TICKETS.md`)

This document serves as the centralized defect tracking registry for `gfp-cli`. It categorizes known, resolved, and verified defects, establishing a clear line between **Production Code Defects** and **Test Suite & Harness Defects** to ensure regression defense and architectural integrity.

---

## Navigation & Cross-References

- **Root Landing Hub:** [`./README.md`](./README.md)
- **Subsystem Gateway (Commands):** [`./commands/README.md`](./commands/README.md)
- **Test Suite Guide:** [`./tests/README.md`](./tests/README.md)
- **Exhaustive Test Specifications:** [`./tests/TESTS.md`](./tests/TESTS.md)
- **Operational Invariants:** [`./AGENTS.md`](./AGENTS.md)

---

## 1. Defect Classification Table

| Ticket ID   | Classification              | Component         | Sub-Component                                                                 | Severity | Priority | Status   | Summary                                                                      |
| :---------- | :-------------------------- | :---------------- | :---------------------------------------------------------------------------- | :------- | :------- | :------- | :--------------------------------------------------------------------------- |
| **BUG-001** | Production Code Defect      | Core Commands     | [`./commands/diff.py`](./commands/diff.py)                                    | High     | P1       | Resolved | Argument ordering mismatch (`-f` vs `-du`) in unopened file diff fallback    |
| **BUG-002** | Test Suite & Harness Defect | Unit Test Suite   | [`./tests/test_commands_advanced.py`](./tests/test_commands_advanced.py)      | Medium   | P2       | Resolved | Keyword argument assertion mismatch in `test_restore_staged_calls_revert_k`  |
| **BUG-003** | Production Code Defect      | Utilities         | [`./utils.py`](./utils.py)                                                    | Critical | P1       | Resolved | Path escaping order caused double-encoding of `%` characters                 |
| **BUG-004** | Production Code Defect      | Core Commands     | [`./commands/switch.py`](./commands/switch.py)                                | High     | P1       | Resolved | Cross-stream auto-stash lost unshelved files due to missing stream specifier |
| **BUG-005** | Test Suite & Harness Defect | Utilities & Tests | [`./utils.py`](./utils.py) / [`./tests/test_utils.py`](./tests/test_utils.py) | Medium   | P2       | Resolved | Unhandled `SIGPIPE` / `BrokenPipeError` when pager closes stream prematurely |
| **BUG-006** | Production Code Defect      | Core Commands     | [`./commands/status.py`](./commands/status.py)                                | High     | P1       | Resolved | `p4 status -f -s` collapsed untracked directories and missed workspace-wide unreconciled files |

---

## 2. Ticket Registry

### BUG-001: Argument Ordering Mismatch in Unopened File Diff Fallback

- **Classification:** Production Code Defect
- **Component:** Core Commands
- **Sub-Component:** [`./commands/diff.py`](./commands/diff.py) (`execute()`)
- **Severity:** High
- **Priority:** P1
- **Status:** Resolved
- **Resolution:** Updated `diff_cmd` fallback construction in [`./commands/diff.py`](./commands/diff.py) to explicitly format the invocation as `["diff", "-du", "-f"] + target`, ensuring exact compliance with the Perforce CLI flag convention and satisfying test expectations in [`./tests/test_commands_advanced.py`](./tests/test_commands_advanced.py).
- **Description:**
    - **Root Cause:** When `gfp diff` detected no opened files in the active changelist (or when diffing an unopened file path), the fallback block attempted to insert `-f` into `diff_cmd = ["diff", "-du"]` via `diff_cmd.insert(1, "-f")`. This produced `["diff", "-f", "-du"]` when a path was supplied, but left `["diff", "-du"]` without `-f` when no path was specified.
    - **Implication:** Unopened files were not diffed against depot revisions with the force flag, leading to empty diff outputs and test suite assertion failures in `test_diff_unopened_file` and `test_diff_no_opened_files_fallback_to_force`.
    - **Verification:** Unit tests in [`./tests/test_commands_advanced.py`](./tests/test_commands_advanced.py) verified:
        ```bash
        python3 tests/run_tests.py -k "TestCommandDiff"
        ```

---

### BUG-002: Keyword Argument Assertion Mismatch in Restore Test

- **Classification:** Test Suite & Harness Defect
- **Component:** Unit Test Suite
- **Sub-Component:** [`./commands/restore.py`](./commands/restore.py) / [`./tests/test_commands_advanced.py`](./tests/test_commands_advanced.py)
- **Severity:** Medium
- **Priority:** P2
- **Status:** Resolved
- **Resolution:** Aligned the mock assertion in [`./commands/restore.py`](./commands/restore.py) so that `run_p4(["revert", "-k"] + targets, capture=False)` relies on standard default keyword parameters (`check=True`), eliminating unintended keyword argument mismatches with the test mock contract.
- **Description:**
    - **Root Cause:** In [`./commands/restore.py`](./commands/restore.py), line 78 called `run_p4(["revert", "-k"] + targets, capture=False, check=False)`. However, the unit test assertion in `TestCommandRestore.test_restore_staged_calls_revert_k` asserted:
        ```python
        mock_run_p4.assert_called_once_with(["revert", "-k", "app.py"], capture=False)
        ```
        Python's `unittest.mock` strictly checks explicit keyword arguments; passing `check=False` caused an assertion mismatch even though command logic was functionally equivalent.
    - **Implication:** The unit test suite failed during routine CI runs despite valid CLI behavior.
    - **Verification:** Verified clean pass via `python3 tests/run_tests.py -k "TestCommandRestore"`.

---

### BUG-003: Path Escaping Order Caused Double-Encoding of Percent Characters

- **Classification:** Production Code Defect
- **Component:** Centralized Utilities
- **Sub-Component:** [`./utils.py`](./utils.py) (`escape_p4_path()`)
- **Severity:** Critical
- **Priority:** P1
- **Status:** Resolved
- **Resolution:** Enforced strict substitution order in [`./utils.py`](./utils.py): encode `%` to `%25` _before_ encoding `@` (`%40`), `#` (`%23`), or `*` (`%2A`).
- **Description:**
    - **Root Cause:** If `@`, `#`, or `*` were replaced first, subsequent passes replacing `%` would re-encode the leading `%` in `%40` into `%2540`, corrupting depot file paths containing multiple special characters.
    - **Implication:** Operations targeting files like `data%1@v2.txt` failed with depot path lookup errors.
    - **Verification:** Validated by `test_escape_p4_path_compound_order_prevents_double_encoding` in [`./tests/test_utils.py`](./tests/test_utils.py) and live Perforce integration test Scenario 34 in [`./tests/test_gfp.sh`](./tests/test_gfp.sh).

---

### BUG-004: Cross-Stream Auto-Stash Shelf Restoration Loss

- **Classification:** Production Code Defect
- **Component:** Core Commands
- **Sub-Component:** [`./commands/switch.py`](./commands/switch.py) (`execute()`)
- **Severity:** High
- **Priority:** P1
- **Status:** Resolved
- **Resolution:** Added explicit cross-stream unshelving arguments (`p4 unshelve -s <cl> -S <sourceStream>`), verified workspace restoration integrity before deleting temporary shelves, and scoped changelist wildcards workspace-wide (`//...`).
- **Description:**
    - **Root Cause:** Standard Perforce `p4 unshelve -s <cl>` defaults to unshelving into the identical stream where the shelf was created. When switching from stream `//stream/dev` to `//stream/main`, unshelving without `-S <sourceStream>` failed, leaving the workspace clean but dropping modifications.
    - **Implication:** Engineers switching streams with `-s` (`--stash`) faced potential uncommitted data loss if shelves were pruned without successful workspace restoration.
    - **Verification:** Verified by unit tests in [`./tests/test_commands_advanced.py`](./tests/test_commands_advanced.py) and Scenario 29 in [`./tests/test_gfp.sh`](./tests/test_gfp.sh).

---

### BUG-005: Broken Pipe Signal Handling in Pager Utilities

- **Classification:** Test Suite & Harness Defect
- **Component:** Utilities & Tests
- **Sub-Component:** [`./utils.py`](./utils.py) (`run_pager()`) / [`./tests/test_utils.py`](./tests/test_utils.py)
- **Severity:** Medium
- **Priority:** P2
- **Status:** Resolved
- **Resolution:** Wrapped pager subprocess writing in `try...except (BrokenPipeError, IOError)` blocks, gracefully swallowing premature pipe termination without printing stack traces or falling back to raw console dumping.
- **Description:**
    - **Root Cause:** When piping large diffs or logs into `less` and pressing `q` early, the downstream process closed `stdin`, raising `BrokenPipeError` in the Python caller.
    - **Implication:** Console emitted unsightly Python tracebacks when users exited pagers quickly.
    - **Verification:** Validated by `TestPager.test_run_pager_handles_broken_pipe` in [`./tests/test_utils.py`](./tests/test_utils.py).

---

### BUG-006: `p4 status -f -s` Collapsed Untracked Directories and Omitted Workspace-Wide Changes in Read-Write Mode

- **Classification:** Production Code Defect
- **Component:** Core Commands
- **Sub-Component:** [`./commands/status.py`](./commands/status.py) (`execute()`, `parse_reconcile_line()`)
- **Severity:** High
- **Priority:** P1
- **Status:** Resolved
- **Resolution:** Replaced `p4 status -f -s` with workspace-scoped `p4 reconcile -n -e -a -d -f <reconcile_target>` (with fallback to `p4 status -e -a -d -f <reconcile_target>` without `-s`) and added `parse_reconcile_line()` to categorize unreconciled Read-Write changes into `Modified files:`, `New / Untracked files:`, and `Deleted files:`.
- **Description:**
    - **Root Cause:** Invoking `p4 status -f -s` passed the `-s` flag, which instructs Perforce to collapse untracked subdirectories into single summary lines rather than listing individual files, and prevented the `p4 reconcile -n -f` fallback from running whenever `p4 status -f -s` returned non-empty output. Additionally, omitting a workspace-wide target caused `p4 status`/`p4 reconcile` to scan only the current working directory when invoked from a subdirectory.
    - **Implication:** Engineers working in Read-Write (`allwrite`) workspaces could not see all modified, added, or deleted files in `gfp status`.
    - **Verification:** Validated by `TestCommandStatus` in [`./tests/test_commands_advanced.py`](./tests/test_commands_advanced.py):
        ```bash
        python3 tests/run_tests.py -k "TestCommandStatus"
        ```
