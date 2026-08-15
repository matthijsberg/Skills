#!/usr/bin/env bash
set -e
echo "==========================================================="
echo "           ZEITGEIST DEMO - TEMPORAL AWARENESS            "
echo "==========================================================="

echo -e "\n1. [Atomic Sync] Stratum-1 Clock Precision:"
python3 scripts/zeitgeist.py atomic-sync

echo -e "\n2. [Now Context] Local Amsterdam + Bali Context:"
python3 scripts/zeitgeist.py now --loc "Amsterdam"
python3 scripts/zeitgeist.py now --loc "Bali"

echo -e "\n3. [Micro Horizon: Ferry naar Gili]"
python3 scripts/zeitgeist.py query "morgen om 10:00 ferry" --loc "Gili Trawangan"

echo -e "\n4. [Clima Horizon: Skiën in Gerlos over 6 maanden]"
python3 scripts/zeitgeist.py query "in januari" --loc "Gerlos"

echo -e "\n5. [Solar Context: Zonsondergang Bali]"
python3 scripts/zeitgeist.py solar "2026-08-15" --loc "Bali"

echo -e "\n==========================================================="
echo "Demo finished successfully!"
