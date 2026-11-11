"""人工裁决：把双标分歧样本推到 Argilla，裁决完成后拉回并覆盖最终标注。

推送：python pipeline/label/review_argilla.py push
拉回：python pipeline/label/review_argilla.py pull   # 写 data/labeled/review-decisions.jsonl 并更新 genome-final.jsonl
环境变量：ARGILLA_API_URL（默认 http://localhost:6900）、ARGILLA_API_KEY
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path

import argilla as rg

from check_labels import GENOME, check

GENES = {g["id"]: g for g in GENOME["genes"]}
REVIEW_GENES = ["relevant", "g5_touchpoint", "g15_solvable", "g16_severity"]
NAME = f"genome-review-v{GENOME['version']}"


def client():
    return rg.Argilla(api_url=os.environ.get("ARGILLA_API_URL", "http://localhost:6900"),
                      api_key=os.environ["ARGILLA_API_KEY"])


def show(v, gid):
    names = GENES[gid]["values"]
    if isinstance(v, list):
        return "、".join(names.get(x, x) for x in v) or "（空）"
    return names.get(v, str(v)) if isinstance(names, dict) else str(v)


def push(args):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["push", "pull"])
    ap.add_argument("--merged", default="data/double/report/merged.jsonl")
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--final", default="data/labeled/genome-final.jsonl")
    ap.add_argument("--decisions", default="data/labeled/review-decisions.jsonl")
    args = ap.parse_args()
    push(args) if args.action == "push" else pull(args)


if __name__ == "__main__":
    main()
