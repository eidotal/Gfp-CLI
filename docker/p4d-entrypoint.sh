#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# SECTION 1: Path & Variable Initialization
# ==============================================================================
export P4ROOT="${P4ROOT:-/data/p4root}"
export P4PORT="${P4PORT:-1666}"
export P4USER="${P4USER:-super}"
export P4JOURNAL="${P4JOURNAL:-/data/p4journal/journal}"
export P4LOG="${P4LOG:-/data/p4log/p4d.log}"
export CONFIG_FILE="${CONFIG_FILE:-/etc/perforce/p4-init-config.json}"
INIT_LOCK="${P4ROOT}/.initialized"

mkdir -p "${P4ROOT}" "$(dirname "${P4JOURNAL}")" "$(dirname "${P4LOG}")" "${P4ROOT}/triggers"

# ==============================================================================
# SECTION 2: Process Signals & Lifecycle Trapping
# ==============================================================================
cleanup() {
    echo "[p4d-lifecycle] Received termination signal. Initiating clean server stop..."
    p4 -p "${P4PORT}" -u "${P4USER}" admin stop 2>/dev/null || true
    if [ -n "${P4D_PID:-}" ]; then
        wait "${P4D_PID}" 2>/dev/null || true
    fi
    echo "[p4d-lifecycle] Server successfully stopped."
    exit 0
}
trap cleanup SIGTERM SIGINT

# ==============================================================================
# SECTION 3: First-Time Bootstrap & Declarative Provisioning
# ==============================================================================
if [ ! -f "${INIT_LOCK}" ]; then
    echo "=========================================================="
    echo " [p4d-init] First-time startup: Running Provisioning Pipeline"
    echo "=========================================================="

    # Step 3.1: Start background bootstrap instance
    echo "[p4d-init] Launching bootstrap p4d daemon..."
    p4d -r "${P4ROOT}" -J "${P4JOURNAL}" -L "${P4LOG}" &
    BOOTSTRAP_PID=$!

    # Step 3.2: Poll server port until responsive
    echo "[p4d-init] Polling server connectivity on ${P4PORT}..."
    P4D_READY=0
    for i in $(seq 1 30); do
        if p4 -p "${P4PORT}" -u "${P4USER}" info >/dev/null 2>&1; then
            P4D_READY=1
            echo "[p4d-init] Server is responsive."
            break
        fi
        sleep 1
    done

    if [ "${P4D_READY}" -ne 1 ]; then
        echo "[p4d-init] ERROR: Temporary p4d failed to respond within 30 seconds." >&2
        kill -TERM "${BOOTSTRAP_PID}" 2>/dev/null || true
        exit 1
    fi

    # Step 3.3: Set baseline server configuration
    echo "[p4d-init] Configuring core system parameters..."
    p4 -p "${P4PORT}" -u "${P4USER}" configure set dm.stream.parentview=1 >/dev/null 2>&1 || true
    p4 -p "${P4PORT}" -u "${P4USER}" configure set security=0 >/dev/null 2>&1 || true

    # Step 3.4: Ingest JSON specs
    if [ -f "${CONFIG_FILE}" ]; then
        echo "[p4d-init] Ingesting configuration from ${CONFIG_FILE}..."

        python3 - <<EOF
import json, subprocess, os

config_path = os.environ.get("CONFIG_FILE")
p4port = os.environ.get("P4PORT")
p4user = os.environ.get("P4USER")

with open(config_path, "r") as f:
    cfg = json.loads(os.path.expandvars(f.read()))

# 1. Depots
for d in cfg.get("depots", []):
    name = d["name"]
    dtype = d.get("type", "local")
    desc = d.get("description", f"Depot {name}")
    depth = d.get("depth", f"//{name}/1")
    mapping = d.get("map", f"{name}/...")

    spec = f"Depot: {name}\nType: {dtype}\nMap: {mapping}\nDescription:\n\t{desc}\n"
    if dtype == "stream":
        spec += f"StreamDepth: {depth}\n"

    proc = subprocess.run(
        ["p4", "-p", p4port, "-u", p4user, "depot", "-i"],
        input=spec, text=True, capture_output=True
    )
    print(f"[p4d-init] Provisioned Depot '{name}': {proc.stdout.strip() or proc.stderr.strip()}")

