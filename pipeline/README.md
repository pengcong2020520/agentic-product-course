# 原始数据集流水线

按执行顺序把 App Store 中国区公开评论抓取、清洗，再用 Codex CLI 做全量主标注、用 Grok CLI 对 10% 分层样本做独立复标，然后计算一致性、把关键分歧送进 Argilla 裁决，并合并成最终标注。

`data/` 在 `.gitignore` 里，不进仓库。仓库只有脚本和 `pipeline/crawl/apps.json` 中的应用清单，没有评论数据。读者需要自己从步骤 1 跑抓取。

除另行说明的命令外，都在仓库根目录执行。脚本参数的默认路径也是相对仓库根目录。

## 环境准备

### Python

`pipeline/pyproject.toml` 的 `requires-python` 是 `>=3.11`，依赖是 `argilla>=2.8`、`openai>=1.50`、`requests>=2.31`。仓库里没有 `uv.lock`。

```bash
uv sync --directory pipeline
source pipeline/.venv/bin/activate
```

`uv sync --directory pipeline` 使用 `pipeline/pyproject.toml`，在 `pipeline/` 下创建 `.venv`，并生成 `pipeline/uv.lock`。`.venv/` 已被忽略。

爬取、清洗、抽样、切块、校验、一致性和合并只用 Python 标准库。`prelabel.py` 导入 `openai`。`to_argilla.py`、`review_argilla.py` 导入 `argilla`。

仓库根目录在 CI（`.github/workflows/ci.yml`）中运行 `python scripts/privacy_check.py`、`python scripts/verify_docs.py`；`pipeline/tests/` 存在时再运行 `python -m unittest discover -s pipeline/tests -t . -v`。提交前可在本地先跑。

### Argilla

裁决（以及文末备用的预标导入）使用本地 Argilla。编排文件是 `pipeline/label/docker-compose.yaml`，其中有 `argilla`、`worker`、`postgres`、`elasticsearch`、`redis`。`argilla` 的端口是 `127.0.0.1:6900`。

账号写在 `pipeline/label/.env`。`.gitignore` 忽略 `.env`、`.env.*` 和 `pipeline/label/.env`。在 `pipeline/label/` 里执行 Compose 时，它读取同目录的 `.env`。变量来自该 yaml：

| 变量 | 作用 |
|---|---|
| `ARGILLA_USERNAME` | 可选，默认 `argilla` |
| `ARGILLA_PASSWORD` | 必填，传给容器环境变量 `PASSWORD` |
| `ARGILLA_API_KEY` | 必填，同时给服务端和后面的 Python 客户端用 |

```bash
cd pipeline/label
docker compose up
```

`ARGILLA_PASSWORD` 或 `ARGILLA_API_KEY` 为空时，Compose 会按 yaml 里的 `${VAR:?set ... in .env}` 拒绝启动。这个命令在前台运行。服务起来后，网页在 `http://localhost:6900`。后面的 Python 命令回到仓库根目录执行。

`to_argilla.py` 和 `review_argilla.py` 从进程环境读取 `ARGILLA_API_KEY`，以及可选的 `ARGILLA_API_URL`（默认 `http://localhost:6900`）。跑这两个脚本前，把 `pipeline/label/.env` 导出到当前环境：

```bash
set -a
source pipeline/label/.env
set +a
```

## 步骤 1 爬取

**做什么。** `pipeline/crawl/appstore_reviews.py` 读取应用清单，请求 Apple 中国区公开评论 RSS。地址模板是 `https://itunes.apple.com/cn/rss/customerreviews/page={page}/id={app_id}/sortby={sort}/json`。每个应用、每种排序最多 10 页；两种排序是 `mostrecent` 和 `mosthelpful`；页与页之间等待 1.5 秒；单次请求超时 20 秒，最多请求 3 次。同一应用内按评论 id 去重。只保存评论本身，不保存评论者昵称。样本 `id` 为 `as-` 加上 `sha1(应用 id + ":" + 评论 id)` 的前 12 位十六进制。固定字段还有 `source`（`appstore-cn`）、`app`、`app_id`、`rating`、`title`、`content`、`version`、`date`。

**命令。**

