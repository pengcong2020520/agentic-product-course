# Agentic 产品课程

带读者亲手把一个 Agentic 产品从想法做到生产：定义任务与边界 → 先建评测 → 构建 → 护栏与安全 → 上线 → 用线上数据持续改进。

> 课程正在设计中，内容尚未开始编写。

## 当前文档

- [调研：生产级 Agentic 产品的方法论与设计思路](docs/research/methodology.md)
- [开源项目调研（按章节）](docs/research/oss-map.md)
- [课程规划草案（待讨论）](docs/course-plan-draft.md)
- [Agentic 产品基因图谱](s03_product_genome/genome.md)
- [标注与裁决规则](s05_agreement/protocol.md)
- [s01 原始数据采集](s01_raw_data/) → [s02 清洗与去标识](s02_clean/) → [s03 产品基因图谱](s03_product_genome/)
- [s04 独立标注](s04_labeling/) → [s05 一致性与人工裁决](s05_agreement/) → [s06 从标签到产品定义](s06_product_definition/)

## 结构

```text
docs/            调研与设计文档
s01_raw_data/   原始数据采集
s02_clean/      清洗与去标识
s03_product_genome/ 产品基因图谱与标注校验
s04_labeling/   抽样、切块、独立标注与合并
s05_agreement/  一致性、人工裁决与质量报告
s06_product_definition/ 基因分布与人群切片报告
tests/          统一测试与仓库检查
.claude/skills/  课程制作流程 skill（总体设计、阶段交付、章节写法、派活与审查、质量关卡、回顾）
```

## 本地运行

在仓库根目录运行，默认输入与输出位于 `data/`。各章节命令见 `code.py` 顶部 Usage 或 `--help`。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q
```

需要预标或 Argilla 时，复制 `.env.example` 为 `.env`，填写占位值并加载环境变量。

## License

MIT
