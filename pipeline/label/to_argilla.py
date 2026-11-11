"""把清洗后的样本与模型预标导入 Argilla，供人工校对。

数据集的问题由 genome.json 生成（与预标脚本同一份定义）；预标结果作为 suggestion 挂在每条记录上，
"没能判定"的基因不挂建议，并在 metadata 里标出，方便筛出来优先校对。

用法：python pipeline/label/to_argilla.py [--name genome-v0.2.2] [--limit 200]
环境变量：ARGILLA_API_URL（默认 http://localhost:6900）、ARGILLA_API_KEY
"""
import argparse
import json
import os
from pathlib import Path

import argilla as rg

HERE = Path(__file__).parent
GENOME = json.loads((HERE / "genome.json").read_text(encoding="utf-8"))
SPEC_URL = GENOME["spec"]


def question(g):
    common = dict(name=g["id"], title=g["title"], required=g["id"] == "relevant")  # 至少要判断相关性
    if g["type"] == "single":
        return rg.LabelQuestion(labels=g["values"], **common)
    if g["type"] == "multi":
        return rg.MultiLabelQuestion(labels=g["values"], **common)
    if g["type"] == "rating":
        return rg.RatingQuestion(values=g["values"], **common)
    return rg.TextQuestion(**common)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--pre", default="data/labeled/prelabels.jsonl")
    ap.add_argument("--name", default=f"genome-v{GENOME['version']}")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

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


if __name__ == "__main__":
    main()