```bash
python pipeline/crawl/appstore_reviews.py --apps pipeline/crawl/apps.json --out data/raw/appstore_reviews.jsonl
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--apps` | `pipeline/crawl/apps.json` | 应用清单，JSON 数组，每项有 `id` 和 `name` |
| `--out` | `data/raw/appstore_reviews.jsonl` | 原始 JSONL |

**输入。** `pipeline/crawl/apps.json`（进仓库）。

**输出。**

- `data/raw/appstore_reviews.jsonl`：每行一条评论。
- `data/raw/appstore_reviews.meta.json`：全部应用写完后才生成，含 `crawled_at`（UTC）、`total`、`apps`。

重跑会覆盖 `--out`。中途停下则没有 meta 文件。

**是否进仓库。** 不进。`data/` 被忽略。

## 步骤 2 清洗

**做什么。** `pipeline/clean/clean.py` 把原始评论变成可标注文本：NFKC 与空白归一；把标题和正文合成 `text`（中间用 `。`）；按固定顺序把链接、邮箱、身份证号、手机号、QQ/微信号替换成 `[链接]`、`[邮箱]`、`[身份证]`、`[手机号]`、`[账号]`。完全去重的键是去掉标点、空白和下划线后的 `text`（正则 `\W` 与 `_`，中文保留）。近似重复只在同一应用内比较，用 3 字符片段的 Jaccard 相似度。信息量不足的样本保留并打上 `low_info`，不删除。判定读取写出前的原 `content` 字段：同样去掉标点、空白和下划线后，长度小于常量 `MIN_CHARS`（10）。这个阈值没有命令行参数。写出前删除 `title` 和 `content`。

**命令。**

```bash
python pipeline/clean/clean.py --src data/raw/appstore_reviews.jsonl --out data/clean/reviews.jsonl --near 0.85
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--src` | `data/raw/appstore_reviews.jsonl` | 步骤 1 的 JSONL |
| `--out` | `data/clean/reviews.jsonl` | 清洗结果 |
| `--near` | `0.85` | 近似重复的 Jaccard 阈值 |

**输入。** `data/raw/appstore_reviews.jsonl`。

**输出。**

- `data/clean/reviews.jsonl`：保留来源字段，并有 `text`、`low_info`。
- `data/clean/reviews.report.json`：`input`、`pii_replaced`、`after_exact_dedup`、`after_near_dedup`、`low_info`、`to_label`。标准输出也会打印这份计数。

**是否进仓库。** 不进。

## 步骤 3 双标抽样

**做什么。** `pipeline/label/sample_double.py` 从清洗结果里去掉 `low_info`，按「应用 × 评分档」分层随机抽样。评分档是固定的：1–2 为 `low`，3 为 `mid`，4–5 为 `high`。每层抽取 `max(1, round(层大小 × ratio))` 条，然后打乱。每条只保留 `id`、`app`、`rating`、`text`。抽样不看任何模型的标注。

**命令。**

```bash
python pipeline/label/sample_double.py --src data/clean/reviews.jsonl --out data/double --ratio 0.1 --chunk 50 --seed 42
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--src` | `data/clean/reviews.jsonl` | 清洗结果 |
| `--out` | `data/double` | 输出目录 |
| `--ratio` | `0.1` | 每层抽样比例 |
| `--chunk` | `50` | 每块条数 |
| `--seed` | `42` | 随机种子 |

**输入。** `data/clean/reviews.jsonl`。

**输出。**

- `data/double/sample.jsonl`
- `data/double/chunks/chunk-00.jsonl`（两位序号）

标准输出打印抽样条数、层数和块数。已有的旧分块文件不会被删掉；重跑前如果块数变少，先清掉 `data/double/chunks/`。

**是否进仓库。** 不进。

## 步骤 4 Codex / Grok 标注

标注规范在 `docs/genome/agentic-product-genome-v0.2.md`，合法取值在 `pipeline/label/genome.json`（当前 `version` 为 `0.2.2`）。角色约定见 `docs/genome/annotation-protocol.md`：Codex CLI 主标注全量，Grok CLI 只独立复标双标样本。复标者只看到规范和原文。

`pipeline/label/run_annotators.sh` 会先 `cd` 到仓库根目录。用法写在脚本头部：

```bash
bash pipeline/label/run_annotators.sh <数据目录> <标注者,逗号分隔> [并发数，默认 5]
```