# 2. Streams
for s in cfg.get("streams", []):
    stream = s["stream"]
    stype = s.get("type", "mainline")
    parent = s.get("parent", "none")

    cmd = ["p4", "-p", p4port, "-u", p4user]
    if parent != "none":
        cmd.extend(["--field", f"Parent={parent}"])
    cmd.extend(["stream", "-o", "-t", stype, stream])

    out = subprocess.check_output(cmd, text=True)
    proc = subprocess.run(
        ["p4", "-p", p4port, "-u", p4user, "stream", "-i"],
        input=out, text=True, capture_output=True
    )
    print(f"[p4d-init] Provisioned Stream '{stream}': {proc.stdout.strip() or proc.stderr.strip()}")

# 3. Users (with type mutation detection)
for u in cfg.get("users", []):
    user = u["user"]
    raw_email = u.get("email", "")
    email = raw_email if raw_email and not raw_email.startswith("$") else os.environ.get("GMAIL_USER", f"{user}@example.local")
    fullname = u.get("fullname", user)
    utype = u.get("type", "standard")

    check_user = subprocess.run(
        ["p4", "-p", p4port, "-u", p4user, "user", "-o", user],
        capture_output=True, text=True
    )

    current_type = "standard"
    for line in check_user.stdout.splitlines():
        if line.startswith("Type:"):
            current_type = line.split(":", 1)[1].strip()
            break

    if "Update:" in check_user.stdout and current_type != utype:
        print(f"[p4d-init] Recreating user '{user}' (changing type from '{current_type}' to '{utype}')...")
        subprocess.run(
            ["p4", "-p", p4port, "-u", p4user, "user", "-d", "-f", user],
            capture_output=True, text=True
        )

    spec = f"User: {user}\nEmail: {email}\nFullName: {fullname}\nType: {utype}\n"
    proc = subprocess.run(
        ["p4", "-p", p4port, "-u", p4user, "user", "-f", "-i"],
        input=spec, text=True, capture_output=True
    )
    print(f"[p4d-init] Provisioned User '{user}': {proc.stdout.strip() or proc.stderr.strip()}")

# 4. Groups
for g in cfg.get("groups", []):
    group = g["group"]
    users = g.get("users", [])
    max_results = str(g.get("max_results", "unset"))
    max_scan = str(g.get("max_scan_rows", "unset"))
    max_lock = str(g.get("max_lock_time", "unset"))
    timeout = str(g.get("timeout", "unset"))

    max_results = "unset" if max_results in ["0", "None"] else max_results
    max_scan = "unset" if max_scan in ["0", "None"] else max_scan
    max_lock = "unset" if max_lock in ["0", "None"] else max_lock

    spec = f"Group: {group}\nMaxResults: {max_results}\nMaxScanRows: {max_scan}\nMaxLockTime: {max_lock}\nTimeout: {timeout}\nUsers:\n"
    for member in users:
        spec += f"\t{member}\n"

    proc = subprocess.run(
        ["p4", "-p", p4port, "-u", p4user, "group", "-i"],
        input=spec, text=True, capture_output=True
    )
    print(f"[p4d-init] Provisioned Group '{group}': {proc.stdout.strip() or proc.stderr.strip()}")

# 5. Protection Table
protections = cfg.get("protections", [])
if protections:
    spec = "Protections:\n"
    for line in protections:
        spec += f"\t{line}\n"
    proc = subprocess.run(
        ["p4", "-p", p4port, "-u", p4user, "protect", "-i"],
        input=spec, text=True, capture_output=True
    )
    print(f"[p4d-init] Configured Protections Table: {proc.stdout.strip() or proc.stderr.strip()}")
EOF
    else
        echo "[p4d-init] WARNING: '${CONFIG_FILE}' not found. Skipping JSON ingest."
    fi

    # Step 3.5: Seed baseline commit into //stream/main
    echo "[p4d-init] Creating initial sample commit in //stream/main..."
    INIT_WS_DIR="$(mktemp -d /tmp/p4_init_ws.XXXXXX)"
    mkdir -p "${INIT_WS_DIR}/src" "${INIT_WS_DIR}/docs"

    p4 -p "${P4PORT}" -u "${P4USER}" --field "Root=${INIT_WS_DIR}" client -o -S //stream/main init_ws |
        p4 -p "${P4PORT}" -u "${P4USER}" client -i

    cat <<'EOF' >"${INIT_WS_DIR}/README.md"
