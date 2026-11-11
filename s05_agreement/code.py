#!/usr/bin/env python3
"""
s05_agreement - 一致性与人工裁决

计算一致性、应用单基因补丁，并通过 Argilla 完成人工裁决与质量统计。
环境变量：ARGILLA_API_URL（默认 http://localhost:6900）、ARGILLA_API_KEY。

Usage:
    python s05_agreement/code.py agree --ann codex=data/double/codex --ann grok=data/double/grok
    python s05_agreement/code.py review push
    python s05_agreement/code.py review pull
    python s05_agreement/code.py quality
    python s05_agreement/code.py import --limit 200
"""


import argparse
from collections import Counter
from copy import deepcopy
from itertools import combinations
import json
import os
from pathlib import Path


GENOME = json.loads((Path(__file__).resolve().parents[1] / "s03_product_genome/genome.json").read_text(encoding="utf-8"))


GENES = {g["id"]: g for g in GENOME["genes"]}


def check(raw, only=None):
    bad = []
    for g in GENOME["genes"]:
        if only and g["id"] not in only:
            continue
        v, t = raw.get(g["id"]), g["type"]
        if not only and raw.get("relevant") == "off_topic" and g["id"] != "relevant":
            continue
        if t in ("single", "rating"):
            ok = v in g["values"]
        elif t == "multi":
            ok = isinstance(v, list) and all(x in g["values"] for x in v) \
                 and bool(v or g.get("optional")) and len(v) <= g.get("max", 99)
            if ok and g.get("parent") and not only:
                ok = all(x.split(".")[0] in (raw.get(g["parent"]) or []) for x in v)
        else:
            ok = isinstance(v, str)
        if not ok:
            bad.append(f"{g['id']}={v!r}")
    return bad

def check_file(src, out, only=None):
    ids = [json.loads(l)["id"] for l in open(src, encoding="utf-8")]
    rows = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
    errors = []
    if sorted(r.get("id") for r in rows) != sorted(ids):
        errors.append(f"id 不对应：输入 {len(ids)} 条，输出 {len(rows)} 条")
    for r in rows:
        bad = check(r, only)
        if bad:
            errors.append(f"{r.get('id')}: " + ", ".join(bad))
    return errors


def load(path, validate=True):
    p = Path(path)
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    out = {}
    for f in files:
        with f.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                d = json.loads(line)
                labels = d.get("labels", d)  # prelabel 输出包在 labels 里，复标直接是字段
                if validate and check(labels):  # 不合法：整条记为没能判定
                    out[d["id"]] = None
                else:
                    out[d["id"]] = labels
    return out


def apply_patch(annotations, gene, path):
    """按 id 叠加一个基因；同一补丁内重复 id 取最后一条，每个 id 只计一次。"""
    replacements = load(path, validate=False)
    if any(gene not in labels for labels in replacements.values()):
        raise ValueError("补丁记录缺少指定基因字段")
    applied = 0
    for rid, replacement in replacements.items():
        labels = annotations.get(rid)
        if labels is not None and labels.get("relevant") != "off_topic":
            labels[gene] = replacement[gene]
            applied += 1
    return applied


def cohen(a, b):
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def fleiss(rows, cats):
    n, m = len(rows), len(rows[0]) if rows else 0
    if n == 0 or m < 2:
        return None
    p_j = {c: sum(r.count(c) for r in rows) / (n * m) for c in cats}
    P_i = [(sum(r.count(c) ** 2 for c in cats) - m) / (m * (m - 1)) for r in rows]
    pe = sum(v * v for v in p_j.values())
    return 1.0 if pe == 1 else (sum(P_i) / n - pe) / (1 - pe)


def weighted(a, b, k=3):
    n = len(a)
    if n == 0:
        return None
    w = lambda x, y: 1 - abs(x - y) / (k - 1)
    po = sum(w(x, y) for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[x] * cb[y] * w(x, y) for x in ca for y in cb) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def jaccard(x, y):
    x, y = set(x or []), set(y or [])
    return 1.0 if not x and not y else len(x & y) / len(x | y)  # 两方都为空算一致