环境变量：`CODEX_BIN`（默认 `codex`）、`GROK_BIN`（默认 `grok`）、`GENE`（默认空）。需要本机已经登录的 Codex CLI 和 Grok CLI。脚本里没有登录命令。

名字是 `codex` 时执行：

```bash
"$CODEX_BIN" exec -C "$PWD" -s workspace-write -o "$DIR/logs/$tag-$n.final.md" - < "$brief"
```

`-` 表示 brief 从标准输入送入。其他名字都执行：

```bash
"$GROK_BIN" -p "$(cat "$brief")" --always-approve --cwd "$PWD" --disable-web-search
```

`GENE` 为空时，brief 模板是 `pipeline/label/annotate-brief.md`，输出目录是 `<数据目录>/<标注者>/`。`GENE` 有值时，模板换成 `pipeline/label/annotate-gene-brief.md`，输出目录是 `<数据目录>/<标注者>-<基因>/`。模板里的 `{IN}`、`{OUT}`、`{GENE}` 会被替换。

已有输出且 `check_labels.py` 通过的分块会跳过，中断后重跑可以续上。要重标某一块，先删掉对应输出文件。并发由第三个参数限制，默认 5。日志在 `<数据目录>/logs/`，展开后的 brief 在 `<数据目录>/briefs/`。

手动校验（脚本内部用 `python3 -I` 调用同一文件）：

```bash
python pipeline/label/check_labels.py <输入 chunk> <标注输出> [只检查的基因，逗号分隔]
```

前两个是位置参数。第三个可选；不写就检查 `genome.json` 里的全部基因。通过时打印 `OK` 并以退出码 0 结束。

### 主标注

先把双标样本以外的待标评论切块。`split_full.py` 只依赖步骤 3 的 `sample.jsonl`，不依赖复标是否跑完。它跳过 `low_info`，也跳过已出现在双标样本里的 `id`。

```bash
python pipeline/label/split_full.py --src data/clean/reviews.jsonl --sample data/double/sample.jsonl --out data/full --chunk 50
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--src` | `data/clean/reviews.jsonl` | 清洗结果 |
| `--sample` | `data/double/sample.jsonl` | 要排除的双标样本 |
| `--out` | `data/full` | 输出目录 |
| `--chunk` | `50` | 每块条数 |

输出是 `data/full/chunks/chunk-000.jsonl`（三位序号），字段仍是 `id`、`app`、`rating`、`text`。旧分块同样不会自动删除。

主标注跑两处：双标样本目录，以及上面切出的其余全量。

```bash
bash pipeline/label/run_annotators.sh data/double codex 5
bash pipeline/label/run_annotators.sh data/full codex 5
```

输出：

- `data/double/codex/chunk-00.jsonl`
- `data/full/codex/chunk-000.jsonl`

每行包含 `id` 和 `genome.json` 中的基因字段。`relevant` 为 `off_topic` 时，模板允许省略其余字段。

### 复标

Grok 只标双标样本，与 Codex 分开写目录：

```bash
bash pipeline/label/run_annotators.sh data/double grok 5
```

输出：`data/double/grok/chunk-00.jsonl`。

双标目录也可以一次交给两个人，这是脚本头部的例子。效果与上面的 `data/double` 两次调用相同：

```bash
bash pipeline/label/run_annotators.sh data/double codex,grok 5
```

### 单基因重标

协议约定：某个基因的一致性不合格时，先改规范，再由主标注者只重标该基因。`GENE` 设为 `genome.json` 里的基因 `id`。下面用 `g17_risk`，因为它是步骤 6 的 `--relabeled` 默认值。

```bash
GENE=g17_risk bash pipeline/label/run_annotators.sh data/double codex 5
GENE=g17_risk bash pipeline/label/run_annotators.sh data/full codex 5
```

输出：

- `data/double/codex-g17_risk/chunk-00.jsonl`
- `data/full/codex-g17_risk/chunk-000.jsonl`

每行是 `id` 加上这一个基因。校验第三个参数传同一个基因 id。

**是否进仓库。** `data/double/`、`data/full/` 及其日志、brief、标注结果都不进仓库。模板 `annotate-brief.md`、`annotate-gene-brief.md` 和 `genome.json` 进仓库。

## 步骤 5 一致性与裁决

