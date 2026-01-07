#!/usr/bin/env bash
set -euo pipefail

PARTITIONS=(p0 p1 p2 p4)

sum_partition_gpus() {
  local part="$1"

  # Sum "gpu:*:<n>" occurrences in the GRES column for running jobs
  squeue -h -p "$part" -t R -O gres:200 2>/dev/null | \
    awk '
      {
        line = $0
        while (match(line, /gpu(:[^, ]+)*:([0-9]+)/, m)) {
          sum += m[2]
          line = substr(line, RSTART + RLENGTH)
        }
      }
      END { print sum + 0 }
    '
}

printf "%-6s %s\n" "PART" "ALLOC_GPUS"
for p in "${PARTITIONS[@]}"; do
  alloc="$(sum_partition_gpus "$p")"
  printf "%-6s %s\n" "$p" "$alloc"
done