def r3(x):
    return None if x is None else round(x, 3)


def agree(args, ap):

    ann = {}
    for spec in args.ann:
        name, path = spec.split("=", 1)
        ann[name] = load(path, validate=False)
    patches = []
    for spec in args.patch:
        try:
            target, path = spec.split("=", 1)
            name, gene = target.split(":", 1)
        except ValueError:
            ap.error("--patch 格式应为 名字:基因=路径")
        if name not in ann or gene not in GENES or not path:
            ap.error("--patch 必须指定已提供的标注者、有效基因与非空路径")
        try:
            applied = apply_patch(ann[name], gene, path)
        except (ValueError, KeyError, TypeError):
            ap.error("补丁必须是包含 id 和指定基因字段的合法 JSONL")
        patches.append({"annotator": name, "gene": gene, "path": path, "applied": applied})
    # 所有补丁叠加后再校验，允许重标修复原先不合法的基因。
    for annotations in ann.values():
        for rid, labels in annotations.items():
            if check(labels):
                annotations[rid] = None
    names = list(ann)
    sample = set.intersection(*(set(v) for v in ann.values() if v)) if all(ann.values()) else set()
    # 只统计三方都有记录的样本；任一方不合法 → 该样本没能判定
    ids = sorted(i for i in sample if all(ann[n][i] is not None for n in names))
    undetermined = {n: sum(ann[n].get(i) is None for i in sample) for n in names}
    rel = [i for i in ids if all(ann[n][i].get("relevant") == "yes" for n in names)]

    report = {"annotators": names, "sample": len(sample), "usable": len(ids), "both_relevant": len(rel),
              "undetermined": undetermined, "genes": {}}
    if args.patch:
        report["patches"] = patches
    for gid, g in GENES.items():
        if g["type"] == "text":
            wrote = {n: sum("Agent 应当" in (ann[n][i].get(gid) or "") for i in rel) for n in names}
            report["genes"][gid] = {"agent_expectation_count": wrote}
            continue
        pool = ids if gid == "relevant" else rel
        if g["type"] in ("single", "rating"):
            cols = {n: [ann[n][i].get(gid) for i in pool] for n in names}
            pair = {f"{a}-{b}": r3(weighted(cols[a], cols[b]) if g["type"] == "rating" else cohen(cols[a], cols[b]))
                    for a, b in combinations(names, 2)}
            three = r3(fleiss([[cols[n][k] for n in names] for k in range(len(pool))], list(g["values"]))) \
                if len(names) >= 3 and g["type"] == "single" else None
            report["genes"][gid] = {"pairwise_kappa": pair, "fleiss_kappa": three}
        else:
            pair = {}
            for a, b in combinations(names, 2):
                ks = []
                for lab in g["values"]:
                    x = [lab in (ann[a][i].get(gid) or []) for i in pool]
                    y = [lab in (ann[b][i].get(gid) or []) for i in pool]
                    if any(x) or any(y):
                        ks.append(cohen(x, y))
                jac = [jaccard(ann[a][i].get(gid), ann[b][i].get(gid)) for i in pool]
                pair[f"{a}-{b}"] = {"mean_label_kappa": r3(sum(ks) / len(ks)) if ks else None,
                                    "mean_jaccard": r3(sum(jac) / len(jac)) if jac else None}
            report["genes"][gid] = {"pairwise": pair}

    # 最终标注取主标注（第一个标注者）；只有关键基因分歧进入人工裁决（规则见 s05_agreement/protocol.md 第 5 节）
    main_name = names[0]
    merged = []
    for i in ids:
        main = ann[main_name][i]
        review = []
        if all(ann[n][i].get("relevant") == "yes" for n in names):
            # G5：主次不同但有交集算部分一致，只有完全没有交集才裁决
            sets = [set(ann[n][i].get("g5_touchpoint") or []) for n in names]
            if not set.intersection(*sets):
                review.append("g5_touchpoint")
            # G15："多层共同"与某一层不同属于部分一致，只有两个具体层不同才裁决
            vals = {ann[n][i].get("g15_solvable") for n in names}
            if len(vals) > 1 and "mixed" not in vals:
                review.append("g15_solvable")
            # G16：严重度决定优先级，任何不一致都裁决
            if len({ann[n][i].get("g16_severity") for n in names}) > 1:
                review.append("g16_severity")
        elif len({ann[n][i].get("relevant") for n in names}) > 1:
            review.append("relevant")
        merged.append({"id": i, "labels": main, "needs_review": review,
                       "raw": {n: ann[n][i] for n in names}})
    report["needs_review"] = sum(bool(m["needs_review"]) for m in merged)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "agreement.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "merged.jsonl").open("w", encoding="utf-8") as f:
        for m in merged:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("sample", "usable", "both_relevant", "undetermined", "needs_review")},
                     ensure_ascii=False))


