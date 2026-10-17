#!/usr/bin/env bash
# ==============================================================================
# DPC-P4 Workspace Setup: source ./setup.sh
# ==============================================================================

CYAN="\033[38;2;137;221;255m"
ORANGE="\033[38;2;250;179;135m"
GREEN="\033[38;2;158;206;106m"
BOLD="\033[1m"
NC="\033[0m"

echo -e "${BOLD}${CYAN}------------------------------------------------------------${NC}"
echo -e "${BOLD}${ORANGE}<<-${NC}${CYAN} DPC-P4 WORKSPACE SETUP ${BOLD}${ORANGE}->>${NC}"
echo -e "${BOLD}${CYAN}------------------------------------------------------------${NC}"

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")/.." && pwd)" 2>/dev/null || _DIR="$(pwd)"
export WA="${_DIR}"

VENV_DIR="${WA}/.venv"
if [[ ! -d "${VENV_DIR}" ]]; then

    echo -e "  ${ORANGE}[+]${NC} Initializing Python virtual environment in .venv..."
    python3 -m venv "${VENV_DIR}"

    echo -e "Activating virtual environment..."
    source "${VENV_DIR}/bin/activate"

    if [[ -f "${WA}/scripts/python_requirements.txt" ]]; then
        echo -e "Installing dependencies from ${WA}/scripts/python_requirements.txt..."
        pip install -r "${WA}/scripts/python_requirements.txt"
    else
        echo "Warning: ${WA}/scripts/python_requirements.txt not found. Skipping installation."
    fi
else
    echo -e "Activating virtual environment..."
    source "${VENV_DIR}/bin/activate"
fi

export PYTHONUNBUFFERED=1
export PYTHONPYCACHEPREFIX="${WA}/output/__pycache__/"
export PYTHONPATH="${WA}/compiler:${WA}/src/dpc-p4/p4runtime:${PYTHONPATH:-}"

if [[ -f "${WA}/targets.env" ]]; then
    source "${WA}/targets.env"
fi

unset CYAN ORANGE GREEN BOLD NC _DIR VENV_DIR

