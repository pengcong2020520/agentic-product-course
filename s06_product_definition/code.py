#!/usr/bin/env python3
"""
s06_product_definition - 从标签到产品定义

标签 → 基因分布与人群切片 → 机会地图（规模·痛感·可解，三组权重）→ 证据回读（人工）→ 产品定义

本脚本生成前三步的报告，只含统计数字；证据回读与定义写作由人完成。

Usage:
    python s06_product_definition/code.py genome-report --src data/labeled/genome-final.jsonl
    python s06_product_definition/code.py segment-report --src data/labeled/genome-final.jsonl
    python s06_product_definition/code.py opportunities --min-n 15 --w1 1 --w2 1 --w3 1
"""


import argparse
from collections import Counter, defaultdict
import json
import math
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


OPPORTUNITY_SEGMENTS = ("陪伴向", "剧情玩家", "创作向", "进阶玩家", "其他/不明")


def opportunity_segments(labels):
    users = values(labels, "g1_user")
    motives = values(labels, "g2_motive")
    result = set()
    if users & {"dream_partner", "confider"} or motives & {
        "companionship", "emotional_support", "romance"
    }:
        result.add("陪伴向")
    if "story_player" in users:
        result.add("剧情玩家")
    if "creator" in users or "creation" in motives:
        result.add("创作向")
    if "power_user" in users:
        result.add("进阶玩家")
    return result or {"其他/不明"}


def opportunity_metrics(key, labels):
    n = len(labels)
    intensities = [label["g8_intensity"] for label in labels
                   if label.get("g8_intensity") is not None]
    segments = Counter(segment for label in labels for segment in opportunity_segments(label))

    def share(gid, accepted):
        return sum(label.get(gid) in accepted for label in labels) / n

    result = {
        "candidate": key, "n": n,
        "pain": share("g16_severity", ("p0", "p1")),
        "intensity": sum(intensities) / len(intensities) if intensities else None,
        "intensity_n": len(intensities),
        "churn": share("g10_stage", ("churning",)),
        "regress": share("g10_stage", ("veteran",)),
        "agent_share": share("g15_solvable", ("agent", "mixed")),
        "platform_share": share("g15_solvable", ("platform", "mixed")),
        "business_share": share("g15_solvable", ("business",)),
        "paying": share("g4_investment", ("paying",)),
        "segments": {segment: segments[segment] for segment in OPPORTUNITY_SEGMENTS},
    }
    intensity_term = (result["intensity"] - 1) / 2 if intensities else 0
    result["severity"] = (0.5 * result["pain"] + 0.2 * intensity_term
                          + 0.15 * result["churn"] + 0.15 * result["regress"])
    result["solvable"] = max(result["agent_share"], result["platform_share"])
    return result


def rank_opportunities(groups, min_n, weights):
    rows = [opportunity_metrics(key, labels) for key, labels in groups.items()
            if len(labels) >= min_n]
    max_n = max((row["n"] for row in rows), default=0)
    for row in rows:
        row["size"] = math.log1p(row["n"]) / math.log1p(max_n)
        row["scores"] = {
            variant: row["size"] ** w1 * row["severity"] ** w2 * row["solvable"] ** w3
            for variant, (w1, w2, w3) in weights.items()
        }
        row["score"] = row["scores"]["default"]
        row["ranks"] = {}
    for variant in weights:
        ordered = sorted(rows, key=lambda row: (-row["scores"][variant], row["candidate"]))
        for rank, row in enumerate(ordered, 1):
            row["ranks"][variant] = rank
    rows.sort(key=lambda row: row["ranks"]["default"])
    for row in rows:
        row["stable"] = all(rank <= 10 for rank in row["ranks"].values())
    return {
        "candidate_count": len(groups), "filtered_count": len(groups) - len(rows),
        "retained_count": len(rows), "max_n": max_n, "rows": rows,
        "stable_opportunities": [row["candidate"] for row in rows if row["stable"]],
    }


def build_opportunity_map(rows, theme_rows, min_n=15, weights=(1, 1, 1)):
    """只聚合标签；评论、句子、样本标识和其他元数据不进入输出结构。"""
    if min_n < 1:
        raise ValueError("min-n 必须至少为 1")
    if len(weights) != 3 or any(not math.isfinite(w) or w < 0 for w in weights):
        raise ValueError("权重必须为三个非负有限数")
    variants = {"default": list(weights), "size_light": [0.5, 1, 1],
                "pain_heavy": [1, 1.5, 1]}
    relevant = {row["id"]: row["labels"] for row in rows
                if row["labels"].get("relevant") == "yes"}
    pain_groups = defaultdict(list)
    excluded_other = set()
    for labels in relevant.values():
        for key in values(labels, "g6_subtouch"):
            if key.endswith(".other"):
                excluded_other.add(key)
            else:
                pain_groups[key].append(labels)
    themes_by_id = defaultdict(set)
    for row in theme_rows:
        if row["id"] in relevant:
            themes_by_id[row["id"]].update(
                theme for theme in as_list(row.get("themes"))
                if isinstance(theme, str) and theme
            )
    behavior_groups = defaultdict(list)
    for sample_id, themes in themes_by_id.items():
        for theme in themes:
            behavior_groups[theme].append(relevant[sample_id])
    return {
        "relevant_n": len(relevant), "min_n": min_n, "weights": variants,
        "method": {
            "denominator": "各候选命中样本数；同一样本同一候选只计一次",
            "candidates": "相关样本中实际命中的候选；痛点限基因枚举且排除 .other",
            "pain": "g16_severity 为 p0 或 p1 的占比",
            "churn / regress": "g10_stage 分别为 churning / veteran 的占比",
            "agent_share / platform_share / business_share":
                "g15_solvable 分别为 agent 或 mixed / platform 或 mixed / business 的占比",
            "paying": "g4_investment 为 paying 的占比",
            "size": "log(1+n)/log(1+max_n)，各表过滤后独立归一",
            "severity": "0.5*pain+0.2*(intensity-1)/2+0.15*churn+0.15*regress",
            "solvable": "max(agent_share, platform_share)",
            "score": "size^w1 * severity^w2 * solvable^w3；权重 0 表示忽略该项",
            "intensity": "缺失不计；全部缺失时均值为 null，强度项贡献为 0",
            "segments": "切片可重叠；未命中前四类的样本计入其他/不明",
            "陪伴向": "g1 含 dream_partner/confider，或 g2 含 companionship/emotional_support/romance",
            "剧情玩家 / 创作向 / 进阶玩家":
                "g1 含 story_player / g1 含 creator 或 g2 含 creation / g1 含 power_user",
            "ranking": "各表过滤后按分数降序，同分按候选键升序；三组均前 10 为稳定机会",
        },
        "pain": {**rank_opportunities(pain_groups, min_n, variants),
                 "excluded_other_count": len(excluded_other)},
        "behavior": rank_opportunities(behavior_groups, min_n, variants),
    }


