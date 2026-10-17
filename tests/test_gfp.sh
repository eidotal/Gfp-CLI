#!/usr/bin/env bash

# ==============================================================================
# gfp-cli Automated End-to-End & Unit Test Suite for Docker Playground
# (Repeatable, Idempotent, with Workspace Isolation & Hook Assertions)
# ==============================================================================

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0
RUN_ID="$(date +%s)_$RANDOM"
WS_DIR="${PWD}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CLI Arguments & Execution Flags
RUN_UNIT=true
RUN_E2E=true
FILTER=""
VERBOSE=false
LIST_ONLY=false

show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --all            Run both unit tests and all E2E integration tests (default)
  -u, --unit       Run only the Python unit & regression test suite (tests/)
  -e, --e2e        Run only the end-to-end integration tests with Perforce
  -k, --filter REGEX
                   Run only tests whose name matches the specified regular expression
  -l, --list       List all available test scenarios and exit
  -v, --verbose    Show command output for passed tests as well as failed tests
  -h, --help       Show this help message and exit

Examples:
  ./test_gfp.sh
  ./test_gfp.sh --unit
  ./test_gfp.sh -k "stash|switch"
  ./test_gfp.sh --e2e -v
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)
            RUN_UNIT=true
            RUN_E2E=true
            shift
            ;;
        -u|--unit)
            RUN_UNIT=true
            RUN_E2E=false
            shift
            ;;
        -e|--e2e)
            RUN_UNIT=false
            RUN_E2E=true
            shift
            ;;
        -k|--filter)
            FILTER="$2"
            shift 2
            ;;
        -l|--list)
            LIST_ONLY=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            ;;
    esac
done

# Save original caller environment to guarantee zero-leakage cleanup on exit
ORIG_P4PORT="${P4PORT-}"
ORIG_P4USER="${P4USER-}"
ORIG_P4CLIENT="${P4CLIENT-}"
ORIG_GFP_CMD="${GFP_CMD-}"
ORIG_GFP_PUSH_MODE="${GFP_PUSH_MODE-}"
ORIG_PAGER="${PAGER-}"

cleanup_env() {
    # Restore original environment or unset if they were not present originally
    if [ -n "${ORIG_P4PORT}" ]; then export P4PORT="${ORIG_P4PORT}"; else unset P4PORT; fi
    if [ -n "${ORIG_P4USER}" ]; then export P4USER="${ORIG_P4USER}"; else unset P4USER; fi
    if [ -n "${ORIG_P4CLIENT}" ]; then export P4CLIENT="${ORIG_P4CLIENT}"; else unset P4CLIENT; fi
    if [ -n "${ORIG_GFP_CMD}" ]; then export GFP_CMD="${ORIG_GFP_CMD}"; else unset GFP_CMD; fi
    if [ -n "${ORIG_GFP_PUSH_MODE}" ]; then export GFP_PUSH_MODE="${ORIG_GFP_PUSH_MODE}"; else unset GFP_PUSH_MODE; fi
    if [ -n "${ORIG_PAGER}" ]; then export PAGER="${ORIG_PAGER}"; else unset PAGER; fi
}

# Resolve gfp executable
if command -v gfp >/dev/null 2>&1; then
    GFP_BIN="gfp"
elif [ -f "${SCRIPT_DIR}/../gfp.py" ]; then
    GFP_BIN="python3 ${SCRIPT_DIR}/../gfp.py"
elif [ -f "/opt/gfp-cli/gfp.py" ]; then
    GFP_BIN="python3 /opt/gfp-cli/gfp.py"
elif [ -f "/home/devuser/gfp-cli/gfp.py" ]; then
    GFP_BIN="python3 /home/devuser/gfp-cli/gfp.py"
elif [ -f "../gfp.py" ]; then
    GFP_BIN="python3 ../gfp.py"
elif [ -f "gfp.py" ]; then
    GFP_BIN="python3 gfp.py"
else
    echo -e "${RED}Error: gfp executable or gfp.py not found.${NC}"
    exit 1
fi

P4PORT="${P4PORT:-p4server:1666}"
P4USER="${P4USER:-devuser}"
P4CLIENT="${P4CLIENT:-devuser_ws}"
export P4PORT P4USER P4CLIENT

# Run gfp in an isolated, explicitly scoped subshell environment
GFP_CMD="env P4PORT=${P4PORT} P4USER=${P4USER} P4CLIENT=${P4CLIENT} ${GFP_BIN}"

# ------------------------------------------------------------------------------
# Workspace Setup & Teardown Helpers
# ------------------------------------------------------------------------------
reset_workspace() {
    cd "${WS_DIR}" 2>/dev/null || true
    # Revert any open files
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert //... >/dev/null 2>&1 || true
    # Reset client back to //stream/main stream
    p4 -p "${P4PORT}" -u "${P4USER}" client -s -S //stream/main "${P4CLIENT}" >/dev/null 2>&1 || true
    # Clean untracked files
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" clean ... >/dev/null 2>&1 || true
    # Resync pristine files from depot
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" sync -f ... >/dev/null 2>&1 || true
    # Remove any test scratch artifacts
    rm -rf "${WS_DIR}"/test_* "${WS_DIR}"/untracked_* "${WS_DIR}"/.gfp/hooks/test_* "${WS_DIR}"/deep 2>/dev/null || true
    # Ensure .p4config exists in workspace
    if [ ! -f "${WS_DIR}/.p4config" ]; then
        cat <<EOF >"${WS_DIR}/.p4config"
P4PORT=${P4PORT}
P4USER=${P4USER}
P4CLIENT=${P4CLIENT}
EOF
    fi
}

cleanup_all() {
    reset_workspace
    cleanup_env
}

# Trap to guarantee cleanup of both workspace and environment variables on exit or abort
trap cleanup_all EXIT INT TERM

ALL_TEST_NAMES=()
register_test_name() {
    ALL_TEST_NAMES+=("$1")
}

run_test() {
    local test_name="$1"
    local test_fn="$2"

    register_test_name "${test_name}"

    if [ "${LIST_ONLY}" = true ]; then
        return 0
    fi

    if [ "${RUN_E2E}" = false ]; then
        return 0
    fi

    if [ -n "${FILTER}" ]; then
        if ! echo "${test_name}" | grep -Eqi "${FILTER}"; then
            SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
            return 0
        fi
    fi

    echo -e "${BLUE}[TEST]${NC} ${test_name}..."
    reset_workspace

    local test_output
    local exit_code=0
    test_output=$("${test_fn}" 2>&1) || exit_code=$?

    if [ "${exit_code}" -eq 0 ]; then
        echo -e "${GREEN}[PASS]${NC} ${test_name}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        if [ "${VERBOSE}" = true ] && [ -n "${test_output}" ]; then
            echo -e "${CYAN}--- Output ---${NC}\n${test_output}\n${CYAN}--------------${NC}"
        fi
    else
        echo -e "${RED}[FAIL]${NC} ${test_name}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        if [ -n "${test_output}" ]; then
            echo -e "${RED}--- Failure Diagnostic ---${NC}\n${test_output}\n${RED}--------------------------${NC}"
        fi
    fi
    echo ""
}

