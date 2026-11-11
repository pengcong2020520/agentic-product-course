#!/usr/bin/env bash
# 用本机已登录的 Codex CLI / Grok CLI 按基因图谱标注分块（总并发不超过 JOBS）。
#
# 用法：
#   bash pipeline/label/run_annotators.sh <数据目录> <标注者,逗号分隔> [并发数，默认 5]
#   例：bash pipeline/label/run_annotators.sh data/double codex,grok 5   # 双标样本
#       bash pipeline/label/run_annotators.sh data/full codex 5          # 全量主标注
# 环境变量：CODEX_BIN（默认 codex）、GROK_BIN（默认 grok）
#           GENE：只重标这一个基因（使用 annotate-gene-brief.md，输出到 <标注者>-<基因>/）
# 已完成且校验通过的分块会跳过，中断后重跑即可续上。
set -euo pipefail
cd "$(dirname "$0")/../.."
DIR="$1"; WHO="$2"; JOBS="${3:-5}"
export DIR CODEX_BIN="${CODEX_BIN:-codex}" GROK_BIN="${GROK_BIN:-grok}" GENE="${GENE:-}"
mkdir -p "$DIR/logs" "$DIR/briefs"

run_one() {
  local who="$1" in="$2"
  local n; n=$(basename "$in" .jsonl)
  local tag="$who${GENE:+-$GENE}" tpl="pipeline/label/annotate-brief.md"
  [ -n "$GENE" ] && tpl="pipeline/label/annotate-gene-brief.md"
  local out="$DIR/$tag/$n.jsonl" brief="$DIR/briefs/$tag-$n.md" log="$DIR/logs/$tag-$n.log"
  mkdir -p "$DIR/$tag"
  if [ -s "$out" ] && python3 -I pipeline/label/check_labels.py "$in" "$out" $GENE >/dev/null 2>&1; then
    echo "跳过 ${who} ${n}（已完成且校验通过）"; return 0
  fi
  sed -e "s#{IN}#$in#g" -e "s#{OUT}#$out#g" -e "s#{GENE}#$GENE#g" "$tpl" > "$brief"
  local start; start=$(date +%s)
  if [ "$who" = codex ]; then
    "$CODEX_BIN" exec -C "$PWD" -s workspace-write -o "$DIR/logs/$tag-$n.final.md" - < "$brief" > "$log" 2>&1 || true
  else
    "$GROK_BIN" -p "$(cat "$brief")" --always-approve --cwd "$PWD" --disable-web-search > "$log" 2>&1 || true
  fi
  local verdict="没能判定（未生成输出）"
  if [ -s "$out" ]; then
    verdict=$(python3 -I pipeline/label/check_labels.py "$in" "$out" $GENE 2>&1 | head -1 || true)
  fi
  echo "${tag} ${n} 用时 $(( $(date +%s) - start ))s：${verdict}"
}
export -f run_one

for in in "$DIR"/chunks/*.jsonl; do
  for who in ${WHO//,/ }; do echo "$who $in"; done
done | xargs -P "$JOBS" -L 1 bash -c 'run_one "$0" "$1"'
