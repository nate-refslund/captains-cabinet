#!/usr/bin/env bash
# Enduring, egg-safe verification for the Cognitive Core architecture contract.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${CABINET_PYTHON:-python3.12}"
cd "$ROOT"

"$PY" -m pytest \
  framework/evolution/tests/test_contracts.py \
  cabinet/scripts/tests/test_cognitive_architecture_census.py -q
"$PY" cabinet/scripts/cognitive-architecture-census.py --check
bash cabinet/scripts/check-layer-separation.sh

echo "cognitive architecture verify: PASS"