# ------------------------------------------------------------------------------
# Unit Test Suite Runner (tests/run_tests.py)
# ------------------------------------------------------------------------------
run_unit_tests() {
    if [ "${LIST_ONLY}" = true ]; then
        echo "  [Unit Suite] Python Unit & Regression Tests (tests/run_tests.py)"
        return 0
    fi

    if [ "${RUN_UNIT}" = false ]; then
        return 0
    fi

    local unit_runner=""
    if [ -f "${SCRIPT_DIR}/run_tests.py" ]; then
        unit_runner="${SCRIPT_DIR}/run_tests.py"
    elif [ -f "/opt/gfp-cli/tests/run_tests.py" ]; then
        unit_runner="/opt/gfp-cli/tests/run_tests.py"
    elif [ -f "${WS_DIR}/../tests/run_tests.py" ]; then
        unit_runner="${WS_DIR}/../tests/run_tests.py"
    elif [ -f "${WS_DIR}/tests/run_tests.py" ]; then
        unit_runner="${WS_DIR}/tests/run_tests.py"
    elif [ -f "tests/run_tests.py" ]; then
        unit_runner="tests/run_tests.py"
    fi

    if [ -z "${unit_runner}" ]; then
        echo -e "${YELLOW}[SKIP] tests/run_tests.py not found in search paths.${NC}\n"
        return 0
    fi

    echo -e "${BLUE}[SUITE]${NC} Running Python Unit & Regression Tests (${unit_runner})..."
    local unit_args=()
    if [ "${VERBOSE}" = true ]; then
        unit_args+=("-v")
    fi
    if [ -n "${FILTER}" ]; then
        unit_args+=("-k" "${FILTER}")
    fi

    if python3 "${unit_runner}" "${unit_args[@]}"; then
        echo -e "${GREEN}[PASS]${NC} Python Unit & Regression Test Suite\n"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}[FAIL]${NC} Python Unit & Regression Test Suite\n"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

# ------------------------------------------------------------------------------
# Test 1: CLI Engine and Help Output
# ------------------------------------------------------------------------------
test_cli_help() {
    local output
    if ! output=$(${GFP_CMD} --help 2>&1); then
        echo -e "Help command failed:\n${output}"
        return 1
    fi
    echo "${output}" | grep -q "Extensible Git-like CLI interface"
}

# ------------------------------------------------------------------------------
# Test 2: Status on Clean Workspace
# ------------------------------------------------------------------------------
test_status_clean() {
    local output
    if ! output=$(${GFP_CMD} status 2>&1); then
        echo -e "Status failed:\n${output}"
        return 1
    fi
    echo "${output}" | grep -qi "working tree clean\|no files currently opened"
}

# ------------------------------------------------------------------------------
# Test 3: Add and Status with Isolated Test Files
# ------------------------------------------------------------------------------
test_add_and_status() {
    local test_file="test_add_${RUN_ID}.py"
    echo "# Test module ${RUN_ID}" > "${test_file}"

    local add_output
    if ! add_output=$(${GFP_CMD} add "${test_file}" 2>&1); then
        echo -e "Add failed:\n${add_output}"
        return 1
    fi

    local status_output
    status_output=$(${GFP_CMD} status 2>&1)
    echo "${status_output}" | grep -q "${test_file}"
}

# ------------------------------------------------------------------------------
# Test 4: Unified Diff
# ------------------------------------------------------------------------------
test_diff() {
    local test_file="test_diff_${RUN_ID}.txt"
    echo "Line 1 baseline" > "${test_file}"
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" add "${test_file}" >/dev/null 2>&1
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" submit -d "Baseline for diff test" >/dev/null 2>&1

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" edit "${test_file}" >/dev/null 2>&1
    echo "Line 2 modified ${RUN_ID}" >> "${test_file}"

    local diff_output
    if ! diff_output=$(${GFP_CMD} diff "${test_file}" 2>&1); then
        echo -e "Diff command failed:\n${diff_output}"
        return 1
    fi
    if ! echo "${diff_output}" | grep -q "Line 2 modified ${RUN_ID}"; then
        echo -e "Diff output missing modified content:\n${diff_output}"
        return 1
    fi

    # Test diff with explicit --color flag
    local colored_diff
    if ! colored_diff=$(${GFP_CMD} diff --color "${test_file}" 2>&1); then
        echo -e "gfp diff --color failed:\n${colored_diff}"
        return 1
    fi
    if ! echo "${colored_diff}" | grep -q $'\033\[32m'; then
        echo -e "gfp diff --color missing ANSI green code:\n${colored_diff}"
        return 1
    fi

    # Test diff with explicit --no-color flag
    local nocolor_diff
    if ! nocolor_diff=$(${GFP_CMD} diff --no-color "${test_file}" 2>&1); then
        echo -e "gfp diff --no-color failed:\n${nocolor_diff}"
        return 1
    fi
    if echo "${nocolor_diff}" | grep -q $'\033\['; then
        echo -e "gfp diff --no-color contains ANSI escape codes:\n${nocolor_diff}"
        return 1
    fi

    # Test diff on unopened modified file (p4 diff -f)
    local unopened_file="test_diff_unopened_${RUN_ID}.txt"
    echo "Unopened baseline" > "${unopened_file}"
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" add "${unopened_file}" >/dev/null 2>&1
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" submit -d "Baseline for unopened diff" >/dev/null 2>&1

    # Modify locally without p4 edit
    echo "Unopened modified line ${RUN_ID}" >> "${unopened_file}"
    local unopened_diff
    if ! unopened_diff=$(${GFP_CMD} diff "${unopened_file}" 2>&1); then
        echo -e "gfp diff on unopened file failed:\n${unopened_diff}"
        return 1
    fi
    echo "${unopened_diff}" | grep -q "Unopened modified line ${RUN_ID}"
}

# ------------------------------------------------------------------------------
# Test 5: Commit (Create Pending Changelist)
# ------------------------------------------------------------------------------
test_commit() {
    local test_file="test_commit_${RUN_ID}.py"
    echo "print('Commit test ${RUN_ID}')" > "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1

    local commit_output
    if ! commit_output=$(${GFP_CMD} commit -m "Add commit test module ${RUN_ID}" 2>&1); then
        echo -e "Commit failed:\n${commit_output}"
        return 1
    fi
    echo "${commit_output}" | grep -Eqi "Created pending changelist|Change"
}

