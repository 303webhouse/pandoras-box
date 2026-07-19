#!/bin/bash
# Stable Market Board - Daily Run (Mac/Linux)
# Run from any directory: this script will cd to its own location.

set -e
cd "$(dirname "$0")"

echo
echo "============================================================"
echo " STABLE MARKET BOARD - Daily Run"
echo " $(date)"
echo "============================================================"
echo

# Pick python3 if it exists, otherwise python
PYTHON=python3
command -v python3 >/dev/null 2>&1 || PYTHON=python

echo "[1/3] Pulling latest market data from Polygon..."
$PYTHON -m stable.ingest

echo
echo "[2/3] Computing metrics..."
$PYTHON -m stable.metrics

echo
echo "[3/3] Starting dashboard server..."
echo

# Open browser in background after a 3 sec delay (gives server time to start)
(sleep 3 && (open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null)) &

$PYTHON -m stable.server
