#!/usr/bin/env python3
"""
s03_product_genome - 产品基因图谱

查看基因清单，并校验标注文件的 id 与基因取值。

Usage:
    python s03_product_genome/code.py list
    python s03_product_genome/code.py check data/double/chunks/chunk-00.jsonl data/double/codex/chunk-00.jsonl
    python s03_product_genome/code.py check INPUT.jsonl OUTPUT.jsonl g17_risk
"""
import argparse
import json
from pathlib import Path

GENOME = json.loads((Path(__file__).resolve().parents[1] / "s03_product_genome/genome.json").read_text(encoding="utf-8"))


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    checker = commands.add_parser("check", help="校验标注 id 与合法取值")
    checker.add_argument("src")
    checker.add_argument("out")
    checker.add_argument("only", nargs="?", help="只检查的基因，逗号分隔")
    commands.add_parser("list", help="打印基因 id、标题、类型与合法取值")
    args = parser.parse_args()
    if args.command == "list":
        for gene in GENOME["genes"]:
            print(f"{gene['id']}\t{gene['title']}\t{gene['type']}")
            for value in gene.get("values", []):
                title = gene["values"][value] if isinstance(gene["values"], dict) else value
                print(f"  {value}: {title}")
    else:
        errors = check_file(args.src, args.out, set(args.only.split(",")) if args.only else None)
        print("OK" if not errors else "\n".join(errors[:30]))
        raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
