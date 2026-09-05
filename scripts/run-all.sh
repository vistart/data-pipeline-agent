#!/usr/bin/env bash
# Run all demo scenarios
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Running all demo scenarios..."
echo ""

for script in "$SCRIPT_DIR"/run-*.sh; do
    bash "$script"
    echo ""
    echo "=========================================="
    echo ""
done

echo "All scenarios completed!"
echo "Session files saved in: sessions/"
