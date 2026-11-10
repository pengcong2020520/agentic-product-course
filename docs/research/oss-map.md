# 调研：可复用的开源项目（按章节）

> 调研日期：2026-11-10。星标与最近更新时间取自 GitHub API。原则：**能复用开源就复用，只写产品自己的业务逻辑**。每章开工前再做一次深度调研（读源码、跑示例、核对许可证与版本），本表是第一轮筛选。

## 底座

| 用途 | 项目 | ★ / 最近更新 / 许可 | 说明 |
|---|---|---|---|
| Agent harness | [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | 30.6k / 2026-11 / MIT | Agent、Runner、Session、Guardrail、Handoff、Tracing、Voice；2026-04 起内置 Codex 式 harness 与沙箱（`agents.sandbox`） |
| 模型接入 | [BerriAI/litellm](https://github.com/BerriAI/litellm) | 63.0k / 2026-11 / 混合 | Agents SDK 通过 LiteLLM 接国内模型（需核实目标模型的工具调用兼容性） |
| Web 服务 | [fastapi/fastapi](https://github.com/fastapi/fastapi) | 104.6k / 2026-11 / MIT | API 与流式输出 |
| 飞书 | [larksuite/oapi-sdk-python](https://github.com/larksuite/oapi-sdk-python) | 568 / 2026-10 / MIT | 官方 SDK：机器人事件、长连接、消息卡片 |
| 飞书参考 | [ConnectAI-E/feishu-openai](https://github.com/ConnectAI-E/feishu-openai) | 5.6k / 2025-07 / GPL-3.0 | 只作参考（GPL，不复制代码）：语音、角色扮演的交互设计 |

## 评测体系

| 用途 | 项目 | ★ / 更新 / 许可 | 说明 |
|---|---|---|---|
| 离线评测主框架 | [confident-ai/deepeval](https://github.com/confident-ai/deepeval) | 19.4k / 2026-11 / Apache-2.0 | pytest 风格；多轮对话指标；会话模拟器；G-Eval 自定义评判 |
| 用户仿真参考 | [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench) | 2.4k / 2026-11 / MIT | 模拟用户 + 按状态评分 + pass^k 的参考实现 |
| 红队 | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | 27.0k / 2026-11 / MIT | 越狱、注入、有害内容的自动化红队 |
| 漏洞扫描 | [NVIDIA/garak](https://github.com/NVIDIA/garak) | 10.0k / 2026-11 / Apache-2.0 | 模型层漏洞探测 |
| 线上评测与可观测 | [langfuse/langfuse](https://github.com/langfuse/langfuse) | 37.2k / 2026-11 / MIT 核心 | 自托管；trace、数据集、标注队列、线上 LLM 评判、成本 |
| 备选 | [comet-ml/opik](https://github.com/comet-ml/opik)、[Arize-ai/phoenix](https://github.com/Arize-ai/phoenix)、[UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai)、[Giskard-AI/giskard-oss](https://github.com/Giskard-AI/giskard-oss) | — | 对比后定 |

## 记忆

| 项目 | ★ / 更新 / 许可 | 说明 |
|---|---|---|
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | 68.7k / 2026-11 / Apache-2.0 | 首选：抽取、更新、检索；支持 pgvector |
| [MemTensor/MemOS](https://github.com/MemTensor/MemOS) | 12.3k / 2026-11 / Apache-2.0 | 国内团队；记忆生命周期 |
| [getzep/graphiti](https://github.com/getzep/graphiti) | 32.7k / 2026-11 / Apache-2.0 | 时序知识图谱（关系、事实随时间变化） |
| [letta-ai/letta](https://github.com/letta-ai/letta) | 25.4k / 2026-10 / Apache-2.0 | 自编辑记忆，可作对照 |
| [memodb-io/memobase](https://github.com/memodb-io/memobase) | 3.0k / 2026-01 / Apache-2.0 | 用户画像式记忆，适合陪伴；更新较少 |
| [pgvector/pgvector](https://github.com/pgvector/pgvector)、[FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | — | 向量存储与中文向量模型（BGE） |

## 语音

| 项目 | ★ / 更新 / 许可 | 说明 |
|---|---|---|
| Agents SDK `VoicePipeline` | — | STT → Agent → TTS；可换成自定义 STT/TTS。Realtime API 在国内不可用，主线走流水线 |
| [modelscope/FunASR](https://github.com/modelscope/FunASR) | 21.0k / 2026-11 / MIT | 中文语音识别 |
| [QwenAudio/CosyVoice](https://github.com/QwenAudio/CosyVoice) | 24.4k / 2026-05 / Apache-2.0 | 中文语音合成，情感与音色 |
| [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)、[livekit/agents](https://github.com/livekit/agents) | 17.2k / 15.2k | 实时语音备选（打断、VAD） |

## 安全、隐私与数据

| 项目 | ★ / 更新 / 许可 | 说明 |
|---|---|---|
| [NVIDIA-NeMo/Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | 7.5k / 2026-11 | 对话护栏（与 SDK 自带 guardrail 对比后定） |
| [protectai/llm-guard](https://github.com/protectai/llm-guard) | 3.2k / 2026-07 / MIT | 输入输出扫描 |
| [data-privacy-stack/presidio](https://github.com/data-privacy-stack/presidio) | 11.8k / 2026-11 / MIT | PII 识别与脱敏（需补中文识别器：手机号、身份证） |
| [thu-coai/ShieldLM](https://github.com/thu-coai/ShieldLM)、[thu-coai/SafetyBench](https://github.com/thu-coai/SafetyBench) | — | 中文安全检测与评测 |
| [HumanSignal/label-studio](https://github.com/HumanSignal/label-studio)、[argilla-io/argilla](https://github.com/argilla-io/argilla) | 28.7k / 5.2k | 打标（先用 Langfuse 标注队列，不够再引入） |

## 情感支持与危机相关数据（只用于评测，逐个核实许可）

| 项目 | 许可 | 说明 |
|---|---|---|
| [thu-coai/Emotional-Support-Conversation](https://github.com/thu-coai/Emotional-Support-Conversation)（ESConv） | 需核实 | 情感支持策略标注，可做共情评判 rubric 的依据 |
| [thu-coai/PsyQA](https://github.com/thu-coai/PsyQA) | 未声明 | 中文心理支持问答 |
| [qiuhuachuan/smile](https://github.com/qiuhuachuan/smile) | CC0 | 中文多轮心理支持对话 |
| [CAS-SIAT-XinHai/CPsyCoun](https://github.com/CAS-SIAT-XinHai/CPsyCoun) | CC-BY-4.0 | 中文多轮咨询对话与评测 |
| [scutcyr/CPED](https://github.com/scutcyr/CPED) | 需核实 | 中文人格与情绪标注对话 |
| [HongzhiQ/FineGrainedSuicideDetection](https://github.com/HongzhiQ/FineGrainedSuicideDetection)（SOS-1K） | 需核实 | 中文自杀风险分级，可做危机识别评测 |

## 待核实

- 国内模型（如 DeepSeek、Kimi、Qwen、GLM）经 LiteLLM 接 Agents SDK 时的工具调用、流式与 guardrail 兼容性；
- Agents SDK 默认把 tracing 上报到 OpenAI，国内需关闭并改接 Langfuse；
- 飞书机器人能否收发语音消息、消息格式与时长限制。
