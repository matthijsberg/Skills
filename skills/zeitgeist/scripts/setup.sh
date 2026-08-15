#!/usr/bin/env bash
set -e
echo "=== Setting up Zeitgeist Temporal Awareness Skill ==="
# pyyaml is VERPLICHT: zonder pyyaml wordt config.yaml stil genegeerd.
python3 -m pip install -q dateparser astral holidays pyyaml
echo "✓ Dependencies installed (dateparser, astral, holidays, pyyaml)."
python3 "$(dirname "$0")/zeitgeist.py" atomic-sync --json || echo "⚠ Atomic sync mislukt (geen netwerk?) — skill valt terug op de systeemklok."
echo "=== Setup complete! ==="
