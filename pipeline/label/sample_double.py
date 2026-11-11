"""抽取双标样本：按"应用 × 评分档"分层随机抽 10%，切成小块，交给其他模型独立标注。

用法：python pipeline/label/sample_double.py [--ratio 0.1] [--chunk 50] [--seed 42]
输出：data/double/sample.jsonl 与 data/double/chunks/chunk-XX.jsonl
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def band(rating):
    return "low" if rating <= 2 else "mid" if rating == 3 else "high"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--out", default="data/double")
    ap.add_argument("--ratio", type=float, default=0.1)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = [r for r in map(json.loads, open(args.src, encoding="utf-8")) if not r["low_info"]]
    strata = defaultdict(list)
    for r in rows:
        strata[(r["app"], band(r["rating"]))].append(r)
    rng = random.Random(args.seed)
    sample = []
    for key in sorted(strata):
        group = strata[key]
        k = max(1, round(len(group) * args.ratio))
        sample += rng.sample(group, min(k, len(group)))
    rng.shuffle(sample)

    out = Path(args.out)
    (out / "chunks").mkdir(parents=True, exist_ok=True)
    keep = ("id", "app", "rating", "text")
    with (out / "sample.jsonl").open("w", encoding="utf-8") as f:
        for r in sample:
            f.write(json.dumps({k: r[k] for k in keep}, ensure_ascii=False) + "\n")
    for i in range(0, len(sample), args.chunk):
        with (out / "chunks" / f"chunk-{i // args.chunk:02d}.jsonl").open("w", encoding="utf-8") as f:
            for r in sample[i: i + args.chunk]:
                f.write(json.dumps({k: r[k] for k in keep}, ensure_ascii=False) + "\n")
    print(f"抽样 {len(sample)} 条（{len(strata)} 层），切成 {(len(sample) + args.chunk - 1) // args.chunk} 块")


if __name__ == "__main__":
    main()
