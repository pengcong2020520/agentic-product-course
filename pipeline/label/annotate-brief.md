# 任务：按《Agentic 产品基因图谱 v0.2.2》独立标注一批用户评论

工作目录 = 项目根目录。只写 `{OUT}`，不改任何其他文件，不 git commit，不安装依赖。

## 先读
1. `docs/genome/agentic-product-genome-v0.2.md`（标注规范 v0.2.2，必须完整读完，尤其是各基因的"判定规则"）
2. `pipeline/label/genome.json`（每个基因的 id、类型与合法取值）
3. `docs/genome/annotation-protocol.md` 第 3 节（复标者规则）

## 要做的事
输入：`{IN}`，每行一条评论 `{"id","app","rating","text"}`，共约 50 条。

逐条阅读原文，**自己判断**后标注。严禁写脚本调用任何模型，严禁用关键词规则批量打标。
看不出来就选 unknown / none，不猜。

输出：`{OUT}`，JSONL，每行一个对象，包含 `id` 与 genome.json 中全部基因字段：
- single：一个取值字符串；multi：取值数组（至少一个值，g6_subtouch 与 g17_risk 可为空数组）；
- g8_intensity：1/2/3；g13_expected：字符串（"Agent 应当……"或"产品应当……"，可为空）；
- g6_subtouch 只能选所选 g5_touchpoint 之下的二级值；relevant 为 off_topic 时其余字段可省略。
输入有几条，输出就必须有几行，id 一一对应。

## 验收（写完后自己检查）
运行：`python3 -I pipeline/label/check_labels.py {IN} {OUT}`，必须输出 "OK"。不 OK 就修正后再检查。
