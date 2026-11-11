#!/usr/bin/env python3
"""
s06_product_definition - 从标签到产品定义

从最终标注生成基因分布与用户画像切片报告，作为产品定义的输入。

Usage:
    python s06_product_definition/code.py genome-report --src data/labeled/genome-final.jsonl
    python s06_product_definition/code.py segment-report --src data/labeled/genome-final.jsonl
"""


import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


GENOME = json.loads((Path(__file__).resolve().parents[1] / "s03_product_genome/genome.json").read_text(encoding="utf-8"))


GENES = {g["id"]: g for g in GENOME["genes"]}


def genome_name(gid, v):
    vals = GENES[gid]["values"]
    return f"{vals.get(v, v)}（`{v}`）" if isinstance(vals, dict) else str(v)


def as_list(v):
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def table(counter, total, gid, top=None):
    rows = ["| 取值 | 条数 | 占比 |", "|---|---|---|"]
    for v, n in counter.most_common(top):
        rows.append(f"| {genome_name(gid, v)} | {n} | {n / total:.1%} |")
    return "\n".join(rows)


def genome_report(args, ap):

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
        out.append(f"| {genome_name('g5_touchpoint', t)} | " + " | ".join(str(cnt[s]) for s in sev) + f" | {sum(cnt.values())} |")
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
        out.append(f"| {genome_name('g15_solvable', k)} | " + " | ".join(str(cnt[s]) for s in sev) + " |")
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


REPORT_GENES = (
    "g5_touchpoint", "g6_subtouch", "g11_value", "g14_capability",
    "g16_severity", "g10_stage",
)


SEGMENTS = {
    value: f"{title}（`{value}`）"
    for value, title in GENES["g1_user"]["values"].items()
    if value != "unknown"
}


SEGMENTS.update({"陪伴向": "陪伴向", "创作向": "创作向"})


def values(labels, gid):
    """只保留规范中的枚举值，且一条样本的同一取值只计一次。"""
    raw = labels.get(gid)
    raw = raw if isinstance(raw, list) else [raw]
    return {value for value in raw
            if isinstance(value, str) and value in GENES[gid]["values"]}


def summarize(rows):
    """累计相关样本；切片之间可重叠，合并切片按并集计数。"""
    segments = {
        key: {"count": 0, "agent": 0, "p0_p1": 0,
              "genes": {gid: Counter() for gid in REPORT_GENES}}
        for key in SEGMENTS
    }
    relevant = 0
    for row in rows:
        labels = row["labels"]
        if labels.get("relevant") != "yes":
            continue
        relevant += 1
        users = values(labels, "g1_user")
        motives = values(labels, "g2_motive")
        memberships = users.intersection(SEGMENTS)
        if users.intersection({"dream_partner", "confider"}) or motives.intersection(
            {"companionship", "emotional_support", "romance"}
        ):
            memberships.add("陪伴向")
        if "creator" in users or "creation" in motives:
            memberships.add("创作向")
        expected = labels.get("g13_expected")
        agent = isinstance(expected, str) and "Agent 应当" in expected
        severe = labels.get("g16_severity") in ("p0", "p1")
        counts = {gid: values(labels, gid) for gid in REPORT_GENES}
        for key in memberships:
            segment = segments[key]
            segment["count"] += 1
            segment["agent"] += agent
            segment["p0_p1"] += severe
            for gid, entries in counts.items():
                segment["genes"][gid].update(entries)
    return relevant, segments


def percent(count, total):
    return f"{count / total if total else 0:.1%}"


def top_values(counter, limit):
    # 同频时按枚举键排序，使输出不受样本顺序或集合迭代顺序影响。
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]


def name(gid, value):
    return f"{GENES[gid]['values'][value]}（`{value}`）"


def render_report(relevant, segments):
    out = [
        f"# Agentic 产品基因图谱 · 人群切片报告（规范 v{GENOME['version']}）", "",
        f"- 相关样本：{relevant} 条（仅统计 relevant = yes）。",
        "- 切片样本占比以相关样本数为分母；基因取值、P0+P1 和“Agent 应当”占比以切片样本数为分母。",
        "- 切片可重叠；多选基因每条样本的每个取值只计一次，占比之和可超过 100%。",
        "- 陪伴向：画像含 dream_partner / confider，或动机含 companionship / emotional_support / romance。",
        "- 创作向：画像含 creator，或动机含 creation。unknown 不单独成片，仍可按动机进入合并切片。",
        "- 取值按条数降序，同频按枚举键排序；空切片比例显示为 0.0%。", "",
    ]
    for key, title in SEGMENTS.items():
        segment = segments[key]
        total = segment["count"]
        out += [
            f"## {title}", "",
            f"- 样本数：{total} 条；占相关样本：{percent(total, relevant)}。",
            f"- 写了“Agent 应当”：{segment['agent']} 条（{percent(segment['agent'], total)}）。",
            f"- P0+P1：{segment['p0_p1']} 条（{percent(segment['p0_p1'], total)}）。", "",
        ]
        for gid in REPORT_GENES:
            out += [f"### {GENES[gid]['title']}（前 8）", "",
                    "| 取值 | 条数 | 占比 |", "|---|---|---|"]
            for value, count in top_values(segment["genes"][gid], 8):
                out.append(f"| {name(gid, value)} | {count} | {percent(count, total)} |")
            out.append("")

    out += ["## 切片对比", "",
            "| 切片 | 样本数 | P0+P1 比例 | “Agent 应当”比例 | 前三触点 | 前三情感价值 |",
            "|---|---|---|---|---|---|"]
    for key, title in SEGMENTS.items():
        segment = segments[key]
        total = segment["count"]
        tops = []
        for gid in ("g5_touchpoint", "g11_value"):
            tops.append("、".join(
                f"{name(gid, value)}：{count}（{percent(count, total)}）"
                for value, count in top_values(segment["genes"][gid], 3)
            ) or "—")
        out.append(
            f"| {title} | {total} | {percent(segment['p0_p1'], total)} | "
            f"{percent(segment['agent'], total)} | {tops[0]} | {tops[1]} |"
        )
    return "\n".join(out) + "\n"


def segment_report(args, ap):
    with Path(args.src).open(encoding="utf-8") as source:
        relevant, segments = summarize(json.loads(line) for line in source if line.strip())
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(relevant, segments), encoding="utf-8")
    print(f"报告已生成（相关样本 {relevant} 条，切片 {len(segments)} 个）")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ap = commands.add_parser("genome-report")
    ap.add_argument("--src", default="data/labeled/genome-final.jsonl")
    ap.add_argument("--out", default="data/reports/genome-report.md")
    ap.set_defaults(handler=genome_report, command_parser=ap)
    ap = commands.add_parser("segment-report")
    ap.add_argument("--src", default="data/labeled/genome-final.jsonl")
    ap.add_argument("--out", default="data/reports/segment-report.md")
    ap.set_defaults(handler=segment_report, command_parser=ap)
    args = parser.parse_args()
    args.handler(args, args.command_parser)


if __name__ == "__main__":
    main()
