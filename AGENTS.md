# AGENTS.md: Developer & Agent Operational Invariants

## Navigation & Cross-References

- **Parent Landing Hub:** [`./README.md`](./README.md)
- **Subsystem Gateway (Commands):** [`./commands/README.md`](./commands/README.md)
- **Everyday Workflow Guide:** [`./README_WORKFLOW.md`](./README_WORKFLOW.md)
- **Docker Playground Runbook:** [`./docker/README.md`](./docker/README.md)
- **Test Suite Overview:** [`./tests/README.md`](./tests/README.md)
- **Exhaustive Test Specifications:** [`./tests/TESTS.md`](./tests/TESTS.md)
- **Defect Registry & Bug Tickets:** [`./BUG-TICKETS.md`](./BUG-TICKETS.md)

---

## 1. Project Overview

- **Description:** A modular, extensible Git-compatible CLI layer and command wrapper for Perforce Helix Core (`p4`) that translates Git workflows, mental models, and lifecycle hooks into native Perforce operations.
- **Target Architecture / Platform:** Linux / POSIX (Cross-platform Python 3 environment with Perforce CLI)
- **Primary Languages:** Python 3 (Compatible with Python >= 3.6.4 and Python 3.8+)
- **Primary Maintainers:** eidotal

---

## 2. Directory Structure

```text
├── LICENSE                   # Open-source Apache 2.0 License
├── Makefile                  # Root orchestration: linting, formatting, staged test runners
├── pyproject.toml            # PEP 517/621 packaging metadata, ruff, mypy & pytest configs
├── README.md                 # Root landing hub, routing table, and architectural overview
├── README_WORKFLOW.md        # Everyday Git-to-Perforce development workflows and mental models
├── BUG-TICKETS.md            # Centralized defect registry and triage tickets
├── AGENTS.md                 # Strict operational invariants, task routing, and style guide
├── utils.py                  # Centralized Perforce, path escaping, and terminal pager utilities
├── gfp.py                    # Core CLI engine, workspace resolution, hook dispatcher, and plugin loader
├── commands/                 # Built-in command plugins subsystem gateway
│   ├── README.md             # Subsystem architecture, plugin contract, and command walkthrough
│   ├── add.py                # Stages/opens files for add, edit, delete, or reconcile
│   ├── blame.py              # Line attribution history viewer (p4 annotate)
│   ├── branch.py             # Stream/branch listing, creation, and deletion (p4 streams)
│   ├── checkout.py           # Discards local modifications (p4 revert)
│   ├── clean.py              # Removes untracked and unreconciled files from workspace (p4 clean)
│   ├── clone.py              # Clones depot/stream into a directory & sets up client workspace (p4 client & p4 sync)
│   ├── commit.py             # Creates or amends numbered pending changelists (p4 change -i)
│   ├── completion.py         # Shell completion script generator (bash, zsh, tcsh)
│   ├── diff.py               # Unified diff against depot head or changelist (p4 diff -du)
│   ├── log.py                # Changelist history viewer (p4 changes -m N -l)
│   ├── pull.py               # Syncs depot revisions and auto-resolves changes (p4 sync && p4 resolve -am)
│   ├── push.py               # Submits pending changelists to depot (p4 submit)
│   ├── rebase.py             # Rebase, squash, or interactively manipulate pending changelists
│   ├── reopen.py             # Moves opened files between changelists (p4 reopen)
│   ├── resolve.py            # Conflict resolution between workspace and depot revisions (p4 resolve)
│   ├── restore.py            # Restores working tree files or purges pending changelists (p4 revert / p4 change -d)
│   ├── show.py               # Changelist details and unified diff viewer (p4 describe -du)
│   ├── stash.py              # Shelves and unshelves pending changelists (p4 shelve / p4 unshelve)
│   ├── status.py             # Workspace status audit for opened and untracked files
│   └── switch.py             # Switches client workspace stream (p4 switch)
├── completions/              # Autocompletion definitions
│   ├── _gfp                  # Zsh completion definition
│   ├── gfp.bash              # Bash completion script
│   └── gfp.tcsh              # TCSH completion definition
├── man/                      # UNIX manual pages (troff/groff)
│   └── man1/
│       ├── gfp.1             # Main CLI manual page
│       ├── gfp-commit.1      # Commit command manual page
│       ├── gfp-push.1        # Push and gated submit queue manual page
│       └── gfp-switch.1      # Stream switching and auto-stash manual page
├── docker/                   # Self-contained Perforce testing playground
│   ├── Dockerfile.jenkins    # Jenkins Controller container with p4 CLI & plugins
│   ├── Dockerfile.p4client   # Client container image with P4 CLI, P4V, and noVNC
│   ├── Dockerfile.p4d        # Perforce Helix Core server container image
│   ├── Makefile              # Playground lifecycle orchestration and test runner
│   ├── README.md             # Subsystem runbook and container orchestration guide
│   ├── docker-compose.yml    # Multi-container network and volume configuration
│   ├── jenkins_config/       # Jenkins Configuration as Code (JCasC) definition
│   │   ├── Jenkinsfile       # Declarative pipeline script for gated submit-queue validation
│   │   └── jenkins.yaml      # Pre-seeded submit-queue pipeline job specification
│   ├── p4client-entrypoint.sh# Client workspace provisioning and VNC initialization
│   └── p4d-entrypoint.sh     # Server bootstrap with sample stream and classic depots
├── tests/                    # Python unit & regression test suite (Python >= 3.6.4)
│   ├── README.md             # Subsystem gateway and test strategy guide
│   ├── TESTS.md              # Test-by-test specifications (Goal, Description, Flow, Check)
│   ├── run_tests.py          # Standalone unit test runner with filtering
│   ├── test_gfp.sh           # End-to-end automated integration test suite
│   ├── test_utils.py         # Unit tests for utils.py
│   ├── test_gfp_core.py      # Unit tests for gfp.py engine & hooks
│   ├── test_commands_basic.py# Unit tests for basic command modules
│   └── test_commands_advanced.py # Unit tests for advanced command modules
├── .gfp/                     # (Optional/Runtime) Workspace-level hooks, commands, and plugins.json
└── ~/.gfp/                   # (Optional/Runtime) User-global hooks, commands, and plugins.json
```