REVIEW_GENES = ["relevant", "g5_touchpoint", "g15_solvable", "g16_severity"]


NAME = f"genome-review-v{GENOME['version']}"


def client():
    import argilla as rg

    return rg.Argilla(api_url=os.environ.get("ARGILLA_API_URL", "http://localhost:6900"),
                      api_key=os.environ["ARGILLA_API_KEY"])


def show(v, gid):
    names = GENES[gid]["values"]
    if isinstance(v, list):
        return "、".join(names.get(x, x) for x in v) or "（空）"
    return names.get(v, str(v)) if isinstance(names, dict) else str(v)


def push(args):
    import argilla as rg

    merged = [m for m in map(json.loads, open(args.merged, encoding="utf-8")) if m["needs_review"]]
    c = client()
    ds = c.datasets(NAME)
    if ds is None:
        g = lambda gid, **kw: (rg.MultiLabelQuestion if GENES[gid]["type"] == "multi" else rg.LabelQuestion)(
            name=gid, title=GENES[gid]["title"], labels=GENES[gid]["values"], **kw)
        settings = rg.Settings(
            guidelines="双标分歧裁决：先看两位标注者的判断，再按《Agentic 产品基因图谱》规范给出最终答案。"
                       "只需裁决“分歧”里列出的基因；其余基因沿用主标注。",
            fields=[rg.TextField(name="text", title="用户评论"),
                    rg.TextField(name="dispute", title="分歧（Codex vs Grok）", use_markdown=True)],
            questions=[g("relevant", required=True)] + [g(x, required=False) for x in REVIEW_GENES[1:]],
            metadata=[rg.TermsMetadataProperty(name="app", title="应用"),
                      rg.TermsMetadataProperty(name="dispute_genes", title="分歧基因")],
        )
        ds = rg.Dataset(name=NAME, settings=settings, client=c).create()
    src = {r["id"]: r for r in map(json.loads, open(args.src, encoding="utf-8"))}
    records = []
    for m in merged:
        raw = m["raw"]
        rows = "\n".join(f"| {GENES[gid]['title']} | {show(raw['codex'].get(gid), gid)} | {show(raw['grok'].get(gid), gid)} |"
                         for gid in m["needs_review"])
        dispute = "| 基因 | Codex | Grok |\n|---|---|---|\n" + rows
        sugg = [rg.Suggestion(question_name=gid, value=raw["codex"][gid], agent="codex", type="model")
                for gid in REVIEW_GENES if raw["codex"].get(gid) not in (None, [], "")]
        records.append(rg.Record(id=m["id"], fields={"text": src[m["id"]]["text"], "dispute": dispute},
                                 metadata={"app": src[m["id"]]["app"], "dispute_genes": m["needs_review"]},
                                 suggestions=sugg))
    ds.records.log(records)
    print(f"已推送 {len(records)} 条待裁决样本 → Argilla 数据集 {NAME}")