**做什么。** `pipeline/label/agreement.py` 比较多方标注。`--ann` 可重复，格式是 `名字=路径`（文件或目录），第一个是主标注。样本先取各方 id 的交集；某一方没有这条 id，该样本不进入交集。各方都有这条 id、但 `check_labels.check` 判定整条不合法时，记为「没能判定」，单独计数，不进入 κ。单基因重标目录只有一个字段，直接作为 `--ann` 会整条变成没能判定。仓库里没有把重标基因叠回原标注再重算一致性的脚本。

指标：单选基因算两两 Cohen's κ，三方及以上时另算 Fleiss' κ；`rating`（情绪强度）算加权 κ；多选基因算逐标签平均 κ 和逐条平均 Jaccard；文本基因不算 κ，只数每方有多少条写了 `Agent 应当`。`relevant` 用全部可用样本，其余基因只用各方都标成相关的样本。

脚本只写出数值。合格线在 `docs/genome/annotation-protocol.md` 第 4 节：κ ≥ 0.6 合格；0.4–0.6 要修订该基因的定义；< 0.4 要重写定义。

合并规则在同一脚本里，对应协议第 5 节：最终标签先取第一个标注者。各方都标成相关时，`g5_touchpoint` 完全没有交集、`g15_solvable` 落在两个不同的具体层（含 `mixed` 则不算）、`g16_severity` 不一致，才会进入 `needs_review`。相关性本身不一致时，`needs_review` 为 `relevant`。

**命令。**

```bash
python pipeline/label/agreement.py --ann codex=data/double/codex --ann grok=data/double/grok --out data/double/report
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--ann` | 必填，可重复 | `名字=路径`，第一个是主标注 |
| `--out` | `data/double/report` | 报告目录 |

**输入。** `data/double/codex/`、`data/double/grok/`。

**输出。**

- `data/double/report/agreement.json`：样本量、可用量、各方都标成相关的数量（字段名 `both_relevant`）、各方没能判定的数量、各基因指标、`needs_review` 条数。
- `data/double/report/merged.jsonl`：每行有 `id`、主标注 `labels`、`needs_review`、各方 `raw`。

标准输出打印 `sample`、`usable`、`both_relevant`、`undetermined`、`needs_review`。

**裁决。** `pipeline/label/review_argilla.py` 把 `needs_review` 非空的样本推到 Argilla，人提交后再拉回。数据集名是 `genome-review-v` 加上 `genome.json` 的 `version`（当前为 `genome-review-v0.2.2`）。题目是 `relevant`（必填）以及 `g5_touchpoint`、`g15_solvable`、`g16_severity`。建议值固定读取合并结果里的 `raw["codex"]`。先导出环境准备里的 Argilla 变量。

推送可以在步骤 6 之前做。拉回会改写 `data/labeled/genome-final.jsonl`，所以放在步骤 6 生成该文件之后。