# ------------------------------------------------------------------------------
# Test 6: Commit Amend (Amend Description & Reopen)
# ------------------------------------------------------------------------------
test_commit_amend() {
    local test_file="test_amend_${RUN_ID}.py"
    echo "v1 = 1" > "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1
    ${GFP_CMD} commit -m "Initial description ${RUN_ID}" >/dev/null 2>&1

    echo "v2 = 2" >> "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1

    local amend_output
    if ! amend_output=$(${GFP_CMD} commit --amend -m "Amended description ${RUN_ID}" 2>&1); then
        echo -e "Commit amend failed:\n${amend_output}"
        return 1
    fi
    echo "${amend_output}" | grep -qi "Amended pending changelist"
}

# ------------------------------------------------------------------------------
# Test 7: Show Changelist Details
# ------------------------------------------------------------------------------
test_show() {
    local test_file="test_show_${RUN_ID}.py"
    echo "x = 42" > "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1
    ${GFP_CMD} commit -m "Show test CL ${RUN_ID}" >/dev/null 2>&1

    local show_output
    if ! show_output=$(${GFP_CMD} show 2>&1); then
        echo -e "Show failed:\n${show_output}"
        return 1
    fi
    echo "${show_output}" | grep -qi "Show test CL ${RUN_ID}"
}

# ------------------------------------------------------------------------------
# Test 8: Push (Gated Shelve Submit & Force Direct Submit)
# ------------------------------------------------------------------------------
test_push() {
    local test_file="test_push_${RUN_ID}.py"
    echo "push_val = True" > "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1
    ${GFP_CMD} commit -m "Push test commit ${RUN_ID}" >/dev/null 2>&1

    # 1. Test Gated Push (shelves change for Jenkins submit queue)
    local gated_output
    if ! gated_output=$(${GFP_CMD} push 2>&1); then
        echo -e "Gated push failed:\n${gated_output}"
        return 1
    fi
    if ! echo "${gated_output}" | grep -Eqi "Shelv|queued for CI"; then
        echo -e "Gated push did not shelve changelist"
        return 1
    fi

    # 2. Test Force Push (direct submit to depot bypassing CI queue)
    local force_output
    if ! force_output=$(${GFP_CMD} push -f 2>&1); then
        echo -e "Force push failed:\n${force_output}"
        return 1
    fi
    echo "${force_output}" | grep -Eqi "Submitted change|Change .* submitted"
}

# ------------------------------------------------------------------------------
# Test 9: Log (Changelist History)
# ------------------------------------------------------------------------------
test_log() {
    local log_output
    if ! log_output=$(${GFP_CMD} log -n 3 2>&1); then
        echo -e "Log failed:\n${log_output}"
        return 1
    fi
    echo "${log_output}" | grep -qi "Change"
}

# ------------------------------------------------------------------------------
# Test 10: Blame (Line Attribution)
# ------------------------------------------------------------------------------
test_blame() {
    local test_file="test_blame_${RUN_ID}.txt"
    echo "Blame Line 1" > "${test_file}"
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" add "${test_file}" >/dev/null 2>&1
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" submit -d "Blame baseline ${RUN_ID}" >/dev/null 2>&1

    local blame_output
    if ! blame_output=$(${GFP_CMD} blame "${test_file}" 2>&1); then
        echo -e "Blame failed:\n${blame_output}"
        return 1
    fi
    echo "${blame_output}" | grep -qi "Blame Line 1"
}

# ------------------------------------------------------------------------------
# Test 11: Stash Workflow (Save, List, Show, Pop)
# ------------------------------------------------------------------------------
test_stash_workflow() {
    local test_file="test_stash_${RUN_ID}.txt"
    echo "Stash content ${RUN_ID}" > "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1

    if ! ${GFP_CMD} stash save -m "WIP stash ${RUN_ID}" >/dev/null 2>&1; then
        echo -e "Stash save failed"
        return 1
    fi

    local stash_list
    stash_list=$(${GFP_CMD} stash list 2>&1)
    if ! echo "${stash_list}" | grep -qi "Change"; then
        echo -e "Stash list did not show stashed changelist:\n${stash_list}"
        return 1
    fi

    if ! ${GFP_CMD} stash pop >/dev/null 2>&1; then
        echo -e "Stash pop failed"
        return 1
    fi

    local status_out
    status_out=$(${GFP_CMD} status 2>&1)
    echo "${status_out}" | grep -q "${test_file}"
}

# ------------------------------------------------------------------------------
# Test 12: Branch (Stream Overview)
# ------------------------------------------------------------------------------
test_branch() {
    local branch_output
    if ! branch_output=$(${GFP_CMD} branch 2>&1); then
        echo -e "Branch command failed:\n${branch_output}"
        return 1
    fi
    echo "${branch_output}" | grep -q "//stream/main"
}

# ------------------------------------------------------------------------------
# Test 13: Switch (Stream Switching)
# ------------------------------------------------------------------------------
test_switch() {
    if ! ${GFP_CMD} switch //stream/dev >/dev/null 2>&1; then
        echo -e "Switch to //stream/dev failed"
        return 1
    fi
    local branch_dev
    branch_dev=$(${GFP_CMD} branch 2>&1)
    if ! echo "${branch_dev}" | grep -q "\* //stream/dev"; then
        echo -e "Active stream did not switch to //stream/dev:\n${branch_dev}"
        return 1
    fi

    if ! ${GFP_CMD} switch //stream/main >/dev/null 2>&1; then
        echo -e "Switch back to //stream/main failed"
        return 1
    fi
    local branch_main
    branch_main=$(${GFP_CMD} branch 2>&1)
    echo "${branch_main}" | grep -q "\* //stream/main"
}

# ------------------------------------------------------------------------------
# Test 14: Checkout and Clean
# ------------------------------------------------------------------------------
test_checkout_and_clean() {
    local test_file="test_checkout_${RUN_ID}.txt"
    echo "initial" > "${test_file}"
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" add "${test_file}" >/dev/null 2>&1
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" submit -d "Checkout baseline ${RUN_ID}" >/dev/null 2>&1

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" edit "${test_file}" >/dev/null 2>&1
    echo "dirty edit" >> "${test_file}"

    ${GFP_CMD} checkout "${test_file}" >/dev/null 2>&1
    if grep -q "dirty edit" "${test_file}"; then
        echo -e "Checkout failed to revert dirty edit"
        return 1
    fi

    touch "untracked_junk_${RUN_ID}.tmp"
    ${GFP_CMD} clean -f >/dev/null 2>&1
    if [ -f "untracked_junk_${RUN_ID}.tmp" ]; then
        echo -e "Clean failed to remove untracked file"
        return 1
    fi
    return 0
}

