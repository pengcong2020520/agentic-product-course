#!/usr/bin/env python3
"""
s02_clean - 清洗与去标识

原始评论 → 统一空白 → 去标识 → 去重 → 标出信息量不足的样本

Usage:
    python s02_clean/code.py --src data/raw/appstore_reviews.jsonl --out data/clean/reviews.jsonl
"""
import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

PII = [
    ("[链接]", re.compile(r"https?://\S+|www\.\S+")),
    ("[邮箱]", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("[身份证]", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("[手机号]", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("[账号]", re.compile(r"(?i)(qq|微信|vx|wx|v信)\s*[:：号]?\s*[a-z0-9_-]{5,}")),
]
MIN_CHARS = 10  # 少于 10 个字的评论信息量不足，只计数不打标


def normalize(text):
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def scrub(text, counter):
    for tag, pat in PII:
        text, n = pat.subn(tag, text)
        counter[tag] += n
    return text


def shingles(text, k=3):
    t = re.sub(r"[\W_]+", "", text)
    return {t[i:i + k] for i in range(max(len(t) - k + 1, 1))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/raw/appstore_reviews.jsonl")
    ap.add_argument("--out", default="data/clean/reviews.jsonl")
    ap.add_argument("--near", type=float, default=0.85, help="近似重复的 Jaccard 阈值")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.src, encoding="utf-8")]
    report = {"input": len(rows)}
    pii = Counter()
    for r in rows:
        r["text"] = scrub(normalize(f"{r['title']}。{r['content']}"), pii)
    report["pii_replaced"] = dict(pii)

    exact, kept = set(), []
    for r in rows:
        key = re.sub(r"[\W_]+", "", r["text"])
        if key in exact:
            continue
        exact.add(key)
        kept.append(r)
    report["after_exact_dedup"] = len(kept)

    # 近似重复：同一应用内比较 3-gram 的 Jaccard 相似度（数据量小，直接两两比较）
    result, by_app = [], {}
    for r in kept:
        sig = shingles(r["text"])
        peers = by_app.setdefault(r["app"], [])
        if any(len(sig & s) / len(sig | s) >= args.near for s in peers):
            continue
        peers.append(sig)
        result.append(r)
    report["after_near_dedup"] = len(result)

    for r in result:
        r["low_info"] = len(re.sub(r"[\W_]+", "", r["content"])) < MIN_CHARS
        for k in ("title", "content"):
            r.pop(k)
    report["low_info"] = sum(r["low_info"] for r in result)
    report["to_label"] = len(result) - report["low_info"]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in result:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()