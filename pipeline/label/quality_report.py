"""按标注协议第 6 节生成质量统计；不输出评论、自由文本标注或裁决原值。

用法：python pipeline/label/quality_report.py --agreement data/double/report/agreement.json
"""
import argparse
import json
from itertools import combinations
from pathlib import Path

from check_labels import GENOME


def verdict(kappa):
    if kappa is None:
        return "没能判定"
    if kappa >= 0.6:
        return "合格"
    if kappa >= 0.4:
        return "需修订定义"
    return "需重写定义"


def cell(value):
    """保持元数据在单个 Markdown 表格单元格内。"""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def review_counts(path):
    pending = decided = changed = 0
    with Path(path).open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            review = record.get("review") or {}
            if review.get("decided"):
                decided += 1
                # 一条样本即使多个基因改变，也只计一次。
                changed += any(record["labels"].get(gene) != before
                               for gene, before in review.get("before", {}).items())
            elif record.get("needs_review"):
                pending += 1
    return pending, decided, changed


def render_report(agreement, final_path):
    names = agreement["annotators"]
    pairs = [f"{a}-{b}" for a, b in combinations(names, 2)]
    lines = [
        "# 标注质量报告", "", "## 样本与没能判定数量", "",
        "| 指标 | 数量 |", "|---|---:|",
        f"| sample | {agreement['sample']} |",
        f"| usable | {agreement['usable']} |",
        f"| both_relevant | {agreement['both_relevant']} |", "",
        "| 标注者 | 没能判定数量 |", "|---|---:|",
    ]
    for name in names:
        lines.append(f"| {cell(name)} | {agreement['undetermined'][name]} |")
    lines.extend(["", "## 已应用的 patches", ""])
    patches = agreement.get("patches", [])
    lines.append(f"补丁数量：{len(patches)}。")
    if patches:
        lines.extend(["", "| 标注者 | 基因 | 路径 | 覆盖条数 |", "|---|---|---|---:|"])
        for patch in patches:
            lines.append("| " + " | ".join(cell(patch[key]) for key in
                         ("annotator", "gene", "path", "applied")) + " |")
    lines.extend([
        "", "## 各基因一致性", "",
        "判定阈值：κ ≥ 0.6 合格；0.4 ≤ κ < 0.6 需修订定义；κ < 0.4 需重写定义；无法计算为没能判定。",
        "单选列两两 κ，多选列平均标签 κ，强度列加权 κ；多方逐对判定。文本基因只统计“Agent 应当”条数。", "",
        "| 基因 | 比较方 / 标注者 | 指标 | 数值 | 判定 |", "|---|---|---|---:|---|",
    ])
    for gene in GENOME["genes"]:
        gid, kind = gene["id"], gene["type"]
        stats = agreement.get("genes", {}).get(gid, {})
        if kind == "text":
            for name in names:
                count = stats.get("agent_expectation_count", {}).get(name)
                lines.append(f"| {gid} | {cell(name)} | Agent 应当条数 | "
                             f"{count if count is not None else '—'} | "
                             f"{'不计算 κ' if count is not None else '没能判定'} |")
            continue
        metric = {"single": "两两 κ", "multi": "平均标签 κ", "rating": "加权 κ"}[kind]
        for pair in pairs or ["—"]:
            if kind == "multi":
                kappa = stats.get("pairwise", {}).get(pair, {}).get("mean_label_kappa")
            else:
                kappa = stats.get("pairwise_kappa", {}).get(pair)
            value = "—" if kappa is None else f"{kappa:.3f}"
            lines.append(f"| {gid} | {cell(pair)} | {metric} | {value} | {verdict(kappa)} |")
    pending, decided, changed = review_counts(final_path)
    ratio = f"{changed / decided:.1%}" if decided else "没能判定（已裁决为 0）"
    lines.extend([
        "", "## 裁决统计", "",
        f"- 待裁决：{pending} 条。", f"- 已裁决：{decided} 条。",
        f"- 裁决改动主标注：{changed} 条。", f"- 裁决改动比例：{ratio}（{changed}/{decided}）。", "",
        "待裁决指 needs_review 非空且 review.decided 未为真；已裁决以 review.decided 为准。",
        "改动指 review.before 中至少一个基因与当前 labels 不同，每条样本计一次；比例分母为已裁决条数。", "",
        "## 质量结论口径", "",
        "双标样本的一致性用于衡量主标注可信度。κ 合格的基因可用于全量主标注统计；不合格的基因须人工复核后使用。",
        "没能判定不视为合格；文本基因仍需人工抽查。", "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agreement", default="data/double/report/agreement.json")
    parser.add_argument("--final", default="data/labeled/genome-final.jsonl")
    parser.add_argument("--out", default="data/reports/quality-report.md")
    args = parser.parse_args()
    agreement = json.loads(Path(args.agreement).read_text(encoding="utf-8"))
    report = render_report(agreement, args.final)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print("质量报告已生成。")


if __name__ == "__main__":
    main()
