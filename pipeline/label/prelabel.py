"""模型预标：按 Agentic 产品基因图谱给每条样本打标签，结果作为人工校对的建议。

调用 OpenAI 兼容接口（默认 Kimi），每次请求一批样本；返回值逐项按 genome.json 校验，
不合法的基因记为"没能判定"（null），进入人工校对时重点看。支持断点续跑。

用法：
  export KIMI_API_KEY=...
  python pipeline/label/prelabel.py --limit 50            # 先试 50 条
  python pipeline/label/prelabel.py                       # 全量
"""
import argparse
import json
import os
import time
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).parent
GENOME = json.loads((HERE / "genome.json").read_text(encoding="utf-8"))
SPEC = (HERE.parent.parent / "docs/genome/agentic-product-genome-v0.1.md").read_text(encoding="utf-8")

SYSTEM = f"""你是用户研究标注员。按下面的《Agentic 产品基因图谱》标注规范，给每条用户评论打标签。
看不出来就用 unknown 或留空，不要猜。只输出 JSON。

{SPEC}

输出格式：{{"items": [{{"id": "...", "relevant": "yes|off_topic", "g1_user": [...], "g2_motive": [...],
"g3_touchpoint": [...], "g4_emotion": "...", "g4_intensity": 1, "g5_voice_type": "...", "g6_stage": "...",
"g7_expected": "Agent 应当……或空字符串", "g8_solvable": "...", "g9_risk": [...]}}]}}
所有取值必须是规范里的英文值。relevant 为 off_topic 时其余字段可省略。"""


def validate(raw):
    """按 genome.json 校验一条结果；不合法的基因置为 None（没能判定）。"""
    out, invalid = {}, []
    for g in GENOME["genes"]:
        v = raw.get(g["id"])
        t = g["type"]
        if t == "single":
            ok = v in g["values"]
        elif t == "multi":
            ok = isinstance(v, list) and all(x in g["values"] for x in v) and (v or g.get("optional")) \
                 and len(v) <= g.get("max", 99)
        elif t == "rating":
            ok = v in g["values"]
        else:
            ok = isinstance(v, str)
        if raw.get("relevant") == "off_topic" and g["id"] != "relevant":
            ok, v = True, None
        out[g["id"]] = v if ok else None
        if not ok:
            invalid.append(g["id"])
    return out, invalid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--out", default="data/labeled/prelabels.jsonl")
    ap.add_argument("--model", default=os.environ.get("PRELABEL_MODEL", "kimi-k3.1-pro"))
    ap.add_argument("--base-url", default=os.environ.get("PRELABEL_BASE_URL", "https://api.moonshot.cn/v1"))
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0, help="只标前 N 条（试跑用）")
    args = ap.parse_args()

    client = OpenAI(api_key=os.environ["KIMI_API_KEY"], base_url=args.base_url)
    rows = [json.loads(l) for l in open(args.src, encoding="utf-8")]
    rows = [r for r in rows if not r["low_info"]]
    if args.limit:
        rows = rows[: args.limit]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["id"] for l in open(out, encoding="utf-8")} if out.exists() else set()
    todo = [r for r in rows if r["id"] not in done]
    usage = {"prompt": 0, "completion": 0, "cached": 0}
    print(f"待标 {len(todo)} 条（已完成 {len(done)}），模型 {args.model}")

    with out.open("a", encoding="utf-8") as f:
        for i in range(0, len(todo), args.batch):
            batch = todo[i: i + args.batch]
            user = json.dumps([{"id": r["id"], "app": r["app"], "rating": r["rating"], "text": r["text"]}
                               for r in batch], ensure_ascii=False)
            for attempt in range(3):
                try:
                    resp = client.chat.completions.create(
                        model=args.model,
                        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                        response_format={"type": "json_object"},
                    )
                    items = {x.get("id"): x for x in json.loads(resp.choices[0].message.content)["items"]}
                    break
                except Exception as exc:  # 网络、限流、格式错误都重试；三次失败则整批记为没能判定
                    print(f"  第 {i} 批第 {attempt + 1} 次失败：{exc}")
                    items = {}
                    time.sleep(5 * (attempt + 1))
            else:
                resp = None
            if resp is not None and resp.usage:
                usage["prompt"] += resp.usage.prompt_tokens
                usage["completion"] += resp.usage.completion_tokens
                details = getattr(resp.usage, "prompt_tokens_details", None)
                usage["cached"] += getattr(details, "cached_tokens", 0) or 0
            for r in batch:
                labels, invalid = validate(items.get(r["id"], {}))
                f.write(json.dumps({"id": r["id"], "labels": labels, "undetermined": invalid,
                                    "model": args.model, "genome": GENOME["version"]}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {min(i + args.batch, len(todo))}/{len(todo)}  tokens={usage}")
    print("用量：", usage)


if __name__ == "__main__":
    main()