# ------------------------------------------------------------------------------
# Test 15: Lifecycle Hooks (pre-commit & post-commit execution)
# ------------------------------------------------------------------------------
test_lifecycle_hooks() {
    mkdir -p "${WS_DIR}/.gfp/hooks"
    local hook_marker="/tmp/gfp_hook_${RUN_ID}.log"
    rm -f "${hook_marker}"

    cat <<EOF > "${WS_DIR}/.gfp/hooks/pre-commit"
#!/usr/bin/env bash
echo "PRE_HOOK_FIRED" >> "${hook_marker}"
exit 0
EOF
    chmod +x "${WS_DIR}/.gfp/hooks/pre-commit"

    cat <<EOF > "${WS_DIR}/.gfp/hooks/post-commit"
#!/usr/bin/env bash
echo "POST_HOOK_FIRED" >> "${hook_marker}"
exit 0
EOF
    chmod +x "${WS_DIR}/.gfp/hooks/post-commit"

    local test_file="test_hook_${RUN_ID}.py"
    echo "hook_test = True" > "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1
    ${GFP_CMD} commit -m "Hook test ${RUN_ID}" >/dev/null 2>&1

    if [ ! -f "${hook_marker}" ] || ! grep -q "PRE_HOOK_FIRED" "${hook_marker}" || ! grep -q "POST_HOOK_FIRED" "${hook_marker}"; then
        echo -e "Lifecycle hooks did not execute properly"
        rm -rf "${WS_DIR}/.gfp/hooks/pre-commit" "${WS_DIR}/.gfp/hooks/post-commit" "${hook_marker}"
        return 1
    fi
    rm -f "${hook_marker}"

    cat <<EOF > "${WS_DIR}/.gfp/hooks/pre-commit"
#!/usr/bin/env bash
echo "Linter failed!" >&2
exit 1
EOF
    chmod +x "${WS_DIR}/.gfp/hooks/pre-commit"

    echo "another_change = True" >> "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1

    if ${GFP_CMD} commit -m "Should be rejected ${RUN_ID}" >/dev/null 2>&1; then
        echo -e "Expected commit to be aborted by pre-commit hook, but it succeeded!"
        rm -rf "${WS_DIR}/.gfp/hooks/pre-commit" "${WS_DIR}/.gfp/hooks/post-commit"
        return 1
    fi

    rm -rf "${WS_DIR}/.gfp/hooks/pre-commit" "${WS_DIR}/.gfp/hooks/post-commit"
    return 0
}

# ------------------------------------------------------------------------------
# Test 16: Autocompletion Generation
# ------------------------------------------------------------------------------
test_completion() {
    local comp_bash
    if ! comp_bash=$(${GFP_CMD} completion bash 2>&1); then
        echo -e "Completion bash failed:\n${comp_bash}"
        return 1
    fi
    echo "${comp_bash}" | grep -qi "complete"
}

# ------------------------------------------------------------------------------
# Test 17: Clone Workflow (Stream Clone to Directory)
# ------------------------------------------------------------------------------
test_clone() {
    local clone_target_dir="${WS_DIR}/test_clone_dir_${RUN_ID}"
    local clone_client="test_clone_client_${RUN_ID}"
    rm -rf "${clone_target_dir}"

    local clone_output
    if ! clone_output=$(${GFP_CMD} clone //stream/main -d "${clone_target_dir}" -c "${clone_client}" 2>&1); then
        echo -e "Clone command failed:\n${clone_output}"
        rm -rf "${clone_target_dir}"
        return 1
    fi

    if [ ! -d "${clone_target_dir}" ] || [ ! -f "${clone_target_dir}/.p4config" ]; then
        echo -e "Clone target directory or .p4config was not created"
        rm -rf "${clone_target_dir}"
        return 1
    fi

    if ! grep -q "P4CLIENT=${clone_client}" "${clone_target_dir}/.p4config"; then
        echo -e ".p4config does not contain expected client name"
        rm -rf "${clone_target_dir}"
        return 1
    fi

    local client_spec
    client_spec=$(p4 -p "${P4PORT}" -u "${P4USER}" client -o "${clone_client}" 2>/dev/null || true)
    if ! echo "${client_spec}" | grep -qi "allwrite"; then
        echo -e "Clone client spec does not have allwrite option enabled"
        rm -rf "${clone_target_dir}"
        p4 -p "${P4PORT}" -u "${P4USER}" client -d "${clone_client}" >/dev/null 2>&1 || true
        return 1
    fi

    rm -rf "${clone_target_dir}"
    p4 -p "${P4PORT}" -u "${P4USER}" client -d "${clone_client}" >/dev/null 2>&1 || true
    return 0
}

# ------------------------------------------------------------------------------
# Test 18: Command Aliases
# ------------------------------------------------------------------------------
test_aliases() {
    local st_out
    if ! st_out=$(${GFP_CMD} st 2>&1); then
        echo -e "gfp st alias failed:\n${st_out}"
        return 1
    fi
    echo "${st_out}" | grep -qi "On Perforce workspace" || return 1

    local ci_help
    if ! ci_help=$(${GFP_CMD} ci --help 2>&1); then
        echo -e "gfp ci --help failed:\n${ci_help}"
        return 1
    fi
    echo "${ci_help}" | grep -qi "commit" || return 1
    return 0
}

# ------------------------------------------------------------------------------
# Test 19: Full Changelist History (gfp log -a)
# ------------------------------------------------------------------------------
test_log_all() {
    local log_out
    if ! log_out=$(${GFP_CMD} log -a 2>&1); then
        echo -e "gfp log -a failed:\n${log_out}"
        return 1
    fi
    echo "${log_out}" | grep -qi "Change" || return 1
    return 0
}

# ------------------------------------------------------------------------------
# Test 20: Pending Changelist Status Breakdown (gfp status -c)
# ------------------------------------------------------------------------------
test_status_pending_cl() {
    local test_file="test_status_cl_${RUN_ID}.py"
    echo "# Test status cl" > "${test_file}"
    ${GFP_CMD} add "${test_file}" >/dev/null 2>&1

    local commit_out
    commit_out=$(${GFP_CMD} commit -m "Test status pending CL ${RUN_ID}" 2>&1)
    local cl_id
    cl_id=$(echo "${commit_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    local st_cl_out
    if ! st_cl_out=$(${GFP_CMD} status -c 2>&1); then
        echo -e "gfp status -c failed:\n${st_cl_out}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl_id}" //... >/dev/null 2>&1 || true
        p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl_id}" >/dev/null 2>&1 || true
        return 1
    fi
    echo "${st_cl_out}" | grep -qi "Pending changelists for workspace" || return 1
    echo "${st_cl_out}" | grep -q "${cl_id}" || return 1

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl_id}" //... >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl_id}" >/dev/null 2>&1 || true
    return 0
}

