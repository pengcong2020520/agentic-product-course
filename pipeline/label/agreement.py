"""多方一致性与合并：主标注（Codex）与独立复标（Grok），也支持三方。

按 docs/genome/annotation-protocol.md 第 4、5 节计算：单选 Cohen's κ / Fleiss' κ，多选逐标签 κ 与 Jaccard，
强度用加权 κ；某方缺失或不合法记为"没能判定"，单独计数。输出一致性报告和合并结果（含是否需人工裁决）。

用法：python pipeline/label/agreement.py --ann codex=data/double/codex --ann grok=data/double/grok \
        --out data/double/report
"""
import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from check_labels import GENOME, check

GENES = {g["id"]: g for g in GENOME["genes"]}


def load(path):
    p = Path(path)
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    out = {}
    for f in files:
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            labels = d.get("labels", d)  # prelabel 输出包在 labels 里，复标直接是字段
            if check(labels):  # 不合法：整条记为没能判定
                out[d["id"]] = None
            else:
                out[d["id"]] = labels
    return out


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ann", action="append", required=True, help="名字=路径（文件或目录），第一个为主标注")
    ap.add_argument("--out", default="data/double/report")
    args = ap.parse_args()

    ann = {}
    for spec in args.ann:
        name, path = spec.split("=", 1)
        ann[name] = load(path)
    names = list(ann)
    sample = set.intersection(*(set(v) for v in ann.values() if v)) if all(ann.values()) else set()
    # 只统计三方都有记录的样本；任一方不合法 → 该样本没能判定
    ids = sorted(i for i in sample if all(ann[n][i] is not None for n in names))
    undetermined = {n: sum(ann[n].get(i) is None for i in sample) for n in names}
    rel = [i for i in ids if all(ann[n][i].get("relevant") == "yes" for n in names)]

    report = {"annotators": names, "sample": len(sample), "usable": len(ids), "both_relevant": len(rel),
              "undetermined": undetermined, "genes": {}}
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

    # 最终标注取主标注（第一个标注者）；只有关键基因分歧进入人工裁决（规则见 annotation-protocol.md 第 5 节）
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


if __name__ == "__main__":
    main()