---

## 3. Task Routing Table

| Task / Intent                      | Entry Points & Target Files                                                                                        | Verification Suite                      |
| :--------------------------------- | :----------------------------------------------------------------------------------------------------------------- | :-------------------------------------- |
| **Core Engine & Hook Dispatch**    | [`./gfp.py`](./gfp.py)                                                                                             | `python3 gfp.py --help`                 |
| **Centralized Utilities (DRY)**    | [`./utils.py`](./utils.py)                                                                                         | `python3 tests/run_tests.py -k "utils"` |
| **Task Runner Automation**         | [`./Makefile`](./Makefile)                                                                                         | `make help`                             |
| **Static Analysis & Tooling**      | [`./pyproject.toml`](./pyproject.toml), [`./Makefile`](./Makefile)                                                 | `make lint`                             |
| **Unit & Regression Test Suite**   | [`./tests/run_tests.py`](./tests/run_tests.py), [`./tests/`](./tests/)                                             | `make test-unit` or `python3 tests/run_tests.py` |
| **Test Catalog & Specifications**  | [`./tests/TESTS.md`](./tests/TESTS.md), [`./tests/README.md`](./tests/README.md)                                   | Document syntax audit                   |
| **Defect Triage & Registry**       | [`./BUG-TICKETS.md`](./BUG-TICKETS.md)                                                                             | Defect audit / regression run           |
| **Built-in Command Plugins**       | [`./commands/`](./commands/), [`./commands/README.md`](./commands/README.md)                                       | `python3 gfp.py <command> --help`       |
| **Everyday Development Workflows** | [`./README_WORKFLOW.md`](./README_WORKFLOW.md)                                                                     | Documentation audit                     |
| **New Subcommand Creation**        | `./commands/<new_cmd>.py`                                                                                          | `python3 gfp.py <new_cmd> [args]`       |
| **External Tool Mappings**         | `plugins.json`, `.gfp/plugins.json`                                                                                | `python3 gfp.py <tool_subcommand>`      |
| **Lifecycle Hook Automation**      | `.gfp/hooks/`, `~/.gfp/hooks/`                                                                                     | Pre/post execution trigger testing      |
| **Shell Autocompletions**          | [`./completions/`](./completions/), [`./commands/completion.py`](./commands/completion.py)                         | `gfp completion <bash\|zsh\|tcsh>`      |
| **UNIX Manual Pages**              | [`./man/man1/*.1`](./man/man1/gfp.1)                                                                               | `man -l man/man1/gfp.1`                 |
| **Docker Playground & E2E Test**   | [`./docker/`](./docker/), [`./docker/README.md`](./docker/README.md), [`./tests/test_gfp.sh`](./tests/test_gfp.sh) | `make test-e2e` or `make -C docker test`|
| **Root Landing Hub**               | [`./README.md`](./README.md), [`./LICENSE`](./LICENSE)                                                             | Document syntax & markdown audits       |

