"""模型预标：按 Agentic 产品基因图谱给每条样本打标签，结果作为人工校对的建议。

调用 OpenAI 兼容接口（默认 Kimi），每次请求一批样本；返回值逐项按 genome.json 校验，
不合法的基因记为"没能判定"（null），进入人工校对时重点看。支持断点续跑。

用法：
  export KIMI_API_KEY=...
  python s05_agreement/prelabel.py --limit 50            # 先试 50 条
  python s05_agreement/prelabel.py                       # 全量
"""
import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).parent
GENOME = json.loads((HERE.parent / "s03_product_genome/genome.json").read_text(encoding="utf-8"))
SPEC = (HERE.parent / GENOME["spec"]).read_text(encoding="utf-8")

EXAMPLE = json.dumps({"id": "样本 id", **{g["id"]: {"single": "<值>", "multi": ["<值>"], "rating": 2, "text": ""}[g["type"]]
                                         for g in GENOME["genes"]}}, ensure_ascii=False)

SYSTEM = f"""你是用户研究标注员。按下面的《Agentic 产品基因图谱》标注规范，给每条用户评论打标签。
看不出来就用 unknown 或留空，不要猜。只输出 JSON。

{SPEC}

输出格式：{{"items": [{EXAMPLE}]}}
每个 item 必须包含上例中的全部字段（single 填一个值，multi 填数组，rating 填 1-3，text 填字符串）。
所有取值必须是规范里的英文值；多选基因至少给一个值（看不出来用 unknown 或 none）；g6_subtouch 只能选所选 g5_touchpoint 之下的二级值。relevant 为 off_topic 时其余字段可省略。"""


def validate(raw):
    """按 genome.json 校验一条结果；不合法的基因置为 None（没能判定）。"""
    out, invalid = {}, []
    for g in GENOME["genes"]:
        v = raw.get(g["id"])
        t = g["type"]
        if t == "single":
            ok = v in g["values"]
        elif t == "multi":
            ok = isinstance(v, list) and all(x in g["values"] for x in v) and bool(v or g.get("optional")) \
                 and len(v) <= g.get("max", 99)
            if ok and g.get("parent"):  # 二级必须落在所选一级之下
                parents = raw.get(g["parent"]) or []
                ok = all(x.split(".")[0] in parents for x in v)
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
    ap.add_argument("--model", default=os.environ.get("PRELABEL_MODEL", "kimi-k2.7-code-highspeed"))
    ap.add_argument("--base-url", default=os.environ.get("PRELABEL_BASE_URL", "https://api.moonshot.cn/v1"))
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="只标前 N 条（试跑用）")
    ap.add_argument("--workers", type=int, default=4, help="并发请求数")
    args = ap.parse_args()

    client = OpenAI(api_key=os.environ["KIMI_API_KEY"], base_url=args.base_url, timeout=300, max_retries=0)
    rows = [json.loads(l) for l in open(args.src, encoding="utf-8")]
    rows = [r for r in rows if not r.get("low_info")]
    if args.limit:
        rows = rows[: args.limit]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["id"] for l in open(out, encoding="utf-8")} if out.exists() else set()
    todo = [r for r in rows if r["id"] not in done]
    usage = {"prompt": 0, "completion": 0, "cached": 0}
    print(f"待标 {len(todo)} 条（已完成 {len(done)}），模型 {args.model}")

    lock = threading.Lock()
    batches = [todo[i: i + args.batch] for i in range(0, len(todo), args.batch)]
    finished = [0]

    stop = threading.Event()
    failed = [0]

    def run(batch):
        if stop.is_set():
            return
        user = json.dumps([{"id": r["id"], "app": r["app"], "rating": r["rating"], "text": r["text"]}
                           for r in batch], ensure_ascii=False)
        items, resp = {}, None
        for attempt in range(3):
            try:
                # 流式请求：模型推理较久，非流式长时间没有数据会被当成超时断开
                stream = client.chat.completions.create(
                    model=args.model,
                    messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    stream=True,
                    stream_options={"include_usage": True},
                )
                parts, resp = [], None
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        parts.append(chunk.choices[0].delta.content)
                    if chunk.usage:
                        resp = chunk
                items = {x.get("id"): x for x in json.loads("".join(parts))["items"]}
                break
            except Exception as exc:  # 网络、限流、格式错误都重试
                print(f"  批次 {batch[0]['id']} 第 {attempt + 1} 次失败：{exc}")
                resp = None
                if "insufficient balance" in str(exc) or "suspended" in str(exc):
                    stop.set()  # 余额不足：停止派发新批次
                    return
                time.sleep(5 * (attempt + 1))
        if not items:
            # 整批失败不写入，下次运行会重新标注；不把"没调通"记成"没能判定"
            with lock:
                failed[0] += len(batch)
            return
        with lock:
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
            finished[0] += len(batch)
            print(f"  {finished[0]}/{len(todo)}  tokens={usage}", flush=True)

    with out.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, batches))
    print("用量：", usage)
    if failed[0] or stop.is_set():
        print(f"未完成 {len(todo) - finished[0]} 条（整批失败 {failed[0]} 条{'，余额不足已停止' if stop.is_set() else ''}），重新运行即可续跑")


if __name__ == "__main__":
    main()
