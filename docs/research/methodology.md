# 调研：生产级 Agentic 产品的方法论与设计思路

> 调研日期：2026-11-09。只收录有出处的结论；数字标明来源，第三方转述的标"转述"。本文是课程设计的依据，不是课程正文。

## 1. 一句话结论

业界的共识已经从"怎么让 Agent 跑起来"转到"怎么让 Agent 可靠、可度量、可持续变好"。生产级 Agentic 产品的核心不是框架，而是四件事：**定义清楚的任务与边界、先于代码的评测、由自己掌控的上下文与控制流、从线上回流的数据闭环。**

## 2. 七条主流方法论

### 2.1 从最简单的方案开始，按需增加自主性
- Anthropic《Building effective agents》区分 **Workflow**（代码决定步骤）与 **Agent**（模型在运行时决定步骤），给出五种工作流模式：提示链、路由、并行、编排者-执行者、评估者-优化者。原则是"找最简单的可行方案，只在需要时增加复杂度"；成功的实现大多用简单、可组合的模式，而不是复杂框架。
- 同文附录：做 SWE-bench Agent 时，花在**优化工具**上的时间多于优化整体提示词。
- 实践建议（转述）：先做非 Agent 版本，用户测试里失败了再引入 Agent。

### 2.2 Agent 主要是软件：掌控上下文、状态与控制流
- 12-Factor Agents（Dex Horthy）：自己掌控提示词、上下文窗口、工具调用、状态、人工审批与控制流；"好的 Agent 大部分是软件，只在有杠杆的地方插入 LLM 步骤"。要点：工具调用即结构化输出、状态统一、可暂停/恢复、把"联系人"建模为工具调用、Agent 小而专注（3–10 步）、把错误压缩进上下文、Agent 是无状态 reducer（可重放）。
- Anthropic《Effective context engineering for AI agents》：上下文是有限而珍贵的资源；工具描述写不好会把 Agent 带偏（转述：一个测试 Agent 改写工具描述后任务耗时降 40%）。

### 2.3 单 Agent 还是多 Agent：取决于任务形态
- Anthropic 多 Agent 研究系统：主 Agent 规划并并行派出 3–5 个子 Agent，各自独立上下文，最后单独做引用核对；内部研究评测上比单 Agent 好 90.2%，token 约为对话的 15 倍；需要共享上下文、依赖多的任务不适合多 Agent。
- Cognition《Don't Build Multi-Agents》：可靠性的核心是上下文工程；子 Agent 看不到彼此完整上下文时会做出冲突决定。
- 调和（Phil Schmid 等）：**可并行、少依赖的任务（研究）适合多 Agent；串行、共享产物的任务（写代码）适合单线程 Agent。** 2026 年 Cognition 也推出"协调者 + 隔离执行者"的形态。
- 转述：多数产品里两个 Agent 的串行链好于十个 Agent 的编排。

### 2.4 评测先于代码，评测驱动迭代
- Anthropic《Demystifying evals for AI agents》（2026-01）：三类评分器——代码（单测、正则、状态校验）、模型（带 rubric 或两两比较，需用人工校准）、人工；每个任务要有参考解，证明任务可解、评分器配置正确；**多次运行 0% 通过往往是任务坏了**；能力评测从低通过率起步，饱和后"毕业"进回归评测（目标近 100%）。
- **pass@k vs pass^k**：pass@k 是 k 次至少一次成功（适合可重试的研究助手）；pass^k 是 k 次全部成功（适合面向客户、要求稳定的 Agent）；单次 75% 的 pass^3 只有 42%。
- 评测轨迹而非只看答案；多 Agent 系统要加移交（handoff）评测（转述）。
- 构建顺序（转述，Rottmann）：窄场景 → 确定工具与数据 → **先建评测集** → 最小 Agent 循环 → 迭代到评测变绿 → 加人工复核 → 上线；首轮 ≥30 条、上线前 ≥100 条真实用例。
- 行业现状（转述，LangChain 2026 报告）：只有 52.4% 的团队做离线评测、37.3% 做线上评测。

### 2.5 错误分析是评测的起点，数据飞轮是目的
- Hamel Husain & Shreya Shankar：**"从错误分析开始，而不是从基础设施开始"**。读约 30 条 trace → 开放编码（逐条标注问题）→ 轴向编码（归纳失败模式）→ 按失败模式建评估器 → 用人工标签校准 LLM 评判（TPR/TNR）→ 循环。没有线上数据时先合成输入。
- 飞轮：建数据集 → 标注通过/失败与理由 → 修明显问题 → 建评估器 → 再做错误分析 → 重复。

### 2.6 仿真、影子与持续发布
- Sierra τ-bench：真实数据库与工具 API + 业务政策文档 + LLM 模拟用户；**按最终数据库状态与动作评分，不按对话文本**；用 pass^k 衡量稳定性。Sierra 提出"Agent 开发生命周期"：用会话仿真器回放成百上千段对话做回归，配合版本与发布管理。
- Decagon：自然语言写的业务流程（AOP）编译成可执行逻辑；模拟客户人设做端到端仿真、A/B、版本管理与持续 QA 监控。
- 影子测试（转述）：新模型/新版本与线上并行跑同样输入，达到或超过基线才切换。