---

---

## 4. Tools & Commands

### Prerequisites

- **Compilers & Interpreters:** `python` >= 3.6.4 (Tested with Python 3.6.4 up to Python 3.14+)
- **Static Analysis & Linters:** `ruff`, `mypy`, `flake8`, `black`
- **Test Frameworks:** Python standard library `unittest`, `pytest`
- **Build Systems:** GNU Make, Standard Python runtime, Perforce CLI client (`p4` available in `$PATH`)
- **Container Testing:** Docker, Docker Compose, `make`

### Execution Commands

- **Build / Compile Syntax Check:**

```bash
make check-syntax
# or directly:
python3 -m py_compile gfp.py commands/*.py
```

- **Run CLI Help Verification:**

```bash
python3 gfp.py --help
# or Makefile help:
make help
```

- **Run Single CLI Command (Local Workspace):**

```bash
python3 gfp.py status
```

- **Run Python Unit Test Suite (Zero Perforce Dependencies):**

```bash
make test-unit
# or directly:
python3 tests/run_tests.py
# or with pattern filter: python3 tests/run_tests.py -k "utils|commit"
# or with verbosity: python3 tests/run_tests.py -v
# or via pytest: pytest
```

- **Run Full End-to-End Test Suite (Docker Playground):**

```bash
make test-e2e
# or directly in docker directory:
make -C docker test
# or unit tests only: make -C docker test ARGS="--unit"
# or filtered E2E: make -C docker test ARGS="-k 'stash|switch'"
# or inside docker client container: gfp-test
# or: bash /opt/gfp-cli/tests/test_gfp.sh
```

- **Run All Test Stages Sequentially (Unit -> E2E):**

```bash
make test-all
```

- **Run Static Analysis & Linters:**

```bash
make lint
# or individually:
make lint-ruff
make lint-mypy
```

- **Format & Format Check:**

```bash
make format
# or verify formatting:
make format-check
```

- **Clean Artifacts & Caches:**

```bash
make clean
# or deep clean (caches, pyc, bytecode):
make clean-all
```

---

## 5. Strict Agent Invariants & Rules

- **No Unsolicited Refactoring:** Only modify code directly relevant to the user request.
- **Python 3.6.4 Compatibility Invariant:** Maintain compatibility with Python 3.6.4+ using `sys.version_info >= (3, 7)` conditional branches for `TEXT_MODE` (`text=True` vs `universal_newlines=True`) and `argparse.add_subparsers` (`required=True` vs setting `.required = True` on the subparsers object). Avoid Python 3.7+ exclusive features such as `capture_output=True` in `subprocess.run` or `dataclasses`.
- **Preserve Plugin Interface Contracts:** All Python command plugins must export `COMMAND_NAME`, `HELP`, and `execute(args, run_p4, run_cmd=None, to_p4_path=None, **kwargs)`, with optional `setup_parser(parser)`.
- **Zero-Touch Core for New Commands:** Add new subcommands as standalone plugins inside `commands/` or `.gfp/commands/` rather than modifying `gfp.py` unless altering the core discovery or hook engine.
- **Workspace Resolution Order:** Workspace root is resolved in order: `.gfp` marker in parent tree -> `Client root:` from `p4 info` -> current working directory (`cwd`).
- **Hook Lifecycle Integrity:** Pre-hooks (`pre-<cmd>`) must abort execution on non-zero exit codes before invoking commands; post-hooks (`post-<cmd>`) run only upon successful command completion. Hook scripts inherit `GFP_COMMAND`, `GFP_HOOK_STAGE`, `GFP_WORKSPACE_ROOT`, and `GFP_ARGS`.
- **Preserve Interfaces:** Do not change public API signatures or function contracts (`run_p4`, `run_cmd`, `find_workspace_root`, `to_p4_path`) without explicit instruction.
- **No Auto-Generated File Edits:** Do not edit generated cache files or `.pyc` files directly; modify source Python files.
- **Deterministic Code:** Use `pathlib.Path` for cross-platform path resolution and avoid hardcoded environment assumptions.
- **Centralized Utilities & DRY:** Common Perforce helpers (`get_active_client`, `get_user`, `get_p4port`, `get_active_stream`, `resolve_stream_path`, `escape_p4_path`, `to_p4_path`, `run_pager`) reside in `utils.py` and are injected into plugins via `**kwargs` or direct import.
- **Terminal Paging Invariant:** Output from commands emitting large bodies (`diff`, `log`, `show`, `blame`) must route through `utils.run_pager()`. Pager execution checks `sys.stdout.isatty()` and catches early-exit signals (`BrokenPipeError`, `KeyboardInterrupt`) without falling back to `print()`.
- **Cross-Stream Auto-Stashing Invariant:** Stream switches using auto-stash (`gfp switch -s`) must scope wildcards workspace-wide (`//...`), employ cross-stream unshelving (`p4 unshelve -s <cl> -S <fromStream>`), and verify successful workspace restoration before deleting shelves.

