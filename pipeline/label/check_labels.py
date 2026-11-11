"""检查一份标注文件：行数与 id 对应、取值合法（与 prelabel.validate 同一套规则）。

用法：python pipeline/label/check_labels.py <输入 chunk> <标注输出>
"""
import json
import sys
from pathlib import Path

GENOME = json.loads((Path(__file__).parent / "genome.json").read_text(encoding="utf-8"))


def check(raw):
    bad = []
    for g in GENOME["genes"]:
        v, t = raw.get(g["id"]), g["type"]
        if raw.get("relevant") == "off_topic" and g["id"] != "relevant":
            continue
        if t in ("single", "rating"):
            ok = v in g["values"]
        elif t == "multi":
            ok = isinstance(v, list) and all(x in g["values"] for x in v) \
                 and bool(v or g.get("optional")) and len(v) <= g.get("max", 99)
            if ok and g.get("parent"):
                ok = all(x.split(".")[0] in (raw.get(g["parent"]) or []) for x in v)
        else:
            ok = isinstance(v, str)
        if not ok:
            bad.append(f"{g['id']}={v!r}")
    return bad


def main():
    src, out = sys.argv[1], sys.argv[2]
    ids = [json.loads(l)["id"] for l in open(src, encoding="utf-8")]
    rows = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
    errors = []
    if sorted(r.get("id") for r in rows) != sorted(ids):
        errors.append(f"id 不对应：输入 {len(ids)} 条，输出 {len(rows)} 条")
    for r in rows:
        bad = check(r)
        if bad:
            errors.append(f"{r.get('id')}: " + ", ".join(bad))
    print("OK" if not errors else "\n".join(errors[:30]))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
