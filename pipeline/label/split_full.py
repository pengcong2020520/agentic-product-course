"""把全量待标样本切块，交给主标注者（Codex CLI）。

已在双标样本里标过的样本不重复切块，最后由 merge 阶段并回。
用法：python pipeline/label/split_full.py [--chunk 50]
输出：data/full/chunks/chunk-XXX.jsonl
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--sample", default="data/double/sample.jsonl")
    ap.add_argument("--out", default="data/full")
    ap.add_argument("--chunk", type=int, default=50)
    args = ap.parse_args()

    done = {json.loads(l)["id"] for l in open(args.sample, encoding="utf-8")}
    rows = [r for r in map(json.loads, open(args.src, encoding="utf-8"))
            if not r["low_info"] and r["id"] not in done]
    out = Path(args.out) / "chunks"
    out.mkdir(parents=True, exist_ok=True)
    keep = ("id", "app", "rating", "text")
    for i in range(0, len(rows), args.chunk):
        with (out / f"chunk-{i // args.chunk:03d}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows[i: i + args.chunk]:
                f.write(json.dumps({k: r[k] for k in keep}, ensure_ascii=False) + "\n")
    print(f"全量待标 {len(rows)} 条（已排除双标样本 {len(done)} 条），切成 {(len(rows) + args.chunk - 1) // args.chunk} 块")


if __name__ == "__main__":
    main()