### 2.7 护栏、人工介入与安全
- OpenAI《A practical guide to building agents》：护栏是分层防御（相关性、安全分类、PII 过滤、内容审核、按风险分级的工具保护、规则、输出校验）；从隐私与内容安全起步，按真实失败逐步加。人工介入的两个触发：**超过失败阈值**、**高风险动作**（不可逆、敏感、高额）。
- Simon Willison 的"致命三要素"：同时拥有私有数据、读取不可信内容、能向外发送数据的 Agent 会被提示注入利用。防御是结构性的：任何一个 Agent 上下文不同时具备三要素；模型层防护不可能 100%（Anthropic 2026 文章，转述）。

## 3. 代表性 Agentic 产品格局（2026）

| 类别 | 代表产品 | 规模（多为第三方估算，仅作参考） | 设计特征 |
|---|---|---|---|
| 编码 Agent | Cursor、Claude Code、Devin、Replit、Lovable、GitHub Copilot | 最大品类；Cursor 年化收入估计 30–40 亿美元，Claude Code 超 25 亿美元，Devin 超 10 亿美元 | 单线程长任务、沙箱执行、测试即评测 |
| 客服 Agent | Sierra、Decagon、Intercom Fin、Salesforce Agentforce | 第二梯队；Sierra、Decagon 约 1–2 亿美元；Fin 按"每次解决 0.99 美元"计费 | 政策 + 工具 + 人工移交；仿真评测；按结果计费 |
| 深度研究 / 通用 Agent | OpenAI/Gemini Deep Research、Manus、Genspark、Perplexity | Genspark 超 2.5 亿美元 | 规划者 + 并行子 Agent、浏览器/代码沙箱、反思与引用核对 |
| 垂直专业 Agent | Harvey（法律） | 约 4 亿美元 | 领域数据、专家评测、合规 |

## 4. 生产级 Agentic 产品的完整步骤（综合以上来源）

1. **选任务**：价值高、可验证、错误可恢复；先判断要不要做成 Agent（Workflow 够用就用 Workflow）。
2. **定边界与成功标准**：能做什么、不能做什么、何时转人工；成功用可检查的结果定义（最好是状态或产物，而不是措辞）。
3. **先建评测**：真实或合成用例、参考解、评分器（代码 > 模型 > 人工），选 pass@k 或 pass^k。
4. **最小可用 Agent**：一个循环 + 少量设计良好的工具；自己掌控上下文与状态。
5. **按需增加结构**：路由、并行、编排者-执行者、评估者-优化者；只有任务可并行、少依赖时才拆多 Agent。
6. **护栏与人工介入**：分层护栏、工具风险分级、高风险动作审批、失败阈值转人工；按"致命三要素"做结构隔离；对抗测试。
7. **可观测**：每次运行留 trace（输入、上下文、工具调用、产物、成本、延迟）。
8. **上线**：上线清单（评测通过线、安全测试、成本预估、回滚）、影子流量、灰度、版本管理。
9. **线上评测与运营指标**：解决率/任务完成率、转人工率、成本、延迟、用户反馈。
10. **数据闭环**：错误分析 → 失败模式归类 → 标注 → 新评测用例与改进（提示词、工具、知识、模型）→ 回归 → 再发布。

## 来源

- [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)
- [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic: Demystifying evals for AI agents（摘要）](https://ai-eval.org/deep-dive/anthropic-demystifying-evals-for-ai-agents)
- [OpenAI: A practical guide to building agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)
- [Cognition vs Anthropic（Latent Space）](https://latent.space/p/ainews-legacy-25-06-13-cognition-vs-anthropic)
- [Phil Schmid: Single vs Multi-Agent System?](https://www.philschmid.de/single-vs-multi-agents)
- [12-Factor Agents 解读（TianPan.co）](https://tianpan.co/blog/2026-01-26-12-factor-agents-production-ai)
- [Hamel Husain & Shreya Shankar: AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/evals-faq.pdf)
- [Decoding AI: Build an AI evals dataset with error analysis](https://www.decodingai.com/p/build-an-ai-evals-dataset-with-error-analysis)
- [Sierra: τ-bench](https://sierra.ai/blog/tau-bench-shaping-development-evaluation-agents)
- [Sequoia Training Data: Clay Bavor (Sierra)](https://sequoiacap.com/podcast/training-data-clay-bavor)
- [Fin: Sierra vs Decagon vs Ada（竞品方撰写，可能有偏）](https://fin.ai/learn/sierra-vs-decagon-vs-ada)
- [Mastra: AI Agent Evaluation](https://mastra.ai/articles/ai-agent-evaluation)
- [Kay Rottmann: Building AI Agents – practical guide 2026](https://www.kay-rottmann.de/en/blog/building-ai-agents-practical-guide/)
- [PM Toolkit: Building Agentic Products 2026](https://pmtoolkit.ai/learn/ai-modern-pm/building-agentic-products-architecture)
- [Cosmonic: The lethal trifecta](https://cosmonic.com/ai-sandbox/principles/lethal-trifecta/)
- [AI Agent Revenue 2026（第三方估算）](https://agentunfolded.com/ai-agent-revenue/)
- [Top agentic AI startups by revenue（第三方估算）](https://newmarketpitch.com/blogs/news/agentic-ai-top-revenue)
- [Awesome-Deep-Research](https://github.com/DavidZWZ/Awesome-Deep-Research)
