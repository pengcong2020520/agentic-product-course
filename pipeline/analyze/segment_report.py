"""按用户画像生成统计报告；不输出样本标识、评论原文或 G13 文本。"""

import argparse
from collections import Counter
import json
from pathlib import Path


GENOME = json.loads(
    (Path(__file__).resolve().parents[1] / "label/genome.json").read_text(encoding="utf-8")
)
GENES = {gene["id"]: gene for gene in GENOME["genes"]}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default="data/labeled/genome-final.jsonl")
    parser.add_argument("--out", default="data/reports/segment-report.md")
    args = parser.parse_args()
    with Path(args.src).open(encoding="utf-8") as source:
        relevant, segments = summarize(json.loads(line) for line in source if line.strip())
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(relevant, segments), encoding="utf-8")
    print(f"报告已生成（相关样本 {relevant} 条，切片 {len(segments)} 个）")


if __name__ == "__main__":
    main()