# ------------------------------------------------------------------------------
# Test 21: Selective File Commit (gfp commit <file1> -m "...")
# ------------------------------------------------------------------------------
test_selective_commit() {
    local file1="test_select_1_${RUN_ID}.txt"
    local file2="test_select_2_${RUN_ID}.txt"
    echo "content 1" > "${file1}"
    echo "content 2" > "${file2}"

    ${GFP_CMD} add "${file1}" "${file2}" >/dev/null 2>&1

    local commit_out
    if ! commit_out=$(${GFP_CMD} commit "${file1}" -m "Selective commit ${RUN_ID}" 2>&1); then
        echo -e "Selective commit failed:\n${commit_out}"
        return 1
    fi
    local cl_id
    cl_id=$(echo "${commit_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    local cl_opened
    cl_opened=$(p4 -p "${P4PORT}" -u "${P4USER}" opened -c "${cl_id}" 2>/dev/null || true)
    if ! echo "${cl_opened}" | grep -q "${file1}"; then
        echo -e "file1 not found in changelist ${cl_id}"
        return 1
    fi
    if echo "${cl_opened}" | grep -q "${file2}"; then
        echo -e "file2 was unexpectedly swept into changelist ${cl_id}"
        return 1
    fi

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl_id}" //... >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl_id}" >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert "${file2}" >/dev/null 2>&1 || true
    rm -f "${file1}" "${file2}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 22: Restore Workflow (gfp restore --staged and --cl)
# ------------------------------------------------------------------------------
test_restore() {
    local rfile="test_restore_${RUN_ID}.txt"
    echo "line 1" > "${rfile}"
    ${GFP_CMD} add "${rfile}" >/dev/null 2>&1

    if ! ${GFP_CMD} restore --staged "${rfile}" >/dev/null 2>&1; then
        echo -e "gfp restore --staged failed"
        return 1
    fi
    if [ ! -f "${rfile}" ]; then
        echo -e "restore --staged deleted local file"
        return 1
    fi
    local opened_check
    opened_check=$(p4 -p "${P4PORT}" -u "${P4USER}" opened "${rfile}" 2>/dev/null || true)
    if [ -n "${opened_check}" ]; then
        echo -e "File is still opened after restore --staged"
        return 1
    fi

    ${GFP_CMD} add "${rfile}" >/dev/null 2>&1
    local commit_out
    commit_out=$(${GFP_CMD} commit -m "CL to restore ${RUN_ID}" 2>&1)
    local cl_id
    cl_id=$(echo "${commit_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    if ! ${GFP_CMD} restore --cl "${cl_id}" >/dev/null 2>&1; then
        echo -e "gfp restore --cl ${cl_id} failed"
        return 1
    fi

    local cl_check
    cl_check=$(p4 -p "${P4PORT}" -u "${P4USER}" change -o "${cl_id}" 2>/dev/null || true)
    if echo "${cl_check}" | grep -qi "Status: pending"; then
        echo -e "Changelist ${cl_id} was not deleted by restore --cl"
        return 1
    fi

    rm -f "${rfile}"

    # Test restoring unopened modified file (p4 clean -e -d)
    local ufile="test_restore_unopened_${RUN_ID}.txt"
    echo "baseline restore ${RUN_ID}" > "${ufile}"
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" add "${ufile}" >/dev/null 2>&1
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" submit -d "Baseline for unopened restore" >/dev/null 2>&1

    # Modify locally on disk without p4 open
    echo "unopened modification ${RUN_ID}" >> "${ufile}"

    # Run gfp restore on the unopened file
    if ! ${GFP_CMD} restore "${ufile}" >/dev/null 2>&1; then
        echo -e "gfp restore on unopened file failed"
        return 1
    fi
    if grep -q "unopened modification ${RUN_ID}" "${ufile}"; then
        echo -e "gfp restore did not revert unopened file modification"
        return 1
    fi
    if ! grep -q "baseline restore ${RUN_ID}" "${ufile}"; then
        echo -e "gfp restore failed to recover baseline content"
        return 1
    fi

    rm -f "${ufile}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 23: Diffing Locally Opened Files in Pending CL (gfp diff -c <CL>)
# ------------------------------------------------------------------------------
test_pending_diff() {
    local dfile="test_diff_cl_${RUN_ID}.txt"
    echo "initial line" > "${dfile}"
    ${GFP_CMD} add "${dfile}" >/dev/null 2>&1
    local commit_out
    commit_out=$(${GFP_CMD} commit -m "Pending CL for diff ${RUN_ID}" 2>&1)
    local cl_id
    cl_id=$(echo "${commit_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    echo "modified line" > "${dfile}"

    local diff_out
    if ! diff_out=$(${GFP_CMD} diff -c "${cl_id}" 2>&1); then
        echo -e "gfp diff -c ${cl_id} failed:\n${diff_out}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl_id}" //... >/dev/null 2>&1 || true
        p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl_id}" >/dev/null 2>&1 || true
        return 1
    fi
    echo "${diff_out}" | grep -qi "modified line\|diff" || return 1

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl_id}" //... >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl_id}" >/dev/null 2>&1 || true
    rm -f "${dfile}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 24: Rebase Squash (gfp rebase --squash <cl2> --onto <cl1>)
# ------------------------------------------------------------------------------
test_rebase_squash() {
    local f1="test_reb_1_${RUN_ID}.txt"
    local f2="test_reb_2_${RUN_ID}.txt"
    echo "reb 1" > "${f1}"
    echo "reb 2" > "${f2}"

    ${GFP_CMD} add "${f1}" >/dev/null 2>&1
    local c1_out
    c1_out=$(${GFP_CMD} commit "${f1}" -m "First feature ${RUN_ID}" 2>&1)
    local cl1
    cl1=$(echo "${c1_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    ${GFP_CMD} add "${f2}" >/dev/null 2>&1
    local c2_out
    c2_out=$(${GFP_CMD} commit "${f2}" -m "Second fix ${RUN_ID}" 2>&1)
    local cl2
    cl2=$(echo "${c2_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    local reb_out
    if ! reb_out=$(${GFP_CMD} rebase --squash "${cl2}" --onto "${cl1}" 2>&1); then
        echo -e "gfp rebase --squash failed:\n${reb_out}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert //... >/dev/null 2>&1 || true
        p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl1}" >/dev/null 2>&1 || true
        p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl2}" >/dev/null 2>&1 || true
        return 1
    fi

    local cl1_opened
    cl1_opened=$(p4 -p "${P4PORT}" -u "${P4USER}" opened -c "${cl1}" 2>/dev/null || true)
    echo "${cl1_opened}" | grep -q "${f1}" || return 1
    echo "${cl1_opened}" | grep -q "${f2}" || return 1

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl1}" //... >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl1}" >/dev/null 2>&1 || true
    rm -f "${f1}" "${f2}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 25: Pull Workflow (Sync & Auto-Resolve)
# ------------------------------------------------------------------------------
test_pull() {
    # 1. Test dry-run preview
    local pull_preview
    if ! pull_preview=$(${GFP_CMD} pull -n 2>&1); then
        echo -e "gfp pull -n preview failed:\n${pull_preview}"
        return 1
    fi
    echo "${pull_preview}" | grep -qi "previewing revisions to sync" || return 1

    # 2. Test standard pull sync
    local pull_out
    if ! pull_out=$(${GFP_CMD} pull 2>&1); then
        echo -e "gfp pull failed:\n${pull_out}"
        return 1
    fi
    echo "${pull_out}" | grep -qi "syncing workspace from depot" || return 1

    # 3. Test force pull (-f)
    local force_pull_out
    if ! force_pull_out=$(${GFP_CMD} pull -f 2>&1); then
        echo -e "gfp pull -f failed:\n${force_pull_out}"
        return 1
    fi
    echo "${force_pull_out}" | grep -qi "syncing workspace from depot" || return 1
    return 0
}

# ------------------------------------------------------------------------------
# Test 26: Resolve Workflow (Conflict Resolution with --ours, --theirs, -n)
# ------------------------------------------------------------------------------
test_resolve() {
    # Test resolve -n (dry-run)
    local res_dry
    if ! res_dry=$(${GFP_CMD} resolve -n 2>&1); then
        echo -e "gfp resolve -n failed:\n${res_dry}"
        return 1
    fi

    # Create baseline file submitted to depot
    local res_file="test_resolve_file_${RUN_ID}.txt"
    echo "Original depot baseline" > "${res_file}"
    ${GFP_CMD} add "${res_file}" >/dev/null 2>&1
    ${GFP_CMD} commit -m "Baseline for resolve test ${RUN_ID}" >/dev/null 2>&1
    ${GFP_CMD} push -f >/dev/null 2>&1

    # Submit rev 2 from super/another context directly
    p4 -p "${P4PORT}" -u super -c devuser_ws edit "${res_file}" >/dev/null 2>&1
    echo "Depot revision 2" > "${res_file}"
    p4 -p "${P4PORT}" -u super -c devuser_ws submit -d "Depot update for resolve test ${RUN_ID}" >/dev/null 2>&1

    # In local workspace, create local modification against rev 1
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" sync "${res_file}#1" >/dev/null 2>&1
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" edit "${res_file}" >/dev/null 2>&1
    echo "Workspace revision" > "${res_file}"

    # Sync head to trigger conflict
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" sync "${res_file}" >/dev/null 2>&1 || true

    # Resolve using --ours (-ay)
    local res_ours
    if ! res_ours=$(${GFP_CMD} resolve --ours "${res_file}" 2>&1); then
        echo -e "gfp resolve --ours failed:\n${res_ours}"
        return 1
    fi

    # Verify our workspace content was kept
    if ! grep -q "Workspace revision" "${res_file}"; then
        echo -e "resolve --ours did not preserve workspace revision"
        return 1
    fi

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert "${res_file}" >/dev/null 2>&1 || true
    return 0
}

# ------------------------------------------------------------------------------
# Test 27: Reopen Workflow (Relocating Opened Files Between Changelists)
# ------------------------------------------------------------------------------
test_reopen() {
    local f1="test_reopen_1_${RUN_ID}.txt"
    local f2="test_reopen_2_${RUN_ID}.txt"
    echo "content 1" > "${f1}"
    echo "content 2" > "${f2}"
    ${GFP_CMD} add "${f1}" "${f2}" >/dev/null 2>&1

    # Create a pending changelist with empty description
    local commit_out
    commit_out=$(${GFP_CMD} commit -m "Target CL for reopen ${RUN_ID}" 2>&1)
    local target_cl
    target_cl=$(echo "${commit_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    # Both files were swept into target_cl, let's reopen f1 back to default changelist
    if ! ${GFP_CMD} reopen -c default "${f1}" >/dev/null 2>&1; then
        echo -e "gfp reopen -c default failed"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert //... >/dev/null 2>&1 || true
        p4 -p "${P4PORT}" -u "${P4USER}" change -d "${target_cl}" >/dev/null 2>&1 || true
        return 1
    fi

    # Verify f1 is now in default and f2 is in target_cl
    local default_opened
    default_opened=$(p4 -p "${P4PORT}" -u "${P4USER}" opened -c default 2>/dev/null || true)
    local cl_opened
    cl_opened=$(p4 -p "${P4PORT}" -u "${P4USER}" opened -c "${target_cl}" 2>/dev/null || true)

    echo "${default_opened}" | grep -q "${f1}" || return 1
    echo "${cl_opened}" | grep -q "${f2}" || return 1

    # Move f1 back into target_cl
    if ! ${GFP_CMD} reopen -c "${target_cl}" "${f1}" >/dev/null 2>&1; then
        echo -e "gfp reopen -c ${target_cl} failed"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert //... >/dev/null 2>&1 || true
        p4 -p "${P4PORT}" -u "${P4USER}" change -d "${target_cl}" >/dev/null 2>&1 || true
        return 1
    fi

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${target_cl}" //... >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" change -d "${target_cl}" >/dev/null 2>&1 || true
    rm -f "${f1}" "${f2}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 28: Branch Full Lifecycle (Create, Query Verbose, and Delete)
# ------------------------------------------------------------------------------
test_branch_lifecycle() {
    local stream_name="//stream/test-stream-${RUN_ID}"

    # 1. Create a development stream
    local create_out
    if ! create_out=$(${GFP_CMD} branch "${stream_name}" -t development -P //stream/main 2>&1); then
        echo -e "gfp branch create failed:\n${create_out}"
        return 1
    fi

    # 2. List with -v (verbose) and check stream existence and parent
    local list_v
    if ! list_v=$(${GFP_CMD} branch -v 2>&1); then
        echo -e "gfp branch -v failed:\n${list_v}"
        ${GFP_CMD} branch -d "${stream_name}" >/dev/null 2>&1 || true
        return 1
    fi
    echo "${list_v}" | grep -qi "${stream_name}" || return 1

    # 3. Delete the stream
    local del_out
    if ! del_out=$(${GFP_CMD} branch -d "${stream_name}" 2>&1); then
        echo -e "gfp branch -d failed:\n${del_out}"
        return 1
    fi

    # 4. Verify stream is gone
    local list_after
    list_after=$(${GFP_CMD} branch 2>&1)
    if echo "${list_after}" | grep -q "${stream_name}"; then
        echo -e "Stream ${stream_name} still exists after deletion"
        return 1
    fi
    return 0
}

# ------------------------------------------------------------------------------
# Test 29: Cross-Stream Auto-Stashing Invariant (gfp switch -s)
# ------------------------------------------------------------------------------
test_switch_auto_stash() {
    # Ensure //stream/dev has baseline files populated from //stream/main
    p4 -p "${P4PORT}" -u "${P4USER}" populate -S //stream/dev -d "Populate dev stream from main" >/dev/null 2>&1 || true

    local stash_file="README.md"
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" edit "${stash_file}" >/dev/null 2>&1
    echo "# Auto-stash test edit ${RUN_ID}" >> "${stash_file}"

    # Switch to //stream/dev with -s (auto-stash)
    local switch_dev_out
    if ! switch_dev_out=$(${GFP_CMD} switch -s //stream/dev 2>&1); then
        echo -e "gfp switch -s //stream/dev failed:\n${switch_dev_out}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert "${stash_file}" >/dev/null 2>&1 || true
        return 1
    fi

    # Verify stream is switched
    local br_dev
    br_dev=$(${GFP_CMD} branch 2>&1)
    if ! echo "${br_dev}" | grep -q "\* //stream/dev"; then
        echo -e "Stream did not switch to //stream/dev:\n${br_dev}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert "${stash_file}" >/dev/null 2>&1 || true
        return 1
    fi

    # Verify file is still present and opened in workspace
    local st_out
    st_out=$(${GFP_CMD} status 2>&1)
    if ! echo "${st_out}" | grep -q "${stash_file}"; then
        echo -e "Status in //stream/dev did not show stashed file:\n${st_out}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert "${stash_file}" >/dev/null 2>&1 || true
        return 1
    fi

    # Switch back to //stream/main with -s
    local switch_main_out
    if ! switch_main_out=$(${GFP_CMD} switch -s //stream/main 2>&1); then
        echo -e "gfp switch -s //stream/main failed:\n${switch_main_out}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert "${stash_file}" >/dev/null 2>&1 || true
        return 1
    fi

    local br_main
    br_main=$(${GFP_CMD} branch 2>&1)
    if ! echo "${br_main}" | grep -q "\* //stream/main"; then
        echo -e "Stream did not switch back to //stream/main:\n${br_main}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert "${stash_file}" >/dev/null 2>&1 || true
        return 1
    fi

    ${GFP_CMD} checkout "${stash_file}" >/dev/null 2>&1 || true
    return 0
}

# ------------------------------------------------------------------------------
# Test 30: Diffstat Summary Output (gfp diff --stat)
# ------------------------------------------------------------------------------
test_diff_stat() {
    local stat_file="test_stat_${RUN_ID}.txt"
    echo "Line A" > "${stat_file}"
    ${GFP_CMD} add "${stat_file}" >/dev/null 2>&1

    local stat_out
    if ! stat_out=$(${GFP_CMD} diff --stat 2>&1); then
        echo -e "gfp diff --stat failed:\n${stat_out}"
        return 1
    fi

    echo "${stat_out}" | grep -qi "changed" || return 1
    echo "${stat_out}" | grep -qi "insertion" || return 1

    ${GFP_CMD} checkout "${stat_file}" >/dev/null 2>&1 || true
    rm -f "${stat_file}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 31: Clean Dry-Run vs Force (-n vs -f -d)
# ------------------------------------------------------------------------------
test_clean_dry_run_and_dirs() {
    local junk_dir="test_junk_dir_${RUN_ID}"
    mkdir -p "${junk_dir}"
    touch "${junk_dir}/junk.tmp"

    # Clean dry-run (-n) preview
    local clean_n_out
    clean_n_out=$(${GFP_CMD} clean -n -d 2>&1)
    if [ ! -d "${junk_dir}" ] || [ ! -f "${junk_dir}/junk.tmp" ]; then
        echo -e "gfp clean -n unexpectedly deleted directory or file"
        return 1
    fi

    # Clean force with directory deletion (-f -d)
    if ! ${GFP_CMD} clean -f -d >/dev/null 2>&1; then
        echo -e "gfp clean -f -d failed"
        rm -rf "${junk_dir}"
        return 1
    fi

    if [ -d "${junk_dir}" ]; then
        echo -e "gfp clean -f -d did not remove untracked directory"
        rm -rf "${junk_dir}"
        return 1
    fi
    return 0
}

# ------------------------------------------------------------------------------
# Test 32: Commit with Auto-Reconcile (gfp commit -a -m "...")
# ------------------------------------------------------------------------------
test_commit_auto_reconcile() {
    # Write a new file directly without running gfp add first
    local auto_file="test_auto_${RUN_ID}.py"
    echo "auto_staged = True" > "${auto_file}"

    local commit_out
    if ! commit_out=$(${GFP_CMD} commit -a -m "Auto reconcile commit ${RUN_ID}" 2>&1); then
        echo -e "gfp commit -a failed:\n${commit_out}"
        rm -f "${auto_file}"
        return 1
    fi
    local cl_id
    cl_id=$(echo "${commit_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1)

    local cl_opened
    cl_opened=$(p4 -p "${P4PORT}" -u "${P4USER}" opened -c "${cl_id}" 2>/dev/null || true)
    echo "${cl_opened}" | grep -q "${auto_file}" || return 1

    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl_id}" //... >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl_id}" >/dev/null 2>&1 || true
    rm -f "${auto_file}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 33: Stash Drop and Show (gfp stash drop & gfp stash show)
# ------------------------------------------------------------------------------
test_stash_drop_and_show() {
    local sfile="test_sdrop_${RUN_ID}.txt"
    echo "stash drop line" > "${sfile}"
    ${GFP_CMD} add "${sfile}" >/dev/null 2>&1

    local save_out
    save_out=$(${GFP_CMD} stash save -m "Stash to drop ${RUN_ID}" 2>&1)
    local cl_id
    cl_id=$(echo "${save_out}" | grep -oE "stash [0-9]+" | awk '{print $2}' | head -n1)
    if [ -z "${cl_id}" ]; then
        cl_id=$(echo "${save_out}" | grep -oE "changelist [0-9]+" | awk '{print $2}' | head -n1)
    fi

    # Verify stash show outputs describe content
    local show_out
    if ! show_out=$(${GFP_CMD} stash show -c "${cl_id}" 2>&1); then
        echo -e "gfp stash show failed:\n${show_out}"
        ${GFP_CMD} stash drop -c "${cl_id}" >/dev/null 2>&1 || true
        return 1
    fi
    echo "${show_out}" | grep -qi "${cl_id}" || return 1

    # Drop the stash
    if ! ${GFP_CMD} stash drop -c "${cl_id}" >/dev/null 2>&1; then
        echo -e "gfp stash drop failed"
        return 1
    fi

    # Verify changelist no longer exists
    local cl_check
    cl_check=$(p4 -p "${P4PORT}" -u "${P4USER}" change -o "${cl_id}" 2>/dev/null || true)
    if echo "${cl_check}" | grep -qi "Status: pending"; then
        echo -e "Stashed changelist ${cl_id} still exists after drop"
        return 1
    fi
    rm -f "${sfile}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 34: Perforce Special Path Escaping (@, #, %, *)
# ------------------------------------------------------------------------------
test_special_character_escaping() {
    local esc_file="test_%percent_#hash_@at_${RUN_ID}.txt"
    echo "Content with special path escaping ${RUN_ID}" > "${esc_file}"

    # Add file
    local add_out
    if ! add_out=$(${GFP_CMD} add "${esc_file}" 2>&1); then
        echo -e "gfp add with special characters failed:\n${add_out}"
        rm -f "${esc_file}"
        return 1
    fi

    # Status check
    local st_out
    st_out=$(${GFP_CMD} status 2>&1)
    if ! echo "${st_out}" | grep -qi "percent"; then
        echo -e "gfp status did not show escaped file:\n${st_out}\nadd output was:\n${add_out}"
        return 1
    fi

    # Diff check
    local diff_out
    diff_out=$(${GFP_CMD} diff "${esc_file}" 2>&1)
    if ! echo "${diff_out}" | grep -qi "Content with special path escaping"; then
        echo -e "gfp diff did not output file content:\n${diff_out}"
        return 1
    fi

    # Commit
    local ci_out
    ci_out=$(${GFP_CMD} commit "${esc_file}" -m "Commit special path ${RUN_ID}" 2>&1)
    local cl_id
    cl_id=$(echo "${ci_out}" | grep -oE "Change [0-9]+" | awk '{print $2}' | head -n1 || true)
    if [ -z "${cl_id}" ]; then
        echo -e "gfp commit failed to create pending CL:\n${ci_out}"
        return 1
    fi

    # Cleanup
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" revert -c "${cl_id}" //... >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" change -d "${cl_id}" >/dev/null 2>&1 || true
    rm -f "${esc_file}"
    return 0
}

# ------------------------------------------------------------------------------
# Test 35: Declarative JSON Plugins (.gfp/plugins.json)
# ------------------------------------------------------------------------------
test_json_plugin() {
    mkdir -p "${WS_DIR}/.gfp"
    cat <<EOF > "${WS_DIR}/.gfp/plugins.json"
{
    "server-info": {
        "exec": "p4 info",
        "help": "Query server info via external plugin"
    }
}
EOF

    local plugin_out
    if ! plugin_out=$(${GFP_CMD} server-info 2>&1); then
        echo -e "External JSON plugin execution failed:\n${plugin_out}"
        rm -f "${WS_DIR}/.gfp/plugins.json"
        return 1
    fi

    echo "${plugin_out}" | grep -qi "Server address:\|User name:" || return 1
    rm -f "${WS_DIR}/.gfp/plugins.json"
    return 0
}

# ------------------------------------------------------------------------------
# Test 36: Workspace Resolution from Deep Subdirectory
# ------------------------------------------------------------------------------
test_subdirectory_workspace_resolution() {
    local deep_dir="${WS_DIR}/deep/nested/sub/dir"
    mkdir -p "${deep_dir}"

    (
        cd "${deep_dir}"
        local sub_st
        if ! sub_st=$(${GFP_CMD} status 2>&1); then
            echo -e "gfp status from subdirectory failed:\n${sub_st}"
            exit 1
        fi
        echo "${sub_st}" | grep -qi "On Perforce workspace" || exit 1
    )
    local sub_rc=$?

    rm -rf "${WS_DIR}/deep"
    return ${sub_rc}
}

# ==============================================================================
# Execution Dispatcher
# ==============================================================================
if [ "${LIST_ONLY}" = true ]; then
    echo -e "${BOLD}${BLUE}Available gfp-cli Test Scenarios:${NC}\n"
    run_unit_tests
fi

echo "================================================="
echo " Starting gfp-cli Playground Test Suite"
echo " Run ID:     ${RUN_ID}"
echo " CLI Target: ${GFP_CMD}"
echo " Workspace:  ${WS_DIR}"
echo " P4PORT:     ${P4PORT}"
echo " P4CLIENT:   ${P4CLIENT}"
if [ -n "${FILTER}" ]; then
echo " Filter:     ${FILTER}"
fi
echo "================================================="
echo ""

# 1. Run Python Unit & Regression Test Suite
run_unit_tests

# 2. Run End-to-End Integration Tests
run_test "CLI Engine & Global --help" test_cli_help
run_test "gfp status (clean workspace)" test_status_clean
run_test "gfp add (staging new file)" test_add_and_status
run_test "gfp diff (unified diff output)" test_diff
run_test "gfp commit (create numbered pending changelist)" test_commit
run_test "gfp commit --amend (update pending CL and description)" test_commit_amend
run_test "gfp show (describe changelist details)" test_show
run_test "gfp push (gated submit queue & force -f submit)" test_push
run_test "gfp log (history viewer)" test_log
run_test "gfp blame (line annotation history)" test_blame
run_test "gfp stash (save, list, show, pop)" test_stash_workflow
run_test "gfp branch (stream overview)" test_branch
run_test "gfp switch (stream switching)" test_switch
run_test "gfp checkout & gfp clean (revert and workspace cleanup)" test_checkout_and_clean
run_test "gfp lifecycle hooks (pre/post execution & abort enforcement)" test_lifecycle_hooks
run_test "gfp completion (bash generation)" test_completion
run_test "gfp clone (stream clone, workspace creation, and sync)" test_clone
run_test "gfp aliases (st -> status, ci -> commit)" test_aliases
run_test "gfp log -a (full changelist history without truncation)" test_log_all
run_test "gfp status -c (pending changelists with opened files)" test_status_pending_cl
run_test "gfp commit (selective file commit)" test_selective_commit
run_test "gfp restore (--staged and --cl)" test_restore
run_test "gfp diff -c (locally opened pending changelist diff)" test_pending_diff
run_test "gfp rebase (--squash CL into target CL)" test_rebase_squash
run_test "gfp pull (sync & auto-resolve)" test_pull
run_test "gfp resolve (conflict resolution with --ours, -n)" test_resolve
run_test "gfp reopen (relocating opened files between changelists)" test_reopen
run_test "gfp branch (full lifecycle creation, query verbose, delete)" test_branch_lifecycle
run_test "gfp switch -s (cross-stream auto-stashing invariant)" test_switch_auto_stash
run_test "gfp diff --stat (diffstat summary histogram)" test_diff_stat
run_test "gfp clean (dry-run -n vs force -f -d)" test_clean_dry_run_and_dirs
run_test "gfp commit -a (auto-reconcile unstaged modifications)" test_commit_auto_reconcile
run_test "gfp stash drop & show (shelf inspection and deletion)" test_stash_drop_and_show
run_test "gfp special characters (@, #, %, * path escaping)" test_special_character_escaping
run_test "gfp declarative JSON plugins (.gfp/plugins.json)" test_json_plugin
run_test "gfp workspace resolution (deep nested subdirectory)" test_subdirectory_workspace_resolution

if [ "${LIST_ONLY}" = true ]; then
    echo -e "\nTotal Scenarios Registered: ${#ALL_TEST_NAMES[@]}"
    exit 0
fi

# ------------------------------------------------------------------------------
# Final Summary & Exit
# ------------------------------------------------------------------------------
echo "================================================="
echo " Test Suite Summary"
echo " Passed:  ${PASSED_TESTS}"
echo " Failed:  ${FAILED_TESTS}"
if [ "${SKIPPED_TESTS}" -gt 0 ]; then
echo " Skipped: ${SKIPPED_TESTS}"
fi
echo "================================================="

if [ "${FAILED_TESTS}" -eq 0 ]; then
    echo -e "${GREEN}All gfp-cli tests passed successfully!${NC}"
    exit 0
else
    echo -e "${RED}${FAILED_TESTS} test(s) failed. Please review diagnostics above.${NC}"
    exit 1
fi
