"""合并最终标注：主标注（Codex）的全量 + 双标样本，替换单独重标的基因，挂上裁决标记。

规则见 docs/genome/annotation-protocol.md 第 5 节：最终标注以主标注为准；双标样本中关键基因分歧的
样本标 needs_review，人工裁决后用 `review_argilla.py pull` 覆盖。

用法：python pipeline/label/merge_final.py [--relabeled g17_risk] [--out data/labeled/genome-final.jsonl]
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from check_labels import GENOME, check


def read_dir(path):
    out = {}
    for f in sorted(Path(path).glob("*.jsonl")):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                out[d["id"]] = d
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", default="codex")
    ap.add_argument("--dirs", default="data/full,data/double")
    ap.add_argument("--relabeled", default="g17_risk", help="单独重标过的基因，逗号分隔")
    ap.add_argument("--review", default="data/double/report/merged.jsonl")
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--out", default="data/labeled/genome-final.jsonl")
    args = ap.parse_args()

    labels, relabels = {}, {g: {} for g in filter(None, args.relabeled.split(","))}
    for d in args.dirs.split(","):
        labels.update(read_dir(f"{d}/{args.main}"))
        for g in relabels:
            relabels[g].update(read_dir(f"{d}/{args.main}-{g}"))
    review = {}
    if Path(args.review).exists():
        review = {m["id"]: m["needs_review"] for m in map(json.loads, open(args.review, encoding="utf-8"))}

    src = {r["id"]: r for r in map(json.loads, open(args.src, encoding="utf-8")) if not r["low_info"]}
    stats = Counter()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for rid, r in src.items():
            lab = labels.get(rid)
            if lab is None:
                stats["missing"] += 1
                continue
            lab = {k: v for k, v in lab.items() if k != "id"}
            for g, rel in relabels.items():
                if lab.get("relevant") == "off_topic":
                    continue
                if rid in rel:
                    lab[g] = rel[rid][g]
                else:
                    stats[f"missing_relabel_{g}"] += 1
            if check(lab):
                stats["invalid"] += 1
            rec = {"id": rid, "app": r["app"], "rating": r["rating"], "date": r["date"], "text": r["text"],
                   "labels": lab, "annotator": args.main, "genome": GENOME["version"],
                   "in_double_sample": rid in review, "needs_review": review.get(rid, [])}
            stats["relevant" if lab.get("relevant") == "yes" else "off_topic"] += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    stats["total_written"] = stats["relevant"] + stats["off_topic"]
    stats["needs_review"] = sum(bool(v) for v in review.values())
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
