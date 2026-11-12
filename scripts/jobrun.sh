#!/bin/bash
# 后台任务包装：pipefail + 状态标记 + 显式 exit code（不再被 | tail 掩盖）
set -o pipefail
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
JOB="${1:?job name}"; LOG="${2:?log path}"; shift 2
STATUS_DIR="$(cd "$(dirname "$0")/.." && pwd)/work/jobs"; mkdir -p "$STATUS_DIR"
MARK="$STATUS_DIR/${JOB}.status"
echo "START $(date '+%F %T')" > "$MARK"
cleanup() {
  code=$?
  if [ $code -eq 0 ]; then echo "DONE $(date '+%F %T') EXIT:0" >> "$MARK"
  elif [ $code -eq 143 ] || [ $code -eq 130 ]; then echo "KILLED $(date '+%F %T') EXIT:$code" >> "$MARK"
  else echo "FAILED $(date '+%F %T') EXIT:$code" >> "$MARK"; fi
}
trap cleanup EXIT
"$@" 2>&1 | tee "$LOG"
code=${PIPESTATUS[0]}
echo "EXIT:$code"
exit $code
