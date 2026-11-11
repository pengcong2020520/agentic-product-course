"""基因分布报告：从最终标注统计每个基因的分布与关键交叉，作为"从标签到产品定义"的输入。

只输出统计数字与样本 id，不输出评论原文（原文只在本地数据里）。

用法：python pipeline/analyze/genome_report.py [--src data/labeled/genome-final.jsonl] [--out data/reports/genome-report.md]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "label"))
from check_labels import GENOME  # noqa: E402

GENES = {g["id"]: g for g in GENOME["genes"]}


def name(gid, v):
    vals = GENES[gid]["values"]
    return f"{vals.get(v, v)}（`{v}`）" if isinstance(vals, dict) else str(v)


def as_list(v):
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def table(counter, total, gid, top=None):
    rows = ["| 取值 | 条数 | 占比 |", "|---|---|---|"]
    for v, n in counter.most_common(top):
        rows.append(f"| {name(gid, v)} | {n} | {n / total:.1%} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/labeled/genome-final.jsonl")
    ap.add_argument("--out", default="data/reports/genome-report.md")
    args = ap.parse_args()

    allrows = [json.loads(l) for l in open(args.src, encoding="utf-8")]
    rows = [r for r in allrows if r["labels"].get("relevant") == "yes"]
    n = len(rows)
    annotator = allrows[0]["annotator"] if allrows else "无已标注样本"
    out = [f"# Agentic 产品基因图谱 · 分布报告（规范 v{GENOME['version']}）", "",
           f"- 样本：{len(allrows)} 条已标注，其中与陪伴产品相关 {n} 条，不相关 {len(allrows) - n} 条",
           f"- 标注：{annotator}（主标注），双标样本 {sum(r['in_double_sample'] for r in allrows)} 条",
           f"- 待人工裁决：{sum(bool(r['needs_review']) for r in allrows)} 条；已裁决：{sum(bool(r.get('review')) for r in allrows)} 条",
           "- 以下占比的分母为相关样本数；多选基因一条样本可计入多个取值，占比之和可超过 100%。", ""]

    out.append("## 一、人：谁在说、为什么用\n")
    for gid in ("g1_user", "g2_motive", "g3_relation", "g4_investment"):
        c = Counter(x for r in rows for x in as_list(r["labels"].get(gid)))
        out += [f"### {GENES[gid]['title']}", table(c, n, gid), ""]

    out.append("## 二、事：发生了什么\n")
    for gid in ("g5_touchpoint", "g7_trigger", "g8_emotion", "g9_voice_type", "g10_stage", "g11_value", "g12_competitor"):
        c = Counter(x for r in rows for x in as_list(r["labels"].get(gid)))
        out += [f"### {GENES[gid]['title']}", table(c, n, gid), ""]
    c = Counter(x for r in rows for x in as_list(r["labels"].get("g6_subtouch")))
    out += ["### G6 体验触点·二级（前 25）", table(c, n, "g6_subtouch", 25), ""]

    out.append("## 三、解：产品该怎么回应\n")
    for gid in ("g14_capability", "g15_solvable", "g16_severity", "g17_risk"):
        c = Counter(x for r in rows for x in as_list(r["labels"].get(gid)))
        out += [f"### {GENES[gid]['title']}", table(c, n, gid), ""]
    agent = [r for r in rows if "Agent 应当" in (r["labels"].get("g13_expected") or "")]
    product = [r for r in rows if "产品应当" in (r["labels"].get("g13_expected") or "")]
    out += ["### G13 期望行为", f"- 写了“Agent 应当”（评测集种子）：{len(agent)} 条（{len(agent) / n if n else 0:.1%}）",
            f"- 写了“产品应当”（需求池）：{len(product)} 条（{len(product) / n if n else 0:.1%}）", ""]

    out.append("## 四、关键交叉\n")
    out.append("### 一级触点 × 严重度（条数）")
    sev = ["p0", "p1", "p2", "none"]
    cross = defaultdict(Counter)
    for r in rows:
        for t in as_list(r["labels"].get("g5_touchpoint")):
            cross[t][r["labels"].get("g16_severity")] += 1
    out += ["| 触点 | P0 | P1 | P2 | 无问题 | 合计 |", "|---|---|---|---|---|---|"]
    for t, cnt in sorted(cross.items(), key=lambda kv: -sum(kv[1].values())):
        out.append(f"| {name('g5_touchpoint', t)} | " + " | ".join(str(cnt[s]) for s in sev) + f" | {sum(cnt.values())} |")
    out.append("")

    out.append("### 能力归属 × “Agent 应当”（评测集种子落在哪些能力上）")
    cap = Counter(x for r in agent for x in as_list(r["labels"].get("g14_capability")))
    out += [table(cap, max(1, len(agent)), "g14_capability"), ""]

    out.append("### 可解性 × 严重度（条数）")
    cross = defaultdict(Counter)
    for r in rows:
        cross[r["labels"].get("g15_solvable")][r["labels"].get("g16_severity")] += 1
    out += ["| 可解性 | P0 | P1 | P2 | 无问题 |", "|---|---|---|---|---|"]
    for k, cnt in cross.items():
        out.append(f"| {name('g15_solvable', k)} | " + " | ".join(str(cnt[s]) for s in sev) + " |")
    out.append("")

    out.append("### 各应用：主要触点（前 3）与 P0/P1 占比")
    by_app = defaultdict(list)
    for r in rows:
        by_app[r["app"]].append(r)
    out += ["| 应用 | 相关样本 | 主要触点 | P0+P1 占比 |", "|---|---|---|---|"]
    for app, rs in sorted(by_app.items(), key=lambda kv: -len(kv[1])):
        top = Counter(x for r in rs for x in as_list(r["labels"].get("g5_touchpoint"))).most_common(3)
        bad = sum(r["labels"].get("g16_severity") in ("p0", "p1") for r in rs)
        out.append(f"| {app} | {len(rs)} | " + "、".join(GENES["g5_touchpoint"]["values"].get(t, t) for t, _ in top)
                   + f" | {bad / len(rs):.0%} |")
    out.append("")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"报告已写入 {args.out}（相关样本 {n} 条）")


if __name__ == "__main__":
    main()