```bash
python pipeline/label/review_argilla.py push --merged data/double/report/merged.jsonl --src data/clean/reviews.jsonl --final data/labeled/genome-final.jsonl --decisions data/labeled/review-decisions.jsonl
python pipeline/label/review_argilla.py pull --merged data/double/report/merged.jsonl --src data/clean/reviews.jsonl --final data/labeled/genome-final.jsonl --decisions data/labeled/review-decisions.jsonl
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `action` | 必填，`push` 或 `pull` | 位置参数 |
| `--merged` | `data/double/report/merged.jsonl` | 一致性合并结果；`push` 使用 |
| `--src` | `data/clean/reviews.jsonl` | 清洗文本；`push` 使用 |
| `--final` | `data/labeled/genome-final.jsonl` | 最终标注；`pull` 读入并覆盖 |
| `--decisions` | `data/labeled/review-decisions.jsonl` | `pull` 写下的裁决 |

`pull` 只采用状态为 `submitted` 的回答，写入 `--decisions`，把这些值覆盖进最终标注的 `labels`，并加上 `review`（`decided` 与覆盖前的原值）。标准输出打印拉回条数，以及其中有多少条改动了主标注。

**是否进仓库。** 不进。

## 步骤 6 合并最终标注

**做什么。** `pipeline/label/merge_final.py` 把主标注在 `data/full/<主标注者>/` 和 `data/double/<主标注者>/` 的 JSONL 按 `id` 合并。`--relabeled` 里的每个基因，若同目录下存在 `<主标注者>-<基因>/`，则用其中的值覆盖；`relevant` 为 `off_topic` 的样本不覆盖。重标目录缺失或没有该 `id` 时，保留主标注原值，并计入 `missing_relabel_<基因>`。默认基因是 `g17_risk`。还没有做单基因重标时，把 `--relabeled` 传成空字符串，覆盖列表为空。

`--review` 文件存在时，用它填写 `needs_review`；`id` 在该文件中则 `in_double_sample` 为真。文件不存在时 `needs_review` 为空列表，`in_double_sample` 为假，其余记录仍会写出。没有主标注的 `id` 不写出，计入 `missing`。校验不通过的记录仍写出，计入 `invalid`。`low_info` 不进入结果。`relevant` 为 `yes` 的计入 `relevant`，其余计入 `off_topic`。

**命令。**

```bash
python pipeline/label/merge_final.py --main codex --dirs data/full,data/double --relabeled g17_risk --review data/double/report/merged.jsonl --src data/clean/reviews.jsonl --out data/labeled/genome-final.jsonl
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--main` | `codex` | 主标注者目录名 |
| `--dirs` | `data/full,data/double` | 逗号分隔的数据目录 |
| `--relabeled` | `g17_risk` | 逗号分隔的重标基因；空字符串表示不覆盖 |
| `--review` | `data/double/report/merged.jsonl` | 步骤 5 的合并文件 |
| `--src` | `data/clean/reviews.jsonl` | 回填 `app`、`rating`、`date`、`text` |
| `--out` | `data/labeled/genome-final.jsonl` | 最终 JSONL |

**输入。** 主标注目录、可选的 `<主标注者>-<基因>/`、清洗结果、步骤 5 的 `merged.jsonl`。

**输出。** `data/labeled/genome-final.jsonl`。每行有 `id`、`app`、`rating`、`date`、`text`、`labels`、`annotator`、`genome`（`genome.json` 的版本）、`in_double_sample`、`needs_review`。标准输出是计数，其中包括 `relevant`、`off_topic`、`needs_review`、`missing`、`invalid`。

写出之后，再执行步骤 5 的 `pull`，让已提交的裁决覆盖对应标签。

**是否进仓库。** 不进。

## 步骤 7 分布报告

**做什么。** `pipeline/analyze/genome_report.py` 读取最终标注，按基因统计分布和几组交叉，写成 Markdown。相关样本是 `labels.relevant` 为 `yes` 的行，其余计入不相关。各基因分布表的占比以相关样本数为分母；多选基因一条样本可计入多个取值，占比之和可超过 100%。「能力归属 ×『Agent 应当』」的占比以写了「Agent 应当」的条数为分母。各应用的 P0+P1 占比以该应用的相关样本为分母。取值在 `genome.json` 里有中文名时，写成「中文（`代码`）」。

报告开头写规范版本（`genome.json` 的 `version`）、已标注条数、相关与不相关条数、第一条的 `annotator`（文件为空时写「无已标注样本」）、`in_double_sample` 为真的条数、`needs_review` 非空的条数、带 `review` 的条数。正文分四节。「一、人」是 `g1_user`、`g2_motive`、`g3_relation`、`g4_investment`。「二、事」是 `g5_touchpoint`、`g7_trigger`、`g8_emotion`、`g9_voice_type`、`g10_stage`、`g11_value`、`g12_competitor`，以及 `g6_subtouch` 的前 25 个取值。「三、解」是 `g14_capability`、`g15_solvable`、`g16_severity`、`g17_risk`；`g13_expected` 只计含「Agent 应当」或「产品应当」的条数。「四、关键交叉」是一级触点 × 严重度（`p0`、`p1`、`p2`、`none`）、能力归属 ×「Agent 应当」、可解性 × 严重度，以及每个应用的相关样本数、主要触点前 3 和 P0+P1 占比。相关样本为 0 时，G13 的占比写成 0.0%，各表仍保留表头。

报告只含统计数字，不含评论原文。`text` 和 `g13_expected` 的原句都不写入文件。

**命令。**

```bash
python pipeline/analyze/genome_report.py --src data/labeled/genome-final.jsonl --out data/reports/genome-report.md
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--src` | `data/labeled/genome-final.jsonl` | 步骤 6 的最终 JSONL。已执行步骤 5 的 `pull` 时，这是裁决覆盖之后的文件 |
| `--out` | `data/reports/genome-report.md` | 分布报告。父目录不存在时会创建 |

**输入。** `data/labeled/genome-final.jsonl`。

**输出。**

- `data/reports/genome-report.md`：只含统计数字，不含评论原文。
- 标准输出：`报告已写入 <路径>（相关样本 <n> 条）`。

**是否进仓库。** 报告不进。`data/` 被忽略。脚本 `pipeline/analyze/genome_report.py` 进仓库。

协议第 6 节要求质量结论写明样本量、各基因 κ、没能判定的数量、裁决改动的比例。双标样本量、各基因 κ 和没能判定的数量在步骤 5 的 `data/double/report/agreement.json`。`review_argilla.py pull` 的标准输出给出拉回条数，以及其中改动了主标注的条数，用来算裁决改动的比例；这条输出里没有百分数。`merge_final.py` 的标准输出只含相关、不相关、待裁决、缺失、非法等计数。分布报告写的是最终标注各基因的条数和占比。协议第 6 节的这四项仍分别在 `agreement.json` 和 `pull` 的标准输出里，仓库里没有把它们合成一份报告的脚本。

## 附：备用的 OpenAI 兼容接口预标

主路径不使用本节。`docs/genome/annotation-protocol.md` 写明 Kimi 不参与标注；`pipeline/label/prelabel.py` 保留为备用，调用 OpenAI 兼容接口，默认是 Kimi。结果只作为人工校对的建议。

脚本启动时读取 `genome.json` 的 `spec` 字段所指的规范（当前是 `docs/genome/agentic-product-genome-v0.2.md`）。接口密钥是环境变量 `KIMI_API_KEY`。模型与地址可用参数或环境变量覆盖。已写入的 `id` 会跳过；整批失败不写入，再次运行会续跑；接口表明余额不足或账号停用时停止派发新批次。

```bash
python pipeline/label/prelabel.py --src data/clean/reviews.jsonl --out data/labeled/prelabels.jsonl --model kimi-k2.7-code-highspeed --base-url https://api.moonshot.cn/v1 --batch 5 --limit 50 --workers 4
python pipeline/label/prelabel.py --src data/clean/reviews.jsonl --out data/labeled/prelabels.jsonl --model kimi-k2.7-code-highspeed --base-url https://api.moonshot.cn/v1 --batch 5 --limit 0 --workers 4
```

第一条只标前 50 条，对应脚本头部的试跑例子。第二条 `--limit 0` 表示不截断。

| 参数 | 默认 | 含义 |
|---|---|---|
| `--src` | `data/clean/reviews.jsonl` | 清洗结果；会跳过 `low_info` |
| `--out` | `data/labeled/prelabels.jsonl` | 预标 JSONL |
| `--model` | 环境变量 `PRELABEL_MODEL`，否则 `kimi-k2.7-code-highspeed` | 模型名 |
| `--base-url` | 环境变量 `PRELABEL_BASE_URL`，否则 `https://api.moonshot.cn/v1` | OpenAI 兼容接口根地址 |
| `--batch` | `5` | 每次请求的样本数 |
| `--limit` | `0` | 只标前 N 条；`0` 表示不限制 |
| `--workers` | `4` | 并发请求数 |

每行输出有 `id`、`labels`、`undetermined`（没能通过校验的基因）、`model`、`genome`。

导入 Argilla 用 `pipeline/label/to_argilla.py`。预标文件存在且读到至少一条时，只导入其中出现的 `id`；文件不存在或为空时，导入全部非 `low_info` 样本。空的建议（`null`、空字符串、空数组）不挂到记录上。数据集不存在时按 `genome.json` 创建。

```bash
python pipeline/label/to_argilla.py --src data/clean/reviews.jsonl --pre data/labeled/prelabels.jsonl --name genome-v0.2.2 --limit 0
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--src` | `data/clean/reviews.jsonl` | 清洗结果 |
| `--pre` | `data/labeled/prelabels.jsonl` | 预标文件；可以不存在 |
| `--name` | `genome-v` 加上 `genome.json` 的 `version` | Argilla 数据集名。当前版本下默认是 `genome-v0.2.2` |
| `--limit` | `0` | 只导入前 N 条；`0` 表示不限制。脚本头部另有示例 `--limit 200` |

**是否进仓库。** `data/labeled/` 不进仓库。
