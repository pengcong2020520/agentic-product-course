# Agentic 产品基因图谱 v0.2.2（标注规范）

> 用途：把原始数据集里的每一条用户声音，拆成一组可统计的"基因"。基因的分布决定产品为谁做、解决什么、做到哪里为止；"期望行为"与"能力归属"两个基因直接长成评测集的用例，并对应到中台与应用的具体能力。
>
> v0.2 相对 v0.1：体验触点拆成**一级 12 类 + 二级 59 个细分基因（另加每个一级的 `.other`）**；新增角色关系、投入程度、触发情境、情感价值、竞品参照、能力归属、严重度 7 个基因；多选基因必须至少给一个值（看不出来选 `unknown`）。示例均为改写，不是评论原文。

## 结构：三条链、十八个基因

```text
 人  ── G1 用户画像 · G2 使用动机 · G3 角色关系 · G4 投入程度
 事  ── G5 体验触点（一级）· G6 体验触点（二级）· G7 触发情境 · G8 情绪与强度
        G9 声音类型 · G10 关系阶段 · G11 情感价值 · G12 竞品参照
 解  ── G13 期望的 Agent 行为 · G14 能力归属 · G15 可解性 · G16 严重度 · G17 风险信号
 （G0 相关性：先判断，不相关就跳过其余基因）
```

### G0 相关性（单选，必填）
`yes` 与陪伴产品的使用体验相关 · `off_topic` 不相关，其余基因省略。

判定规则（v0.2.1 补充）：
- 通用助手（如豆包）的**纯工具使用**——解题、搜题、写作、生图、报税、翻译、事实问答——标 `off_topic`，即使评论里有情绪或差评；
- 同一条评论里只要涉及陪伴、情绪、角色、智能体、人设或关系，就标 `yes`（此时可同时标 `tool_user`）；
- 乱码、与产品无关的内容标 `off_topic`。

**通用规则**：只标评论里有依据的内容；看不出来选 `unknown`，自由文本留空；不猜、不补。

---

## 人：谁在说、为什么用

### G1 用户画像（多选）
| 值 | 判定依据 |
|---|---|
| `dream_partner` 梦女 / 乙女向 | 把角色当恋人、梦角、追星寄托 |
| `creator` 角色创作者 | 自己写人设、做智能体、上传角色 |
| `story_player` 剧情玩家 | 剧情、故事模式、文游、跑团 |
| `confider` 倾诉者 | 情绪困扰、孤独、找人说话 |
| `power_user` 进阶玩家 | 自带 API、预设、世界书，对比多款产品 |
| `tool_user` 工具型用户 | 学习、搜题、写作等实用目的 |
| `minor_hint` 疑似未成年 | 学生、家长代付、没有银行卡 |
| `unknown` 不明 | — |

### G2 使用动机（多选）
`companionship` 陪伴不孤单 · `emotional_support` 情绪安抚 · `romance` 亲密关系想象 · `roleplay` 剧情扮演 · `escape` 解压 / 逃离现实 · `pastime` 打发时间 · `creation` 创作与分享 · `social` 社区与社交 · `utility` 实用问答 · `unknown`

### G3 角色关系（多选：用户与 AI 角色是什么关系）
`lover` 恋人 · `friend` 朋友 / 知己 · `family` 家人 · `idol` 偶像 / 梦角 · `story_npc` 剧情角色 · `mentor` 导师 / 助手 · `pet` 宠物 / 萌物 · `unknown`

判定规则（v0.2.1 补充）：乙女 / 梦女 / 乙游、恋爱等级或好感等级、"老公""宝宝"等亲密称呼 → `lover`；追星、"梦角"指真实明星 → `idol`；只说"角色""智能体"而看不出关系 → `unknown`。

### G4 投入程度（单选）
| 值 | 判定依据 |
|---|---|
| `trial` 试用 | 刚下载、玩了一会 |
| `regular` 日常使用 | 经常用、每天聊 |
| `heavy` 重度 / 长期 | 用了一年以上、"老玩家"、多个角色长期养成 |
| `paying` 付费用户 | 提到充值、会员、月卡（与时长无关时优先标此项） |
| `unknown` | — |

判定规则（v0.2.1 补充）：**只认明确的说法，不从语气推断**。
- `trial`：明说刚下载、第一次用、试了一下，或注册 / 实名 / 开局付费这类"一进来就卡住"的问题；
- `regular`：明说每天、经常、一直在用、用了几个月；"用着用着""最近"不算；
- `heavy`：明说一年以上、老玩家，或角色等级、养成进度很高；
- `paying`：明说自己充值、开会员、买月卡（看不出自己付没付钱不算）；
- 以上都没有 → `unknown`。

---

## 事：发生了什么

### G5 体验触点 · 一级（多选，最多 3 个，按主次）
`persona` 人设 · `memory` 记忆 · `dialogue` 对话质量 · `agency` 主动与推进 · `moderation` 内容审核 · `voice` 语音 · `creation_tool` 创作工具 · `play_feature` 玩法功能 · `monetization` 商业化 · `reliability` 稳定与数据 · `platform` 平台适配 · `lifecycle` 下线与迁移 · `unknown`