def apply_decision(labels, decision, raw_by_annotator, main="codex"):
    """Apply a review without mutating inputs; retain a trace of dependent repairs."""
    new_labels = deepcopy(labels)
    notes = []
    if decision.get("relevant") == "off_topic":
        new_labels["relevant"] = "off_topic"
        return new_labels, notes

    others = [(name, raw) for name, raw in raw_by_annotator.items() if name != main]
    if labels.get("relevant") == "off_topic" and decision.get("relevant") == "yes":
        if others:
            name, raw = others[0]
            # Raw annotations also contain record metadata (such as id).
            new_labels = deepcopy({k: v for k, v in raw.items() if k in GENES})
            notes.append(f"filled_from={name}")
        # Force full validation even if the other annotator also chose off_topic.
        if not others or check({**new_labels, "relevant": "yes"}):
            notes.append("incomplete")

    new_labels.update(deepcopy(decision))
    if "g5_touchpoint" in decision:
        candidates = list(labels.get("g6_subtouch") or [])
        for _, raw in others:
            candidates.extend(raw.get("g6_subtouch") or [])
        candidates = list(dict.fromkeys(candidates))
        parents = new_labels["g5_touchpoint"] or []
        subtouch = [value for value in candidates if value.split(".", 1)[0] in parents]
        for value in candidates:
            if value not in subtouch:
                notes.append(f"g6_subtouch_removed={value}")
        for parent in parents:
            fallback = f"{parent}.other"
            if (fallback in GENES["g6_subtouch"]["values"]
                    and not any(value.split(".", 1)[0] == parent for value in subtouch)):
                subtouch.append(fallback)
        for value in subtouch:
            if value not in (labels.get("g6_subtouch") or []):
                notes.append(f"g6_subtouch_added={value}")
        new_labels["g6_subtouch"] = subtouch
    return new_labels, notes


def pull(args):
    ds = client().datasets(NAME)
    decisions = {}
    for rec in ds.records(with_responses=True):
        sub = [r for r in rec.responses if r.status == "submitted"] if rec.responses else []
        if not sub:
            continue
        decisions.setdefault(rec.id, {})
        for r in sub:
            decisions[rec.id][r.question_name] = r.value
    out = Path(args.decisions)
    out.write_text("".join(json.dumps({"id": k, "decision": v}, ensure_ascii=False) + "\n"
                           for k, v in decisions.items()), encoding="utf-8")
    with open(args.final, encoding="utf-8") as source:
        final = [json.loads(line) for line in source]
    with open(args.merged, encoding="utf-8") as source:
        raw_by_id = {rec["id"]: rec.get("raw", {}) for rec in map(json.loads, source)}
    covered = changed = invalid = 0
    for rec in final:
        d = decisions.get(rec["id"])
        if not d:
            continue
        before = rec["labels"]
        rec["labels"], notes = apply_decision(before, d, raw_by_id.get(rec["id"], {}))
        overwritten = ["relevant"] if d.get("relevant") == "off_topic" else list(d)
        overwritten.extend(k for k in dict.fromkeys([*before, *rec["labels"]])
                           if k not in overwritten and before.get(k) != rec["labels"].get(k))
        rec["review"] = {"decided": True, "before": {k: before.get(k) for k in overwritten},
                         "notes": notes}
        bad = check(rec["labels"])
        if bad:
            rec["review"]["invalid"] = bad
            invalid += 1
        covered += 1
        changed += before != rec["labels"]
    Path(args.final).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in final), encoding="utf-8")
    print(f"拉回 {len(decisions)} 条裁决；已覆盖条数：{covered}；改动主标注条数：{changed}；"
          f"校验不通过条数：{invalid}；已更新 {args.final}")
    if invalid:
        raise SystemExit(1)


def review(args, ap):
    push(args) if args.action == "push" else pull(args)


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


def quality(args, ap):
    agreement = json.loads(Path(args.agreement).read_text(encoding="utf-8"))
    report = render_report(agreement, args.final)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print("质量报告已生成。")


SPEC_URL = GENOME["spec"]


def question(g):
    import argilla as rg

    common = dict(name=g["id"], title=g["title"], required=g["id"] == "relevant")  # 至少要判断相关性
    if g["type"] == "single":
        return rg.LabelQuestion(labels=g["values"], **common)
    if g["type"] == "multi":
        return rg.MultiLabelQuestion(labels=g["values"], **common)
    if g["type"] == "rating":
        return rg.RatingQuestion(values=g["values"], **common)
    return rg.TextQuestion(**common)