def render_opportunity_map(report):
    def cell(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
            ">", "&gt;"
        ).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")

    out = ["# 机会地图", "", f"- 相关样本：{report['relevant_n']}；min-n：{report['min_n']}。"]
    out.extend(f"- {key}：{value}。" for key, value in report["method"].items())
    out.extend(f"- 权重 {key} (w1,w2,w3)：{tuple(weights)}。"
               for key, weights in report["weights"].items())
    out.append("- 人群顺序：陪伴向 / 剧情玩家 / 创作向 / 进阶玩家 / 其他/不明（命中样本数）。")
    headings = (("pain", "A. 痛点机会"), ("behavior", "B. 行为机会"))
    columns = ["候选", "n", "pain", "intensity", "intensity_n", "churn", "regress",
               "agent_share", "platform_share", "business_share", "paying", "size",
               "severity", "solvable", "score", "名次 default", "名次 size_light",
               "名次 pain_heavy", "人群分布", "稳定"]
    for key, title in headings:
        table_data = report[key]
        out += ["", f"## {title}", "",
                f"候选 {table_data['candidate_count']} 个；min-n 过滤 {table_data['filtered_count']} 个；"
                f"保留 {table_data['retained_count']} 个；max_n = {table_data['max_n']}。"]
        if key == "pain":
            out.append(f"另排除 .other 候选 {table_data['excluded_other_count']} 个。")
        out += ["", "| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
        for row in table_data["rows"]:
            cells = [cell(row["candidate"]), str(row["n"]), f"{row['pain']:.2%}",
                     f"{row['intensity']:.4f}" if row["intensity"] is not None else "—",
                     str(row["intensity_n"])]
            cells += [f"{row[field]:.2%}" for field in (
                "churn", "regress", "agent_share", "platform_share", "business_share", "paying"
            )]
            cells += [f"{row[field]:.6f}" for field in ("size", "severity", "solvable", "score")]
            cells += [str(row["ranks"][variant]) for variant in report["weights"]]
            cells += [" / ".join(str(row["segments"][segment]) for segment in OPPORTUNITY_SEGMENTS),
                      "是" if row["stable"] else "否"]
            out.append("| " + " | ".join(cells) + " |")
    out += ["", "## 稳定机会", ""]
    for key, title in headings:
        out.append(f"### {title}")
        out.append("")
        for candidate in report[key]["stable_opportunities"]:
            out.append(f"- {cell(candidate)}")
        if not report[key]["stable_opportunities"]:
            out.append("无。")
        out.append("")
    return "\n".join(out)


def opportunities(args, ap):
    def read_rows(path):
        with Path(path).open(encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]

    weights = (args.w1, args.w2, args.w3)
    if args.min_n < 1 or any(not math.isfinite(w) or w < 0 for w in weights):
        ap.error("min-n 必须至少为 1；权重必须为非负有限数")
    report = build_opportunity_map(read_rows(args.src), read_rows(args.themes), args.min_n, weights)
    for destination, content in (
        (args.out, render_opportunity_map(report)),
        (args.json, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"),
    ):
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"机会地图已生成（相关样本 {report['relevant_n']} 条；"
          f"痛点过滤 {report['pain']['filtered_count']} 个；行为过滤 {report['behavior']['filtered_count']} 个）")


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
    ap = commands.add_parser("opportunities", help="从痛点标签与行为主题生成机会地图")
    ap.add_argument("--src", default="data/labeled/genome-final.jsonl")
    ap.add_argument("--themes", default="data/labeled/agent-themes.jsonl")
    ap.add_argument("--out", default="data/reports/opportunity-map.md")
    ap.add_argument("--json", default="data/reports/opportunity-map.json")
    ap.add_argument("--min-n", type=int, default=15)
    ap.add_argument("--w1", type=float, default=1, help="主排序的规模权重")
    ap.add_argument("--w2", type=float, default=1, help="主排序的痛感权重")
    ap.add_argument("--w3", type=float, default=1, help="主排序的可解权重")
    ap.set_defaults(handler=opportunities, command_parser=ap)
    args = parser.parse_args()
    args.handler(args, args.command_parser)


if __name__ == "__main__":
    main()
