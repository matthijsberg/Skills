#!/usr/bin/env bash
set -e
echo "=== Setting up Zeitgeist Temporal Awareness Skill ==="
python3 -m pip install -q dateparser astral
echo "✓ Dependencies installed."
python3 scripts/zeitgeist.py atomic-sync --json
echo "✓ Atomic Clock synchronization verified."
echo "=== Setup complete! ==="