---

## 6. Code Methodology & Style

- **Indentation:** 4 spaces (no tabs).
- **Naming Conventions:**
    - Variables & Functions: `snake_case`
    - Types, Classes & Structs: `PascalCase`
    - Constants & Macros: `ALL_CAPS_WITH_UNDERSCORES`

- **Error Handling:** Use explicit return codes with `sys.exit(...)` or `raise SystemExit(...)` and log error diagnostics to `sys.stderr`. Avoid uncaught exceptions escaping to the CLI user.
- **Comments & Docs:** Document invariants, Perforce mapping nuances, and non-obvious subprocess constraints. Avoid redundant self-descriptive comments.

---

## 7. Keywords & Domain Glossary

- **Changelist (CL):** Perforce's unit of atomic change, equivalent to a Git commit before and after submission (`p4 change`, `p4 submit`).
- **Opened / Reconciled:** Files checked out for edit, marked for add, or marked for delete in the Perforce client workspace (`p4 opened`, `p4 reconcile`).
- **Shelve / Unshelve:** Perforce equivalent of `git stash` where pending changelist files are temporarily stored on the Perforce server (`p4 shelve` / `p4 unshelve`).
- **Revert:** Discard local modifications and restore files to depot head state (`p4 revert`), equivalent to `git checkout <file>` or `git restore <file>`.
- **Sync:** Updating local workspace files to match the depot revision (`p4 sync`), part of `gfp pull`.
- **Stream:** Branching and release management mechanism in Perforce Helix Core (`p4 stream`, `p4 streams`, `p4 switch`), mapped to `gfp branch` and `gfp switch`.
- **Gated Submit Queue:** Automated pre-commit CI validation pipeline in Jenkins that unshelves proposed changelists (`p4 unshelve`), runs syntax/linter checks, and submits atomically to mainline (`p4 submit -e`) via `jenkins_bot`.
- **Reopen:** Relocating opened files between changelists (e.g. from default changelist to a numbered pending changelist) via `p4 reopen`.
- **Restore:** Reverting working tree files (`p4 revert`), unstaging files (`p4 revert -k`), or atomically purging pending changelists and their shelves (`p4 change -d`).
- **Resolve:** Conflict resolution between local workspace revisions and depot revisions (`p4 resolve -ay` for ours, `-at` for theirs).
- **Rebase / Squash:** Combining pending changelists into a target changelist by reopening files, merging changelist descriptions, and deleting source changelists.
- **Diffstat:** Formatted histogram and summary of added/deleted lines across modified files, modeled after `git diff --stat`.
- **Allwrite / Clobber Workspace Options:** Client workspace options configured during `gfp clone` (`allwrite clobber nocompress unlocked`) allowing Git-like local file modification without upfront checkout locking.
- **Lifecycle Hook:** Executable scripts located in `.gfp/hooks/` or `~/.gfp/hooks/` run automatically before (`pre-`) or after (`post-`) command execution.
- **Plugin Contract:** The standardized interface (`COMMAND_NAME`, `HELP`, `setup_parser`, `execute`) required for all Python modules in `commands/`.