### G6 体验触点 · 二级（多选，必须落在所选一级之下；表里没有合适的，选该一级的 `<一级>.other`）

| 一级 | 二级基因 | 含义（示例为改写） |
|---|---|---|
| persona | `persona.ooc` | 人设漂移、"突然换了个人" |
| | `persona.homogenized` | 角色同质化、"每个人设聊出来都一样" |
| | `persona.setting_ignored` | 关系或背景设定被无视（"恋人变成兄弟"） |
| | `persona.intensity_off` | 性格强度偏差（设定冷淡却过度热情、刻薄） |
| | `persona.gaze_bias` | 性别向偏差、"男凝" |
| | `persona.likeness` | 活人感 / 真人感（正向或负向） |
| memory | `memory.in_session` | 同一会话里转头就忘 |
| | `memory.cross_session` | 跨会话失忆、隔天不记得 |
| | `memory.profile_unused` | 用户设定（名字、身份）没被使用 |
| | `memory.contradiction` | 前后矛盾、剧情接不上 |
| | `memory.long_term_request` | 希望有长期记忆 / 记忆表格 |
| dialogue | `dialogue.ai_flavor` | AI 味、人机感、做作 |
| | `dialogue.repetition` | 重复、固定口癖、执念某个词 |
| | `dialogue.verbosity` | 冗长、描写过度、回复太长 |
| | `dialogue.irrelevant` | 答非所问、逻辑对不上 |
| | `dialogue.tone_hostile` | 语气刻薄、怼用户 |
| | `dialogue.style_pollution` | 颜文字、格式等风格污染 |
| | `dialogue.language` | 中文表达差、翻译腔 |
| | `dialogue.factual` | 事实错误、知识过时 |
| agency | `agency.plot_drive` | 主动推进剧情（正向或不足） |
| | `agency.proactive_care` | 主动关心、主动发消息 |
| | `agency.overreach` | 过度主动、强行推进、乱判失败 |
| | `agency.passive` | 被动、只会接话、无聊 |
| moderation | `moderation.false_positive` | 日常对话被误拦 |
| | `moderation.deflection` | "我们换个话题吧" |
| | `moderation.creation_rejected` | 创作 / 上传被判违规 |
| | `moderation.too_loose` | 希望更严格（如未成年保护） |
| voice | `voice.tts_quality` | 配音音色、声音难听或好听 |
| | `voice.call_request` | 希望语音通话 / 更多语音 |
| | `voice.asr_error` | 语音识别异常 |
| | `voice.no_audio` | 没声音、加载失败 |
| creation_tool | `creation_tool.persona_editor` | 人设编辑、改不了设定 |
| | `creation_tool.media` | 头像、立绘、皮肤、图片 |
| | `creation_tool.manage` | 删除、找回、管理角色 |
| | `creation_tool.advanced` | 预设、正则、世界书、自定义 API |
| play_feature | `play_feature.phone_sim` | 小手机 |
| | `play_feature.moments` | 朋友圈 |
| | `play_feature.diary` | 日记 |
| | `play_feature.gift` | 转账、礼物 |
| | `play_feature.story_mode` | 故事 / 剧情模式 |
| | `play_feature.discovery` | 广场、搜索、推荐、浏览记录 |
| monetization | `monetization.quota` | 聊天次数、撤回 / 回溯次数限制 |
| | `monetization.price` | 会员、月卡太贵 |
| | `monetization.ads` | 广告多、关不掉 |
| | `monetization.unexpected_charge` | 莫名扣费、自动续费 |
| | `monetization.early_paywall` | 一上来就收费、没有试用 |
| | `monetization.economy` | 签到、糖果、金币等虚拟货币 |
| reliability | `reliability.crash` | 闪退、卡顿 |
| | `reliability.login` | 登录、验证码、账号 |
| | `reliability.network` | 网络错误、API 报错 |
| | `reliability.message_lost` | 消息被吞、回复空白 |
| | `reliability.data_lost` | 聊天记录、角色、会员丢失 |
| platform | `platform.tablet` | iPad 适配 |
| | `platform.multi_device` | 多端登录 |
| | `platform.os_version` | 系统版本不兼容 |
| | `platform.input` | 输入框、光标、输入法 |
| lifecycle | `lifecycle.feature_removed` | 功能或角色下线 |
| | `lifecycle.model_change` | 换模型、"降智" |
| | `lifecycle.migration` | 被迫迁移到别的产品 |

### G7 触发情境（多选）
`after_update` 更新后 · `first_use` 首次使用 / 注册 · `long_chat` 长时间对话后 · `payment` 付费时 · `creating` 创作 / 上传时 · `returning` 回归后 · `daily` 日常使用中 · `unknown`

