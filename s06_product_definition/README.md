# s06: 从标签到产品定义 — 让分布替你拍板

s01 → s02 → s03 → s04 → s05 → `s06`
> *"定义里的每一句都能指回样本"* — 分布、切片、机会地图 → 产品假设 → 产品定义。
>
> **方法层**：产品定义 v0：每条结论附条数与样本 id。

---

## 问题

标签齐了：4,209 条相关样本，十八个基因。你要的是「做什么」，手里还只有一张更大的表。

最大的人群不一定最该先做。陪伴向 708 条，一半没有提出任何问题（严重度为"无问题"的占 51.6%）。剧情玩家 216 条，P0+P1 占 60.6%。人多的那组多半满意，人少的那组在疼。按人数拍板，定义会做反。

这一章先把分布、切片和行为主题摆在一起，再按命中样本、P0+P1 比例、和首要用户的相关性来收敛。写进定义的每一句，都要带上条数和样本 id。

## 解决方案

![从标签到产品定义](images/definition-flow.svg)

三样东西一起看。`genome-report` 和 `segment-report` 由这一章的脚本从最终标注生成。写了「Agent 应当」的 821 条，再归成 24 个行为主题。然后看哪个痛点值得先做、谁来解。

| 报告 | 它回答的问题 | 占比的分母 |
|------|--------------|------------|
| `genome-report` | 人、事、解各取值有多少条 | 相关样本数；多选可以超过 100% |
| `segment-report` | 哪一类人更疼、更常写出「Agent 应当」 | 基因占比用这一片的人数 |
| 行为主题 | 821 条「Agent 应当」在要求什么 | 24 个主题各自的条数 |

两张表给的是条数和比例，不附样本 id。写产品定义时，从 `data/labeled/genome-final.jsonl` 里把对应的 id 摘到那一句旁边。产品定义的每一句都要能指回去。

## 工作原理

分步来看。

**第 1 步**：分布只统计 `relevant` 为 `yes` 的样本。表上的占比，分母是这个相关样本数。

```python
    allrows = [json.loads(l) for l in open(args.src, encoding="utf-8")]
    rows = [r for r in allrows if r["labels"].get("relevant") == "yes"]
    n = len(rows)
    annotator = allrows[0]["annotator"] if allrows else "无已标注样本"
    out = [f"# Agentic 产品基因图谱 · 分布报告（规范 v{GENOME['version']}）", "",
           f"- 样本：{len(allrows)} 条已标注，其中与陪伴产品相关 {n} 条，不相关 {len(allrows) - n} 条",
           f"- 标注：{annotator}（主标注），双标样本 {sum(r['in_double_sample'] for r in allrows)} 条",
           f"- 待人工裁决：{sum(bool(r['needs_review']) for r in allrows)} 条；已裁决：{sum(bool(r.get('review')) for r in allrows)} 条",
           "- 以下占比的分母为相关样本数；多选基因一条样本可计入多个取值，占比之和可超过 100%。", ""]
```

一条样本选了多个取值，会分别计入，所以占比加起来可以超过 100%。

**第 2 步**：人这条链四个基因各做一张表。事、解用同样的数法。

```python
    out.append("## 一、人：谁在说、为什么用\n")
    for gid in ("g1_user", "g2_motive", "g3_relation", "g4_investment"):
        c = Counter(x for r in rows for x in as_list(r["labels"].get(gid)))
        out += [f"### {GENES[gid]['title']}", table(c, n, gid), ""]
```

**第 3 步**：G13 不进取值表。句子里出现「Agent 应当」的，计为评测集种子；出现「产品应当」的，计为需求池。

```python
    agent = [r for r in rows if "Agent 应当" in (r["labels"].get("g13_expected") or "")]
    product = [r for r in rows if "产品应当" in (r["labels"].get("g13_expected") or "")]
    out += ["### G13 期望行为", f"- 写了“Agent 应当”（评测集种子）：{len(agent)} 条（{len(agent) / n if n else 0:.1%}）",
            f"- 写了“产品应当”（需求池）：{len(product)} 条（{len(product) / n if n else 0:.1%}）", ""]
```

同一条可以两句都有，两边都会数到。在这批标注上，评测集种子是 821 条（裁决把 1 条改判为不相关），后面归成 24 个行为主题。

**第 4 步**：一级触点对严重度做交叉，才能看见哪里又多又疼。

```python
    out.append("## 四、关键交叉\n")
    out.append("### 一级触点 × 严重度（条数）")
    sev = ["p0", "p1", "p2", "none"]
    cross = defaultdict(Counter)
    for r in rows:
        for t in as_list(r["labels"].get("g5_touchpoint")):
            cross[t][r["labels"].get("g16_severity")] += 1
    out += ["| 触点 | P0 | P1 | P2 | 无问题 | 合计 |", "|---|---|---|---|---|---|"]
    for t, cnt in sorted(cross.items(), key=lambda kv: -sum(kv[1].values())):
        out.append(f"| {genome_name('g5_touchpoint', t)} | " + " | ".join(str(cnt[s]) for s in sev) + f" | {sum(cnt.values())} |")
    out.append("")
```

列是 P0、P1、P2、无问题。一个触点被一条样本选中，就在这个触点的严重度上加 1。

**第 5 步**：切片的名字来自 G1 的取值，再加「陪伴向」和「创作向」。`unknown` 不单独成片。

