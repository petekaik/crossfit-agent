#!/bin/bash
#
# Crossfit Agent — Cron Run Script
#
# This is called by Hermes Agent cron jobs.
# It activates the project venv, loads SA credentials from .env,
# and runs the pipeline.
#
set -euo pipefail

cd "/Users/petekaik/projects/crossfit-agent"

# Load environment variables if .env exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Activate venv
VENV_PYTHON="./venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "ERROR: venv not found. Run: python3.12 -m venv venv && ./venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Run the requested command
CMD="${1:-full}"

echo "=== Crossfit Agent Cron — $(date) ==="
echo "Command: $CMD"
echo "SA_EMAIL: ${SA_EMAIL:-not set}"
echo ""

case "$CMD" in
    search)
        "$VENV_PYTHON" scripts/cron_runner.py search
        ;;
    sync)
        "$VENV_PYTHON" scripts/cron_runner.py sync
        ;;
    full)
        "$VENV_PYTHON" scripts/cron_runner.py full
        ;;
    status)
        "$VENV_PYTHON" scripts/cron_runner.py status
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Usage: $0 {search|sync|full|status}"
        exit 1
        ;;
esac
