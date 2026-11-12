#!/usr/bin/env python3
"""
s04_labeling - 独立标注

分层抽样 → 全量切块 → 并发独立标注 → 合并主标注与单基因重标结果。
环境变量：CODEX_BIN、GROK_BIN、GENE（只重标一个基因）。

Usage:
    python s04_labeling/code.py sample --ratio 0.1
    python s04_labeling/code.py split --chunk 50
    python s04_labeling/code.py run data/double codex,grok 5 --dry-run
    GENE=g17_risk python s04_labeling/code.py run data/double codex,grok 5
    python s04_labeling/code.py merge --relabeled g17_risk
"""


import argparse
import json
import os
import random
import shlex
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


GENOME = json.loads((Path(__file__).resolve().parents[1] / "s03_product_genome/genome.json").read_text(encoding="utf-8"))


GENES = {g["id"]: g for g in GENOME["genes"]}


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


def band(rating):
    return "low" if rating <= 2 else "mid" if rating == 3 else "high"


def sample(args, ap):

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




def split(args, ap):

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


def read_dir(path):
    out = {}
    for f in sorted(Path(path).glob("*.jsonl")):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                out[d["id"]] = d
    return out


def merge(args, ap):

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


def run(args, ap):
    """保留 shell 调用参数、总并发上限、断点校验与日志/brief 命名。"""
    started_at = datetime.now(timezone.utc).isoformat()
    if args.jobs < 1:
        ap.error("并发数必须大于 0")
    root = Path(__file__).resolve().parents[1]
    directory = Path(args.directory)
    gene = os.environ.get("GENE", "")
    only = set(gene.split(",")) if gene else None
    template = Path(__file__).with_name("gene-brief.md" if gene else "brief.md").read_text(encoding="utf-8")
    codex = os.environ.get("CODEX_BIN") or "codex"
    grok = os.environ.get("GROK_BIN") or "grok"
    environment = {**os.environ, "DIR": str(directory), "CODEX_BIN": codex,
                   "GROK_BIN": grok, "GENE": gene, "PWD": str(root)}

    def task(who, src):
        number = src.stem
        tag = who + (f"-{gene}" if gene else "")
        out = directory / tag / f"{number}.jsonl"
        brief = directory / "briefs" / f"{tag}-{number}.md"
        log = directory / "logs" / f"{tag}-{number}.log"
        final = directory / "logs" / f"{tag}-{number}.final.md"
        text = template.replace("{IN}", str(src)).replace("{OUT}", str(out)).replace("{GENE}", gene)
        if who == "codex":
            command = [codex, "exec", "-C", str(root), "-s", "workspace-write", "-o", str(final), "-"]
            display = shlex.join(command) + " < " + shlex.quote(str(brief))
        else:
            command = [grok, "-p", text.rstrip("\n"), "--always-approve", "--cwd", str(root), "--disable-web-search"]
            # Display shell-equivalent brief expansion on one line, without dumping the prompt.
            display = shlex.quote(grok) + ' -p "$(cat ' + shlex.quote(str(brief)) + ')" --always-approve --cwd ' + shlex.quote(str(root)) + ' --disable-web-search'
        if out.is_file() and out.stat().st_size:
            try:
                if not check_file(src, out, only):
                    print(f"跳过 {who} {number}（已完成且校验通过）", flush=True)
                    return
            except Exception:
                pass  # 原 shell 的校验失败同样会重新运行。
        if args.dry_run:
            print(display + " > " + shlex.quote(str(log)) + " 2>&1")
            return
        for parent in (out.parent, brief.parent, log.parent):
            parent.mkdir(parents=True, exist_ok=True)
        brief.write_text(text, encoding="utf-8")
        start = int(time.time())
        with log.open("w", encoding="utf-8") as output, brief.open(encoding="utf-8") as prompt:
            try:
                subprocess.run(command, cwd=root, env=environment, stdin=prompt if who == "codex" else None,
                               stdout=output, stderr=subprocess.STDOUT, check=False)
            except OSError as exc:
                output.write(f"{exc}\n")  # 与 shell 的 || true 一致，继续校验并运行其他分块。
            output.write(f"\n# annotator-version: {metadata['annotators'][who]['version']}\n")
        verdict = "没能判定（未生成输出）"
        if out.is_file() and out.stat().st_size:
            try:
                errors = check_file(src, out, only)
                verdict = errors[0] if errors else "OK"
            except Exception as exc:
                verdict = f"{type(exc).__name__}: {exc}"
        print(f"{tag} {number} 用时 {int(time.time()) - start}s：{verdict}", flush=True)

    annotators = args.annotators.replace(",", " ").split()
    metadata = {"started_at": started_at, "annotators": {
        who: {"bin": codex if who == "codex" else grok, "version": "unknown"}
        for who in annotators
    }, "gene": gene}

    def preflight(who):
        info = metadata["annotators"][who]
        command = [info["bin"], "--version"]
        with tempfile.TemporaryDirectory(prefix=f"labeling-{who}-") as temporary:
            smoke = Path(temporary) / "smoke.txt"
            log = Path(temporary) / "preflight.log"
            with log.open("w", encoding="utf-8") as output:
                try:
                    version = subprocess.run(command, cwd=temporary, env=environment,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             text=True, check=False, timeout=15)
                    output.write(version.stdout or "")
                    if version.returncode != 0 or not (version.stdout or "").strip():
                        raise RuntimeError("版本查询失败或返回空版本")
                    info["version"] = version.stdout.splitlines()[0]
                    prompt = "Write a file named smoke.txt in the current directory containing exactly ok (no newline)."
                    if who == "codex":
                        command = [info["bin"], "exec", "-C", temporary, "-s", "workspace-write",
                                   "--skip-git-repo-check", "-"]
                    else:
                        command = [info["bin"], "-p", prompt, "--always-approve", "--cwd", temporary]
                    output.flush()
                    result = subprocess.run(command, cwd=temporary, env=environment,
                                            input=prompt if who == "codex" else None, text=True,
                                            stdout=output, stderr=subprocess.STDOUT, check=False, timeout=120)
                    if result.returncode != 0:
                        raise RuntimeError(f"冒烟命令退出码 {result.returncode}")
                    if not smoke.is_file() or smoke.read_text(encoding="utf-8") != "ok":
                        raise RuntimeError("smoke.txt 不存在或内容不是 ok")
                    return
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    failure = str(exc)
            print(f"冒烟检查失败：{who}\n命令：{shlex.join(command)}\n原因：{failure}\n日志末尾 20 行：", flush=True)
            print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]), flush=True)
            raise SystemExit(2)

    # Like the original shell, resolve relative data paths from the repository root.
    os.chdir(root)
    if not args.dry_run:
        (directory / "logs").mkdir(parents=True, exist_ok=True)
        (directory / "briefs").mkdir(parents=True, exist_ok=True)
        try:
            if not args.skip_preflight:
                for who in metadata["annotators"]:
                    preflight(who)
        finally:
            (directory / "logs" / "run-meta.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tasks = [(who, src) for src in sorted((directory / "chunks").glob("*.jsonl"))
             for who in args.annotators.replace(",", " ").split()]
    if args.dry_run:
        for who, src in tasks:
            task(who, src)
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(task, who, src) for who, src in tasks]
            for future in futures:
                future.result()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ap = commands.add_parser("sample")
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--out", default="data/double")
    ap.add_argument("--ratio", type=float, default=0.1)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.set_defaults(handler=sample, command_parser=ap)
    ap = commands.add_parser("split")
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--sample", default="data/double/sample.jsonl")
    ap.add_argument("--out", default="data/full")
    ap.add_argument("--chunk", type=int, default=50)
    ap.set_defaults(handler=split, command_parser=ap)
    ap = commands.add_parser("merge")
    ap.add_argument("--main", default="codex")
    ap.add_argument("--dirs", default="data/full,data/double")
    ap.add_argument("--relabeled", default="g17_risk", help="单独重标过的基因，逗号分隔")
    ap.add_argument("--review", default="data/double/report/merged.jsonl")
    ap.add_argument("--src", default="data/clean/reviews.jsonl")
    ap.add_argument("--out", default="data/labeled/genome-final.jsonl")
    ap.set_defaults(handler=merge, command_parser=ap)
    ap = commands.add_parser("run", help="并发运行已登录的 Codex/Grok CLI")
    ap.add_argument("directory", help="数据目录，如 data/double 或 data/full")
    ap.add_argument("annotators", help="标注者，逗号分隔，如 codex,grok")
    ap.add_argument("jobs", type=int, nargs="?", default=5)
    ap.add_argument("--dry-run", action="store_true", help="仅打印命令；不调用 CLI、不写文件")
    ap.add_argument("--skip-preflight", action="store_true", help="跳过执行器冒烟检查及版本查询")
    ap.set_defaults(handler=run, command_parser=ap)
    args = parser.parse_args()
    args.handler(args, args.command_parser)


if __name__ == "__main__":
    main()