# Playground Perforce Depot

Welcome to the `gfp` CLI playground!
This repository is running on a live Perforce Helix Core (`p4d`) server.
EOF

    cat <<'EOF' >"${INIT_WS_DIR}/src/main.py"
#!/usr/bin/env python3
def main():
    print("Hello from Perforce Helix Core & gfp CLI!")

if __name__ == "__main__":
    main()
EOF

    cat <<'EOF' >"${INIT_WS_DIR}/docs/architecture.md"
# System Architecture

- VCS Backend: Perforce Helix Core (p4d)
- CLI Translation Layer: gfp-cli
- Client GUI: Perforce P4V via noVNC
EOF

    (
        cd "${INIT_WS_DIR}"
        p4 -p "${P4PORT}" -u "${P4USER}" -c init_ws reconcile ... >/dev/null 2>&1 || true
        p4 -p "${P4PORT}" -u "${P4USER}" -c init_ws submit -d "Initial baseline project import" >/dev/null 2>&1 || true
    )

    p4 -p "${P4PORT}" -u "${P4USER}" client -d init_ws
    rm -rf "${INIT_WS_DIR}"

    # Populate child development stream //stream/dev from //stream/main
    p4 -p "${P4PORT}" -u "${P4USER}" populate -S //stream/dev -d "Initial baseline dev stream population" >/dev/null 2>&1 || true

    # Step 3.6: Configure submit-queue webhook notification trigger
    echo "[p4d-init] Setting up Jenkins submit-queue trigger..."
    cat <<'EOF' >"${P4ROOT}/triggers/notify_jenkins.sh"
#!/usr/bin/env bash
CL="$1"
USER="$2"
DESC=$(p4 -p 127.0.0.1:1666 -u super describe -s "${CL}" 2>/dev/null || true)
if echo "${DESC}" | grep -Eqi "Auto-stash|Stash:"; then
    exit 0
fi
DETECTED_STREAM=$(echo "${DESC}" | grep -o '//stream/[^/]*' | head -n1 || true)
STREAM="${DETECTED_STREAM:-//stream/main}"

curl -s -m 5 -X POST "http://jenkins:8080/generic-webhook-trigger/invoke?token=gfp-submit-token" \
    -H "Content-Type: application/json" \
    -d "{\"changelist\": \"${CL}\", \"user\": \"${USER}\", \"stream\": \"${STREAM}\"}" >/dev/null 2>&1 || true
exit 0
EOF
    chmod +x "${P4ROOT}/triggers/notify_jenkins.sh"

    printf "Triggers:\n\tjenkins_submit_gate shelve-commit //stream/... \"${P4ROOT}/triggers/notify_jenkins.sh %%changelist%% %%user%%\"\n" |
        p4 -p "${P4PORT}" -u "${P4USER}" triggers -i

    # Step 3.7: Gracefully stop temporary daemon
    echo "[p4d-init] Stopping bootstrap p4d instance..."
    p4 -p "${P4PORT}" -u "${P4USER}" admin stop 2>/dev/null || true
    for i in $(seq 1 10); do
        if ! kill -0 "${BOOTSTRAP_PID}" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    wait "${BOOTSTRAP_PID}" 2>/dev/null || true

    touch "${INIT_LOCK}"
    echo "[p4d-init] Initialization complete."
fi

# ==============================================================================
# SECTION 4: Pre-Flight Journal Verification
# ==============================================================================
if [ -f "${P4JOURNAL}" ] && [ -s "${P4JOURNAL}" ]; then
    echo "[p4d-core] Verifying journal integrity: ${P4JOURNAL}..."
    p4d -r "${P4ROOT}" -jv "${P4JOURNAL}" || true
fi

# ==============================================================================
# SECTION 5: Foreground Production Execution
# ==============================================================================
echo "[p4d-core] Launching foreground p4d server on port ${P4PORT}..."
export P4PORT="${P4PORT}"
exec p4d -r "${P4ROOT}" -J "${P4JOURNAL}" -L "${P4LOG}"
