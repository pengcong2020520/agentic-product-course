#!/usr/bin/env bash
# 用 Codex CLI 与 Grok CLI 独立标注双标样本的各个分块（最多 5 个并发）。
# 用法：bash pipeline/label/run_annotators.sh [并发数，默认 5] [分块编号…，默认全部]
set -euo pipefail
cd "$(dirname "$0")/../.."
JOBS="${1:-5}"; shift || true
CHUNKS=("$@")
if [ ${#CHUNKS[@]} -eq 0 ]; then
  CHUNKS=($(ls data/double/chunks | sed -E 's/chunk-([0-9]+)\.jsonl/\1/'))
fi
mkdir -p data/double/{codex,grok,logs,briefs}

run_one() {
  local who="$1" n="$2"
  local in="data/double/chunks/chunk-$n.jsonl" out="data/double/$who/chunk-$n.jsonl"
  local brief="data/double/briefs/$who-$n.md" log="data/double/logs/$who-$n.log"
  if [ -s "$out" ] && python3 -I pipeline/label/check_labels.py "$in" "$out" >/dev/null 2>&1; then
    echo "跳过 $who $n（已完成且校验通过）"; return 0
  fi
  sed -e "s#{IN}#$in#g" -e "s#{OUT}#$out#g" pipeline/label/annotate-brief.md > "$brief"
  local start=$(date +%s)
  if [ "$who" = codex ]; then
    codex exec -C "$PWD" -s workspace-write -o "data/double/logs/$who-$n.final.md" - < "$brief" > "$log" 2>&1 || true
  else
    grok -p "$(cat "$brief")" --always-approve --cwd "$PWD" --disable-web-search > "$log" 2>&1 || true
  fi
  local verdict
  verdict=$(python3 -I pipeline/label/check_labels.py "$in" "$out" 2>&1 | head -1 || true)
  echo "$who $n 用时 $(( $(date +%s) - start ))s：$verdict"
}
export -f run_one

for n in "${CHUNKS[@]}"; do echo "grok $n"; echo "codex $n"; done | xargs -P "$JOBS" -L 1 bash -c 'run_one "$0" "$1"'