def import_data(args, ap):
    import argilla as rg


    client = rg.Argilla(api_url=os.environ.get("ARGILLA_API_URL", "http://localhost:6900"),
                        api_key=os.environ["ARGILLA_API_KEY"])
    pre = {}
    if Path(args.pre).exists():
        pre = {d["id"]: d for d in map(json.loads, open(args.pre, encoding="utf-8"))}
    rows = [r for r in map(json.loads, open(args.src, encoding="utf-8")) if not r["low_info"]]
    if pre:
        rows = [r for r in rows if r["id"] in pre]
    if args.limit:
        rows = rows[: args.limit]

    dataset = client.datasets(args.name)
    if dataset is None:
        settings = rg.Settings(
            guidelines=f"按《Agentic 产品基因图谱》v{GENOME['version']} 标注（{SPEC_URL}）。看不出来就选“不明”或留空，不猜。",
            fields=[rg.TextField(name="text", title="用户评论")],
            questions=[question(g) for g in GENOME["genes"]],
            metadata=[
                rg.TermsMetadataProperty(name="app", title="应用"),
                rg.IntegerMetadataProperty(name="rating", title="评分", min=1, max=5),
                rg.TermsMetadataProperty(name="undetermined", title="预标没能判定的基因"),
            ],
            distribution=rg.TaskDistribution(min_submitted=1),
        )
        dataset = rg.Dataset(name=args.name, settings=settings, client=client).create()

    records = []
    for r in rows:
        p = pre.get(r["id"], {})
        labels = p.get("labels", {})
        suggestions = [
            rg.Suggestion(question_name=k, value=v, agent=p.get("model"), type="model")
            for k, v in labels.items()
            if v not in (None, "", [])
        ]
        records.append(rg.Record(
            id=r["id"],
            fields={"text": r["text"]},
            metadata={"app": r["app"], "rating": r["rating"], "undetermined": p.get("undetermined") or ["none"]},
            suggestions=suggestions,
        ))
    dataset.records.log(records)
    print(f"已导入 {len(records)} 条 → Argilla 数据集 {args.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ap = commands.add_parser("agree")
    ap.add_argument("--ann", action="append", required=True, help="名字=路径（文件或目录），第一个为主标注")
    ap.add_argument("--patch", action="append", default=[],
                    help="名字:基因=路径（JSONL 文件或目录），可重复；按参数顺序叠加，跳过 off_topic")
    ap.add_argument("--out", default="data/double/report")
    ap.set_defaults(handler=agree, command_parser=ap)
    review_parser = commands.add_parser("review", help="推送或拉回人工裁决")
    actions = review_parser.add_subparsers(dest="action", required=True)
    for action in ("push", "pull"):
        ap = actions.add_parser(action)
        ap.add_argument("--merged", default="data/double/report/merged.jsonl")
        ap.add_argument("--src", default="data/clean/reviews.jsonl")
        ap.add_argument("--final", default="data/labeled/genome-final.jsonl")
        ap.add_argument("--decisions", default="data/labeled/review-decisions.jsonl")
        ap.set_defaults(handler=review, command_parser=ap)
    ap = commands.add_parser("quality")
    ap.add_argument("--agreement", default="data/double/report/agreement.json")
    ap.add_argument("--final", default="data/labeled/genome-final.jsonl")
    ap.add_argument("--out", default="data/reports/quality-report.md")
    ap.set_defaults(handler=quality, command_parser=ap)
    ap = commands.add_parser("import")
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--pre", default="data/labeled/prelabels.jsonl")
    ap.add_argument("--name", default=f"genome-v{GENOME['version']}")
    ap.add_argument("--limit", type=int, default=0)
    ap.set_defaults(handler=import_data, command_parser=ap)
    args = parser.parse_args()
    args.handler(args, args.command_parser)


if __name__ == "__main__":
    main()