### G8 情绪与强度（单选 + 1–3）
`delight` 喜爱 · `satisfied` 满意 · `neutral` 中性 · `disappointed` 失望 · `angry` 愤怒 · `anxious` 害怕失去；强度 1 轻 / 2 中 / 3 强。

### G9 声音类型（单选）
`problem` 问题反馈 · `request` 功能请求 · `expectation` 对 AI 行为的期望 · `praise` 价值肯定 · `comparison` 竞品 / 旧版对比

### G10 关系阶段（单选）
`first_try` 初次体验 · `ongoing` 持续使用 · `veteran` 老用户对比从前 · `churning` 流失 / 准备离开 · `unknown`

判定规则（v0.2.1 补充），按顺序取第一个命中的：
1. `churning`：明说自己卸载、删了、不玩了、换别的产品，或劝别人"避雷""别用"；气话（"干脆停服算了"）不算；
2. `veteran`：拿现在和以前比（"以前……现在……""越更新越差""回不去了"）；
3. `first_try`：刚下载、第一次用、一进来就遇到的问题；
4. `ongoing`：描述正在使用中遇到的情况（"最近""每次""现在"），或在提功能建议；
5. 只有一句评价、看不出处境 → `unknown`。

### G11 情感价值（多选：用户感受到或期待的价值）
`aliveness` 活人感 · `reliance` 精神寄托 · `soothing` 治愈 / 安抚 · `not_alone` 不孤单 · `immersion` 沉浸 / 代入 · `fantasy` 梦想成真 · `achievement` 创作成就 · `fun` 好玩 · `none` 未提及

### G12 竞品参照（多选：评论里提到的其他产品）
`xingye` 星野 · `maoxiang` 猫箱 · `doubao` 豆包 · `zhumengdao` 筑梦岛 · `glow` Glow · `tavern` 酒馆 / SillyTavern · `other` 其他 · `none` 未提及

---

## 解：产品该怎么回应

### G13 期望行为（自由文本，可为空）
对 AI 行为的期望写"Agent 应当……"（**评测集用例的种子**）；对产品功能、商业、工程的期望写"产品应当……"（进入需求池，不进评测集）。一条评论可写多句，用"；"分隔。

### G14 能力归属（多选：要满足 G13，需要哪项能力）
| 值 | 能力 | 对应课程章节 |
|---|---|---|
| `cap.persona` | 人设与角色资产 | 知识、回复编排 |
| `cap.memory` | 记忆基建 | 记忆 |
| `cap.dialogue` | 回复编排 / 对话方法 | 回复编排 |
| `cap.proactive` | 定时任务与主动触达 | 定时任务 |
| `cap.moderation` | 审核策略 | 中台安全（课程不展开合规） |
| `cap.voice` | 语音服务 | 语音 |
| `cap.creation` | 创作工具 | 应用功能 |
| `cap.model` | 模型服务 | 模型服务 |
| `cap.runtime` | 运行底座与数据可靠 | 运行底座 |
| `cap.billing` | 计费与权益 | 商业运营（课程不展开） |
| `none` | 无需能力 | — |

### G15 可解性（单选）
`agent` Agent 设计 · `platform` 中台能力 · `business` 商业与运营 · `mixed` 多层共同

### G16 严重度（单选）
| 值 | 判定依据 |
|---|---|
| `p0` | 导致流失、扣费争议、数据丢失 |
| `p1` | 严重影响核心体验（人设、记忆、对话明显失败） |
| `p2` | 轻微不便、功能建议 |
| `none` | 正面评价、无问题 |

### G17 风险信号（多选，可为空）
`minor` 未成年迹象 · `dependency` 强情感依赖 · `billing_dispute` 扣费争议 · `data_loss` 数据丢失

判定规则（v0.2.2 补充）：**只在评论明说时标注，没有就留空数组**。
| 值 | 标 | 不标 |
|---|---|---|
| `minor` | 明说自己是学生 / 未成年、家长代付、没有银行卡 | 只是语气幼稚、用了网络流行语 |
| `dependency` | 明说把 AI 当唯一或主要的情感依靠："离不开""精神支柱""只有它能倾诉""没有它不行""最难的时候都是它陪着" | 只是长期使用、很喜欢、"像真人"、舍不得某个角色 |
| `billing_dispute` | 扣费不明或未经同意（自动续费、莫名扣钱）、付了钱却没拿到权益、退订或退款困难 | 只是嫌贵、抱怨要充值才能玩、次数太少 |
| `data_loss` | **用户自己的**数据丢失：聊天记录、自建角色、自设、等级进度、已购会员或虚拟币 | 平台下架公共角色或别人的智能体、功能下线（这些标 `lifecycle`） |

---

## 质量要求

- 模型预标 + 人工校对；抽 10% 双人独立标注，按基因计算一致率（目标 Cohen's κ ≥ 0.6）。
- G6 必须落在所选 G5 之下，否则判为没能判定。
- 不一致的样本进入分歧复盘，修订本规范后升版本号；数据集记录所用规范版本。