```python
SEGMENTS = {
    value: f"{title}（`{value}`）"
    for value, title in GENES["g1_user"]["values"].items()
    if value != "unknown"
}


SEGMENTS.update({"陪伴向": "陪伴向", "创作向": "创作向"})
```

**第 6 步**：陪伴向看画像或动机，创作向也一样。一条样本可以同时进好几片。

```python
        users = values(labels, "g1_user")
        motives = values(labels, "g2_motive")
        memberships = users.intersection(SEGMENTS)
        if users.intersection({"dream_partner", "confider"}) or motives.intersection(
            {"companionship", "emotional_support", "romance"}
        ):
            memberships.add("陪伴向")
        if "creator" in users or "creation" in motives:
            memberships.add("创作向")
```

画像里有 `dream_partner` 或 `confider`，或者动机里有 `companionship`、`emotional_support`、`romance`，就进入陪伴向。画像里有 `creator`，或者动机里有 `creation`，就进入创作向。陪伴向的 708 条就是按这几条规则圈出来的。

**第 7 步**：每一片再数两件事：写了「Agent 应当」，以及严重度是 P0 或 P1。

```python
        expected = labels.get("g13_expected")
        agent = isinstance(expected, str) and "Agent 应当" in expected
        severe = labels.get("g16_severity") in ("p0", "p1")
        counts = {gid: values(labels, gid) for gid in REPORT_GENES}
        for key in memberships:
            segment = segments[key]
            segment["count"] += 1
            segment["agent"] += agent
            segment["p0_p1"] += severe
            for gid, entries in counts.items():
                segment["genes"][gid].update(entries)
```

同一个取值在一条样本里只计一次。剧情玩家这 216 条里，P0+P1 的 60.6% 就是这里的 `p0_p1 / count`。

**第 8 步**：写切片报告时，两套分母分开。样本占比用全部相关样本；P0+P1 和「Agent 应当」用这一片的人数。

```python
    for key, title in SEGMENTS.items():
        segment = segments[key]
        total = segment["count"]
        out += [
            f"## {title}", "",
            f"- 样本数：{total} 条；占相关样本：{percent(total, relevant)}。",
            f"- 写了“Agent 应当”：{segment['agent']} 条（{percent(segment['agent'], total)}）。",
            f"- P0+P1：{segment['p0_p1']} 条（{percent(segment['p0_p1'], total)}）。", "",
```

<details>
<summary>分母、排序与命令</summary>

空切片的比例写成 0.0%，不除以零。

```python
def percent(count, total):
    return f"{count / total if total else 0:.1%}"
```

只保留规范里有的取值，同一条里的重复取值收成一次。

```python
def values(labels, gid):
    """只保留规范中的枚举值，且一条样本的同一取值只计一次。"""
    raw = labels.get(gid)
    raw = raw if isinstance(raw, list) else [raw]
    return {value for value in raw
            if isinstance(value, str) and value in GENES[gid]["values"]}
```

条数相同的时候按枚举键排序，输出不跟着样本顺序晃。

```python
def top_values(counter, limit):
    # 同频时按枚举键排序，使输出不受样本顺序或集合迭代顺序影响。
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
```

| 子命令 | 默认输入 | 默认输出 |
|--------|----------|----------|
| `genome-report` | `data/labeled/genome-final.jsonl` | `data/reports/genome-report.md` |
| `segment-report` | 同上 | `data/reports/segment-report.md` |

- 切片内每个基因最多列 8 个取值。对比表里的触点和情感价值各列前 3。
- 分布报告的基因列表写在三段循环里。情绪强度没有单独的一张分布表，严重度出现在交叉表里。
- 分布报告末尾还有一张按应用的表：相关样本数、前三个一级触点、P0+P1 占比。
- 输入全是跑题样本时，相关样本数为 0，报告仍然写出，比例显示 0.0%。

</details>

## 试一下

**准备**（首次运行）：

```sh
pip install -r requirements.txt
```

这一章不读 `.env`。输入是 s04 合并、并经过 s05 裁决拉回之后的 `data/labeled/genome-final.jsonl`。下面的命令都在仓库根目录运行。

**运行**：

```sh
python s06_product_definition/code.py genome-report --src data/labeled/genome-final.jsonl
python s06_product_definition/code.py segment-report --src data/labeled/genome-final.jsonl
```

可以试这三件事：

1. 打开 `data/reports/segment-report.md` 末尾的切片对比，找出样本数最大的一行，再找出 P0+P1 比例最高的一行；
2. 在 `data/reports/genome-report.md` 里看 G13 的两行计数，再回到切片报告看各片的「Agent 应当」比例，两套分母不一样；
3. 给 `segment-report` 加上 `--out data/reports/segment-v2.md`，默认的 `data/reports/segment-report.md` 还在，新文件是另一份切片报告。

切片对比里能对上剧情玩家的 P0+P1；陪伴向的"无问题"比例在人群切片报告陪伴向一节的 G16 严重度表里。

**观察重点**：陪伴向 708 条里一半没有提出问题，剧情玩家 216 条 P0+P1 占 60.6%——人多的不一定最疼，最疼的不一定人多。

## 接下来

定义里的句子已经能指回样本。别人还不能拿着它直接做，也没有一套可以重复跑的测试。

s07 → 这些句子怎样写成一份别人能照着做、能照着测的 PRD？
