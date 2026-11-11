# 任务：按《Agentic 产品基因图谱 v0.2.2》只重标一个基因：{GENE}

工作目录 = 项目根目录。只写 `{OUT}`，不改任何其他文件，不 git commit，不安装依赖。

## 先读
1. `s03_product_genome/genome.md` 中 {GENE} 一节，尤其是"判定规则"表（标什么、不标什么）
2. `s03_product_genome/genome.json` 中 {GENE} 的合法取值

## 要做的事
输入：`{IN}`，每行一条评论 `{"id","app","rating","text"}`。

逐条阅读原文，**自己判断**后只标 {GENE}。严禁写脚本调用任何模型，严禁用关键词规则批量打标。
评论没有明说就给空数组，不猜。

输出：`{OUT}`，JSONL，每行 `{"id": "...", "{GENE}": [...]}`。输入有几条，输出就必须有几行，id 一一对应。

## 验收（写完后自己检查）
运行：`python3 -I s03_product_genome/code.py check {IN} {OUT} {GENE}`，必须输出 "OK"。不 OK 就修正后再检查。
