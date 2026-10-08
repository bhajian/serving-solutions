#!/usr/bin/env bash
# Run every arm once, in a fixed order, at the same client concurrency.
#   KUBE_CONTEXT=<context> ./run_all.sh [suffix] [concurrency]   e.g. ./run_all.sh 1 8 -> labels r1, b1, t1
set -uo pipefail
suffix=${1:-1}; concurrency=${2:-8}
cd "$(dirname "$0")"
for spec in "random r$suffix" "optimized-baseline b$suffix" "optimized-baseline-tuned t$suffix"; do
  set -- $spec
  echo "=== $(date -u +%FT%TZ) start $1 ($2)"
  ./run_arm.sh "$1" "$2" "$concurrency" 2>&1 | grep -vE '^\s*$' | tail -25
  echo "=== $(date -u +%FT%TZ) end $1 exit=${PIPESTATUS[0]}"
done
