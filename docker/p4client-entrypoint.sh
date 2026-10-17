#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# SECTION 1: Path & Variable Configuration
# ==============================================================================
P4PORT="${P4PORT:-p4server:1666}"
P4USER="${P4USER:-devuser}"
P4CLIENT="${P4CLIENT:-devuser_ws}"
P4STREAM="${P4STREAM:-//stream/main}"

HOME_DIR="/home/devuser"
WORKSPACE_DIR="${HOME_DIR}/workspace"
CLIENT_ROOT="${WORKSPACE_DIR}/devuser-stream-ws"

echo "================================================="
echo " Starting Perforce Client & noVNC Environment"
echo " P4PORT:      ${P4PORT}"
echo " P4USER:      ${P4USER}"
echo " P4CLIENT:    ${P4CLIENT}"
echo " P4STREAM:    ${P4STREAM}"
echo " CLIENT ROOT: ${CLIENT_ROOT}"
echo "================================================="

sudo mkdir -p "${CLIENT_ROOT}"
sudo chown -R "${P4USER}:${P4USER}" "${WORKSPACE_DIR}"

# ==============================================================================
# SECTION 2: Process Signals & Lifecycle Trapping
# ==============================================================================
cleanup() {
    echo "[p4client-lifecycle] Stopping desktop services..."
    vncserver -kill :1 2>/dev/null || true
    rm -f /tmp/.X11-unix/X1 /tmp/.X1-lock
    if [ -n "${WEBSOCK_PID:-}" ]; then
        kill -TERM "${WEBSOCK_PID}" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

# ==============================================================================
# SECTION 3: Global Wrapper Scripts Provisioning
# ==============================================================================
sudo mkdir -p /usr/local/bin
cat <<'EOF' | sudo tee /usr/local/bin/gfp >/dev/null
#!/usr/bin/env bash
if [ -f "/opt/gfp-cli/gfp.py" ]; then
    exec python3 /opt/gfp-cli/gfp.py "$@"
else
    echo "Error: /opt/gfp-cli/gfp.py not found." >&2
    exit 1
fi
EOF
sudo chmod +x /usr/local/bin/gfp

cat <<'EOF' | sudo tee /usr/local/bin/gfp-test >/dev/null
#!/usr/bin/env bash
if [ -f "/opt/gfp-cli/tests/test_gfp.sh" ]; then
    exec /bin/bash /opt/gfp-cli/tests/test_gfp.sh "$@"
else
    echo "Error: /opt/gfp-cli/tests/test_gfp.sh not found." >&2
    exit 1
fi
EOF
sudo chmod +x /usr/local/bin/gfp-test

# ==============================================================================
# SECTION 4: Server Readiness & Workspace Setup
# ==============================================================================
echo "[p4client-init] Waiting for Perforce Server (${P4PORT})..."
P4_UP=0
for i in $(seq 1 45); do
    if p4 -p "${P4PORT}" -u "${P4USER}" info -s >/dev/null 2>&1; then
        echo "[p4client-init] Connected to Perforce Server successfully."
        P4_UP=1
        break
    fi
    sleep 1
done

if [ "${P4_UP}" -ne 1 ]; then
    echo "[p4client-init] FATAL: Could not connect to ${P4PORT} within 45 seconds." >&2
    exit 1
fi

echo "[p4client-init] Provisioning workspace '${P4CLIENT}'..."
p4 -p "${P4PORT}" -u "${P4USER}" \
    --field "Root=${CLIENT_ROOT}" \
    --field "Host=" \
    --field "Options=allwrite clobber nocompress unlocked" \
    client -o -S "${P4STREAM}" "${P4CLIENT}" | p4 -p "${P4PORT}" -u "${P4USER}" client -i

# Write .p4config so local directory sessions pick up connection details
cat <<EOF >"${CLIENT_ROOT}/.p4config"
P4PORT=${P4PORT}
P4USER=${P4USER}
P4CLIENT=${P4CLIENT}
EOF

# Copy .p4config to base workspace folder for convenience
cp "${CLIENT_ROOT}/.p4config" "${WORKSPACE_DIR}/.p4config"

echo "[p4client-init] Syncing workspace..."
(
    cd "${CLIENT_ROOT}"
    p4 -p "${P4PORT}" -u "${P4USER}" -c "${P4CLIENT}" sync || true
)

if [ ! -d "${CLIENT_ROOT}/.gfp" ]; then
    mkdir -p "${CLIENT_ROOT}/.gfp/hooks"
    cat <<'EOF' >"${CLIENT_ROOT}/.gfp/hooks/pre-commit"
#!/usr/bin/env bash
echo "[gfp hook: pre-commit] Running pre-commit validation checks..."
exit 0
EOF
    chmod +x "${CLIENT_ROOT}/.gfp/hooks/pre-commit"

    cat <<'EOF' >"${CLIENT_ROOT}/.gfp/hooks/post-commit"
#!/usr/bin/env bash
echo "[gfp hook: post-commit] Commit completed successfully."
exit 0
EOF
    chmod +x "${CLIENT_ROOT}/.gfp/hooks/post-commit"
fi

# ==============================================================================
# SECTION 5: Desktop & VNC/noVNC Startup
# ==============================================================================
vncserver -kill :1 2>/dev/null || true
rm -f /tmp/.X11-unix/X1 /tmp/.X1-lock

echo "[p4client-init] Starting TigerVNC..."
vncserver :1 -geometry 1920x1080 -depth 24 -localhost no

echo "[p4client-init] Starting websockify bridge..."
websockify --web=/usr/share/novnc/ 6080 localhost:5901 &
WEBSOCK_PID=$!

wait "${WEBSOCK_PID}"
