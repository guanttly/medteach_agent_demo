# 前台交互与后台工作流解耦方案

## 1. 结论

当前 Demo 的核心问题不是某一个接口慢，也不是单纯把超时调短就能解决。问题在架构层：语音/前端交互被后台工作流串行占用，导致数字人沉默、用户无法被即时安抚；同时对话层没有使用完整 session 上下文，导致用户问“有哪些人参加了考试”时，智能体只能按默认方案机械回应。

完整方案必须把系统拆成两条并行通道：

- 前台交互通道：等价于 UI 主线程，只负责即时接话、上下文问答、打断、确认、安抚和播报调度。任何后台任务都不能阻塞它。
- 后台工作流通道：等价于 worker 线程，只负责识别任务后的业务执行、工具调用、状态推进、结果沉淀和进度事件。

前台交互通道必须始终可用。后台工作流无论在调用 DeepSeek、Claude CLI、教学平台接口、TTS，还是等待模拟进度，都只能通过事件把状态告诉前台，不能占用前台响应路径。

## 2. 当前现状

### 2.1 请求链路

当前用户输入链路大致为：

1. 前端调用 `POST /api/demo/message`。
2. 后端路由在 `backend/app/routes/demo.py` 中通过 `spawn(orchestrator.handle_message(...))` 启动后台协程，并立即返回。
3. 页面真正等待的是 WebSocket 事件，而不是 REST 响应。
4. `backend/app/orchestrator.py` 的 `handle_message` 进入同一个串行编排协程。
5. 编排协程依次执行意图识别、演示 delay、方案生成、话术生成、流式播报。

表面上 REST 是异步返回，但用户体验仍被串行后台协程控制。只要协程中间有一段没有发出 `assistant_stream` 或 `assistant_message`，前端就表现为沉默等待。

### 2.2 主要阻塞点

当前安排考试路径中，最明显的沉默窗口在：

- `backend/app/orchestrator.py`：`await agent_brain.generate_arrange_text(...)`
- `backend/app/agent_brain.py`：当 `LLM_PROVIDER=claude_cli` 时调用 `claude_client.run_agent_turn(...)`
- `backend/app/claude_code_client.py`：`proc.communicate()` 最多等待 `CLAUDE_TIMEOUT_SECONDS`

这一步发生在 exam plan 已经有本地默认数据之后。也就是说，系统已经具备可以对用户说话的事实，却为了等一段“更像智能体”的话术而让前台沉默。

### 2.3 交互与工作流割裂

当前编排器既负责业务状态推进，又负责数字人说什么。结果是：

- 工作流慢，前台也慢。
- 工作流忙，用户新问题被 `s.busy` 拦住或被降级处理。
- 工作流状态变化和用户可感知播报没有严格 SLA。
- 数字人播报是工作流步骤的副产品，而不是独立的交互能力。

这违反语音交互的基本原则：语音助手必须先接住用户，再解释后台正在做什么。后台可以慢，前台不能沉默。

### 2.4 上下文缺失

当前 `agent_brain._context_block(...)` 主要包含：

- 当前演示状态
- 是否等待确认
- 默认考试方案

它没有把完整 session facts 注入对话层，例如：

- 已查询到的学员列表
- 当前考试草稿
- 试卷预览
- 下发状态
- 答题进度
- 阅卷结果
- 推荐病例
- 正在运行的后台 job
- 最近几轮用户问题和助教回答

同时 `_CHAT_SYSTEM_PROMPT` 固定要求“顺势引导回安排考试”，这会让很多正常上下文问题被错误处理。例如用户问“有哪些人参加了考试”，正确答案应该直接列出参加人员；当前模型容易复述默认方案或继续引导安排考试。

### 2.5 当前事件模型不足

现有 WebSocket 事件可以驱动画面，但缺少面向交互体验的关键语义：

- 没有 job id，无法把一次用户请求、后台任务、进度事件、最终结果关联起来。
- 没有前台响应 SLA 标记，无法检测“用户说话后 800ms 内是否有助教回应”。
- 没有 heartbeat/progress narration 事件，无法保证慢任务期间持续安抚。
- 没有 interrupt/cancel 语义，用户打断时只能依赖局部 TTS stop，后台任务仍按原流程推进。
- 没有明确区分“给用户听的 utterance”和“给大屏看的 workflow event”。

## 3. 不可妥协的设计目标

1. 前台响应不可阻塞：用户输入后 300-800ms 内必须有可见字幕或语音回应。
2. 后台任务不可直接占用前台：任何 LLM、CLI、工具、平台接口都必须跑在后台 job 中。
3. 慢任务必须持续播报：超过 2 秒没有结果就进入进度安抚；之后每 3-5 秒根据实际状态播报一次。
4. 上下文问答必须准确：任何用户问题都必须基于 session facts 回答，不能只看默认方案。
5. 工作流和对话必须可并发：后台正在创建考试时，用户仍可问“有哪些人”“现在到哪一步”“能不能下发”等问题。
6. 事件必须可追踪：每条用户输入、每个 job、每次口播、每个工具调用都有 correlation id。
7. 支持打断和优先级：用户追问、取消、确认、下发等高优先级输入可以打断低优先级播报。
8. 真实接口失败不等于前台失败：工具失败必须被转成解释、兜底和下一步选择，而不是沉默。
9. TTS 不是业务锁：语音播放队列不能阻止状态更新、文本显示和用户继续提问。
10. 大屏展示和语音助手共享事实源，但展示节奏不能绑死前台对话节奏。
11. 播报不是事件 FIFO：用户回答或长播报期间积累的多条进度/结果，必须先合并、去重、总结，再播报给用户。

## 4. 目标架构

### 4.1 总体分层

目标架构分为七层：

1. Client Interaction Layer
   - 负责麦克风、文字输入、字幕、TTS 队列、打断按钮、状态提示。
   - 只消费事件，不推断业务事实。

2. Conversation Gateway
   - 用户输入的唯一入口。
   - 负责创建 turn id、记录输入、快速 ack、路由到前台问答或后台 job。

3. Context Manager
   - 维护 session facts、对话历史、active jobs、用户确认状态。
   - 对 LLM 暴露结构化上下文，而不是拼一段零散 prompt。

4. Foreground Dialogue Engine
   - 前台主线程。
   - 负责即时回应、上下文问答、确认澄清、打断处理、播报策略。
   - 允许使用低延迟模型，但必须有模板级兜底，不能等待慢模型。

5. Narration Aggregator
   - 负责把后台积累的进度、结果和错误转成“该不该说、说几句、怎么说”。
   - 消费 domain/workflow events，但不逐条照读。
   - 当用户问答、TTS 播放或打断期间积累了多条信息，它必须先压缩成摘要再进入 TTS。

6. Workflow Engine
   - 后台 worker。
   - 负责安排考试、查询学员、创建考试、获取预览、下发、监控进度、阅卷、推荐病例。
   - 只写入 facts 并发事件，不直接控制前台是否沉默。

7. Event Bus
   - 统一分发 domain event、workflow event、utterance event、diagnostic event。
   - 前端、大屏、TTS、日志都从事件流消费。

### 4.2 逻辑结构

```text
User Input
  -> Conversation Gateway
       -> Turn created
       -> Immediate foreground ack
       -> Intent + context routing
            -> Foreground Dialogue Engine
            -> Workflow Engine job

Workflow Engine
  -> Tool calls / LLM / platform APIs
  -> Domain facts updated
  -> Progress events emitted

Narration Aggregator
  -> Collect pending user-visible facts
  -> Coalesce by job/step/fact version
  -> Summarize with LLM or deterministic template
  -> Emit one concise utterance

Event Bus
  -> Avatar subtitles
  -> TTS scheduler
  -> Big screen workflow
  -> Control console
  -> Logs and trace
```

关键点：`Conversation Gateway` 收到用户输入后，不等待 `Workflow Engine` 结果才说话。它先让 `Foreground Dialogue Engine` 接住用户，再把后台任务挂出去。

## 5. 核心数据模型

### 5.1 Session

Session 是单一事实源，应至少包含：

```json
{
  "session_id": "demo_001",
  "conversation": {
    "turns": [],
    "last_user_intent": "arrange_exam",
    "last_assistant_utterance": "",
    "last_interaction_at": 0
  },
  "facts": {
    "exam_plan": null,
    "participants": null,
    "exam_draft": null,
    "exam_preview": null,
    "publish_info": null,
    "progress": null,
    "result": null,
    "recommendation": null
  },
  "workflow": {
    "active_jobs": {},
    "current_stage": "IDLE",
    "steps": []
  },
  "interaction": {
    "need_user_confirmation": false,
    "confirmation_type": null,
    "foreground_state": "idle",
    "speaking": false,
    "current_utterance_id": null,
    "current_utterance_priority": null,
    "interrupt_generation": 0,
    "last_interrupt_at": 0,
    "barge_in_enabled": true
  }
}
```

`facts` 里的信息必须是前台问答的来源。任何“有哪些人”“现在多少人提交”“平均分多少”“下一步做什么”都应该先查 facts，再决定是否调用模型润色。

### 5.2 Job

后台工作必须用 job 表达：

```json
{
  "job_id": "job_20260609_0001",
  "type": "arrange_exam",
  "status": "queued|running|waiting_user|succeeded|failed|cancelled",
  "current_step": "students",
  "progress": {
    "percent": 35,
    "label": "正在查询现场学员"
  },
  "started_at": 0,
  "updated_at": 0,
  "deadline_at": 0,
  "last_user_visible_event_at": 0,
  "cancel_requested": false,
  "error": null
}
```

job 的 `last_user_visible_event_at` 用来驱动安抚口播。如果后台还在跑，但用户可见事件超过阈值未更新，系统必须自动发进度播报。

### 5.3 Turn

每次用户输入都生成 turn：

```json
{
  "turn_id": "turn_0008",
  "session_id": "demo_001",
  "source": "voice|text|control",
  "text": "有哪些人参加了考试",
  "received_at": 0,
  "routed_as": "context_question",
  "related_job_id": "job_20260609_0001",
  "interrupts_utterance_id": "utt_0007",
  "interrupt_policy": "stop_low_priority|stop_all|listen_only|none",
  "first_response_at": 0
}
```

`first_response_at - received_at` 是前台主线程是否健康的核心指标。

如果用户是在智能体发言过程中插话，新的 turn 必须记录它打断了哪条 utterance。后续任何来自旧 utterance 的字幕、音频帧、TTS end 事件、LLM 流式 token，都必须带 generation 校验；generation 已过期则丢弃，不能覆盖新 turn 的字幕和语音。

### 5.4 Pending Narration Item

后台产生的可播报信息不能直接进入 TTS 队列，必须先进入 `pending_narration`：

```json
{
  "item_id": "nar_0012",
  "session_id": "demo_001",
  "job_id": "job_20260609_0001",
  "kind": "progress|result|warning|error|confirmation|answer_followup",
  "priority": "urgent|high|normal|low",
  "fact_path": "facts.progress",
  "fact_version": 7,
  "summary_key": "exam_progress",
  "created_at": 0,
  "expires_at": 0,
  "requires_verbatim": false,
  "payload": {}
}
```

字段规则：

- `summary_key` 用于合并同类信息，例如多条答题进度只保留最新事实并总结趋势。
- `fact_version` 防止旧数据覆盖新数据；同一 `fact_path` 只播最新版本。
- `requires_verbatim=true` 的信息不能被摘要吞掉，例如用户确认请求、严重错误、取消结果。
- `expires_at` 用于丢弃过期进度，例如“正在查询学员”在学员名单已经返回后不应再播。

Narration Aggregator 从 `pending_narration` 中取信息，而不是从 TTS 队列中取句子。TTS 队列只接受最终要播报的 utterance。

## 6. 事件协议

### 6.1 事件分类

必须区分六类事件：

1. `utterance.*`
   - 给用户看的字幕和给 TTS 读的内容。
   - 例如 `utterance.started`、`utterance.delta`、`utterance.completed`。

2. `workflow.*`
   - 给大屏和控制台看的工作流状态。
   - 例如 `workflow.step_started`、`workflow.step_completed`。

3. `domain.*`
   - 事实数据更新。
   - 例如 `domain.participants_updated`、`domain.exam_plan_updated`。

4. `diagnostic.*`
   - 调试和观测。
   - 例如 `diagnostic.llm_call_started`、`diagnostic.tool_timeout`。

5. `interaction.*`
   - 前台交互控制事件。
   - 例如 `interaction.interrupted`、`interaction.barge_in_started`、`interaction.barge_in_ignored`。

6. `narration.*`
   - 播报聚合与摘要事件。
   - 例如 `narration.item_queued`、`narration.summary_requested`、`narration.summary_emitted`。

当前的 `assistant_stream`、`workflow_update`、`students_update` 可以继续兼容，但新实现应在内部使用清晰事件类型，再由 adapter 转成旧前端能消费的格式。

### 6.2 统一事件 envelope

所有事件都带统一 envelope：

```json
{
  "event_id": "evt_000001",
  "session_id": "demo_001",
  "turn_id": "turn_0008",
  "job_id": "job_20260609_0001",
  "utterance_id": "utt_0009",
  "generation": 12,
  "type": "utterance.completed",
  "priority": "high|normal|low",
  "created_at": 0,
  "data": {}
}
```

没有 `turn_id` 或 `job_id` 的系统事件也可以发送，但只要是用户触发链路，必须能关联回 turn。

### 6.3 用户可见进度事件

慢任务期间必须最终产生用户可见进度。原始后台进度先进入 `narration.item_queued`；Narration Aggregator 合并后再发 `utterance.progress`：

```json
{
  "type": "utterance.progress",
  "priority": "normal",
  "data": {
    "text": "我已经识别到考试需求，正在查询现场学员名单。您可以继续问我目前准备到哪一步。",
    "interruptible": true,
    "tts": true
  }
}
```

这类事件不是装饰，而是前台主线程的生命体征。

### 6.4 打断事件

用户打断不是 TTS 的本地 stop，而是一次新的交互事实。必须广播 `interaction.interrupted`：

```json
{
  "type": "interaction.interrupted",
  "priority": "urgent",
  "utterance_id": "utt_0007",
  "generation": 13,
  "data": {
    "reason": "user_barge_in",
    "new_turn_id": "turn_0008",
    "stopped_priorities": ["low", "normal"],
    "affected_job_id": "job_20260609_0001",
    "job_policy": "continue"
  }
}
```

这个事件的含义：

- 前端立即停止或淡出被打断 utterance 的音频。
- 前端丢弃旧 generation 的后续音频帧和字幕 delta。
- Conversation Gateway 把新输入作为新的 turn 处理。
- Workflow Engine 默认继续运行，除非新 turn 明确要求取消、暂停、重置或修改方案。
- 大屏工作流不因为普通插话回退，但可以显示“用户追问中”这类轻量状态。

### 6.5 播报聚合事件

后台有新进度或结果时，先发 `narration.item_queued`，不直接发 `utterance.progress`：

```json
{
  "type": "narration.item_queued",
  "job_id": "job_20260609_0001",
  "data": {
    "item_id": "nar_0012",
    "kind": "progress",
    "priority": "normal",
    "summary_key": "exam_progress",
    "fact_path": "facts.progress",
    "fact_version": 7
  }
}
```

Narration Aggregator 在合适时机发 `narration.summary_emitted`，再转成 `utterance.*`：

```json
{
  "type": "narration.summary_emitted",
  "job_id": "job_20260609_0001",
  "data": {
    "source_item_ids": ["nar_0012", "nar_0013", "nar_0014"],
    "text": "我这边看到进度有了新变化：8 名学员都已进入考试，其中 5 人已经交卷，剩下 3 人还在答题。",
    "dropped_item_ids": ["nar_0011"],
    "reason": "coalesced_progress"
  }
}
```

这个机制保证后台事件可以高频更新大屏，但语音只播用户真正需要听的一段总结。

## 7. 前台交互通道设计

### 7.1 职责

前台交互通道必须负责：

- 立即确认收到用户输入。
- 判断用户是在发起任务、追问上下文、确认、取消、修改参数，还是闲聊。
- 在后台任务运行时回答插入问题。
- 控制 TTS 优先级和打断。
- 把复杂后台状态翻译成人能理解的短句。

它不负责：

- 调用创建考试接口。
- 等待 Claude CLI。
- 等待 DeepSeek 强模型。
- 等待完整试卷生成。
- 直接推进工作流步骤。

### 7.2 即时回应策略

用户输入后必须先走本地或低延迟响应模板：

| 用户意图 | 即时回应 |
| --- | --- |
| 安排考试 | “收到，我先按胸部 CT 基础诊断考试来准备。我会同步整理方案、查询学员名单和匹配题库，进展随时告诉您。” |
| 确认方案 | “好的，我继续往下创建试卷草稿。这个过程我会边做边告诉您进度。” |
| 下发考试 | “收到，我开始下发考试，同时会盯住学员进入和提交情况。” |
| 询问上下文 | 直接基于 facts 回答，不启动工作流 |
| 修改参数 | “可以，我先记录这个调整，再同步更新考试方案。” |
| 取消/暂停 | “收到，我先暂停当前流程。” |

LLM 可以润色，但不能决定是否先回应。模板响应是硬保障。

### 7.3 忙碌期间用户输入

当前 `s.busy` 会导致忙碌期间无法正常处理用户输入。完整方案中，`busy` 只能表示后台 job 忙，不代表前台不能说话。

忙碌期间输入应按优先级处理：

1. `cancel` / `pause` / `reset`：高优先级，打断播报并请求取消后台 job。
2. `confirm` / `publish`：高优先级，写入 confirmation facts，唤醒等待中的 job。
3. `context_question`：高优先级，直接从 facts 回答。
4. `modify_request`：中高优先级，记录变更，必要时让 job 进入 replanning。
5. `smalltalk`：低优先级，简短回答，不影响 job。

后台 job 运行不能拒绝前台 turn。最多只能说“这个信息还在查询中，目前我已经拿到的是...”

### 7.4 用户打断智能体发言

语音交互必须支持 barge-in：用户可以在智能体还没说完时插话。打断场景至少分为五类：

| 打断类型 | 用户表现 | 助教动作 | 工作流处理 |
| --- | --- | --- | --- |
| 追问事实 | “有哪些人？”“现在到哪了？” | 停止低优先级播报，立即回答新问题 | 继续 |
| 确认/下发 | “可以”“下发” | 停止当前播报，优先处理确认或下发 | 从等待点继续，或记录为待执行动作 |
| 修改方案 | “改成 20 分钟”“人数换成 10 个” | 停止当前播报，确认变更并触发 replanning | 暂停相关步骤，重新生成受影响 facts |
| 取消/暂停/重置 | “停一下”“取消”“重来” | 停止所有播报，发取消/暂停确认 | 请求取消、暂停或重建 job |
| 无效噪声/误识别 | 背景音或短词 | 不打断或只进入 listen-only | 继续 |

打断处理流程：

1. 前端检测到用户开始说话时，如果当前 utterance `interruptible=true`，立即发 `POST /api/conversation/interrupt` 或在新 turn 中带 `barge_in=true`。
2. 后端 `Interaction Controller` 增加 `interrupt_generation`，广播 `interaction.interrupted`。
3. TTS Scheduler 停止指定优先级以下的音频，清空旧 utterance 队列。
4. Conversation Gateway 创建新 turn，并把 `interrupts_utterance_id` 写入 turn。
5. Intent Router 只处理新 turn，不等待旧 utterance 完成。
6. 新 turn 如果是上下文问题，直接走 facts resolver；如果是修改/取消，向 Workflow Engine 发送 job command。
7. 旧 LLM 流、旧 TTS 流、旧字幕流继续返回也必须因 generation 过期被丢弃。
8. 新答案播报完成后，如果后台 job 仍在运行，Progress Narrator 可以恢复后续进度播报，但不能重播已被用户打断的长句。

关键原则：

- “用户开始说话”只负责降低或停止当前音频，不等于业务取消。
- “用户说了取消/暂停/重置”才会影响后台 job 生命周期。
- “用户说了修改方案”会让相关 job step 进入 replanning，但不应该粗暴重置全流程。
- 旧播报不能在用户新问题之后继续播放，否则会造成对话错乱。
- 如果用户打断的是确认请求，系统必须保留确认状态，直到新 turn 明确确认、拒绝或修改。

### 7.5 上下文问答

上下文问答必须先通过确定性 facts resolver：

| 问题类型 | 数据源 |
| --- | --- |
| 有哪些人参加 | `facts.participants.students` |
| 多少人参加 | `facts.participants.total` 或 `facts.exam_plan.student_count` |
| 考什么 | `facts.exam_plan.topic` |
| 几道题/多久/总分 | `facts.exam_plan` |
| 现在到哪步 | `workflow.active_jobs.current_step` |
| 有多少人提交 | `facts.progress.submitted` |
| 平均分/最高分 | `facts.result.summary` |
| 谁分数最高 | `facts.result.students` |
| 薄弱点是什么 | `facts.result.weak_points` |
| 推荐了什么病例 | `facts.recommendation.cases` |

如果 facts 中没有答案，前台应明确说明正在查询或尚未到该阶段，而不是编造。

示例：

用户：“有哪些人参加了考试？”

如果 `participants` 已有：

“这场考试一共 8 名学员：张伟、李静、王磊、刘洋、陈晨、赵敏、孙浩和周琳。主要来自放射科、呼吸内科和胸外科。”

如果 `participants` 未查询完成：

“学员名单我还在查询，目前方案里预计是 8 名现场规培学员。名单返回后我会马上告诉您具体姓名。”

## 8. 后台工作流通道设计

### 8.1 工作流引擎

工作流引擎以 job 为单位运行。安排考试 job 包含：

1. `recognize_intent`
2. `build_exam_plan`
3. `wait_plan_confirm`
4. `query_participants`
5. `create_exam_draft`
6. `fetch_exam_preview`
7. `wait_publish_confirm`
8. `publish_exam`
9. `monitor_progress`
10. `grade_exam`
11. `recommend_cases`

每一步必须：

- 更新 job current_step。
- 发 workflow event。
- 成功后写入 facts。
- 失败后写入 error fact，并生成可解释的前台口播。
- 不直接阻塞 Conversation Gateway。

### 8.2 慢任务 heartbeat

每个 job 配一个 progress narrator：

- 2 秒没有用户可见事件：发第一条进度安抚。
- 之后每 3-5 秒，如果 job 仍 running 且没有新事实：发非重复进度。
- 工具开始、工具成功、工具失败都可以触发事实型播报。
- 所有进度先进入 `pending_narration`，不能绕过 Narration Aggregator 直接进 TTS。

进度播报必须基于当前 step：

| step | 进度播报 |
| --- | --- |
| `build_exam_plan` | “我已经识别到考试主题，正在整理题量、时长和评分方案。” |
| `query_participants` | “我正在查现场学员名单，查到后会直接报姓名和人数。” |
| `create_exam_draft` | “题库匹配还在进行，我会先把草稿状态同步到大屏。” |
| `fetch_exam_preview` | “试卷草稿已经在生成预览，马上给您看题型结构。” |
| `publish_exam` | “正在打开学员端入口，同时生成考试二维码。” |
| `monitor_progress` | “我正在看答题进度，目前会按进入、答题、提交三个指标同步。” |
| `grade_exam` | “已收到提交数据，正在汇总分数和薄弱点。” |

### 8.3 积压进度与结果的合并播报

用户问答、长句播报、TTS 合成、网络抖动或用户打断期间，后台可能连续产生多条进度和结果。系统不能逐条补播，否则用户会听到过时且冗长的信息。必须按以下规则合并：

1. 同一 `summary_key` 只保留最新事实版本，旧版本标记为 dropped。
2. 同一 job 的连续 step 进展可以合成一句，例如“已经完成学员查询和试卷草稿，正在生成预览”。
3. 结果类信息优先于过程类信息，例如成绩结果到了以后，不再补播“正在阅卷”。
4. 错误、确认请求、取消结果不能被普通摘要吞掉，必须单独播报或排在摘要前。
5. 用户刚问过的问题相关信息优先，例如用户问“有哪些人”，学员名单返回后应主动补充。
6. 过期进度不播，例如 `fetch_exam_preview` 已完成后，不再说“正在生成预览”。
7. 多条答题进度要总结趋势，不逐条读数。

示例：用户正在听“学员名单”回答时，后台依次产生：

- `students.completed`
- `create_exam_draft.completed`
- `preview.completed`

不应播三句：

- “学员名单查到了。”
- “考试草稿创建好了。”
- “试卷预览生成好了。”

应播一段总结：

“您刚才问名单时，我这边也把考试草稿和试卷预览准备好了：8 名学员已经绑定，下一步等您确认是否下发。”

如果同时有确认请求，则确认请求必须保留在总结末尾，不能被摘要省略。

### 8.4 确认点

用户确认是前台交互事件，不是后台阻塞调用。后台 job 到确认点后：

1. 更新 job status 为 `waiting_user`。
2. 写入 `interaction.need_user_confirmation`。
3. 发 `utterance.confirmation_requested`。
4. 释放 worker，不占用执行线程。

用户确认后：

1. Conversation Gateway 写入 confirmation fact。
2. Workflow Engine 唤醒对应 job。
3. 继续后续步骤。

## 9. 上下文管理与 Prompt 策略

### 9.1 结构化上下文

传给 LLM 的上下文必须来自结构化 facts，不允许只传默认方案。推荐上下文格式：

```json
{
  "current_state": "MONITORING_PROGRESS",
  "need_confirmation": false,
  "active_jobs": [
    {
      "job_id": "job_001",
      "type": "arrange_exam",
      "status": "running",
      "current_step": "monitor_progress"
    }
  ],
  "facts": {
    "exam_plan": {
      "exam_name": "胸部 CT 基础诊断测评",
      "student_count": 8,
      "duration_minutes": 15,
      "question_total": 17
    },
    "participants": {
      "total": 8,
      "names": ["张伟", "李静", "王磊", "刘洋", "陈晨", "赵敏", "孙浩", "周琳"]
    },
    "progress": {
      "entered": 8,
      "answering": 5,
      "submitted": 3
    }
  },
  "recent_turns": []
}
```

### 9.2 Prompt 角色拆分

不要用一个 prompt 同时承担意图识别、业务执行、闲聊、状态播报。至少拆五类：

1. Intent Router
   - 只输出结构化 intent。
   - 低延迟。

2. Context QA
   - 基于 facts 回答用户问题。
   - 如果 facts 已足够，不需要调用模型。

3. Progress Narrator
   - 把 job 状态翻译为自然口播。
   - 输入是 job step 和 facts。

4. Narration Summarizer
   - 把积压的 pending narration items 合并成一段自然口播。
   - 输入是“最新 facts + 被合并/丢弃的 item 列表 + 当前用户焦点”。
   - 输出必须短，优先说结果和下一步，不逐条复述过程。

5. Workflow Planner
   - 负责复杂任务计划或工具选择。
   - 可以慢，但只能在后台 job 里运行。

### 9.3 禁止的 Prompt 行为

必须从 prompt 中去掉以下倾向：

- 对所有 smalltalk 都强行引导回“要不要安排考试”。
- 在不知道 facts 时编造学员、分数、进度。
- 把用户上下文问题当成重新安排考试。
- 用系统状态句替代真实回答。
- 让强模型话术生成阻塞第一句回应。
- 对 pending narration items 逐条复述，而不是按最新事实总结。

### 9.4 拟人化话术约束

这是智能体教学助手，不是运维控制台。任何进入 `utterance.*`、TTS、字幕主文本的内容，都必须以“助教本人正在协助老师”的口吻表达。

面向用户的可听文本禁止使用这些技术视角词：

- “后台”
- “系统”
- “workflow / job / task”
- “接口返回”
- “TTS / LLM / 模型调用”
- “队列 / 事件 / generation”

替代表达：

| 禁用表达 | 推荐表达 |
| --- | --- |
| “刚刚后台完成了……” | “您刚才问这个时，我这边也准备好了……” |
| “后台正在处理” | “我正在处理” / “我这边正在查” |
| “系统生成了试卷” | “我把试卷准备好了” |
| “接口返回学员名单” | “我查到了学员名单” |
| “任务进入等待确认” | “接下来等您确认一下” |
| “模型正在总结进度” | “我先把最新情况整理给您” |

用户可听文本应遵循：

- 用第一人称：“我查到”“我整理好”“我正在看进度”。
- 用面向老师的称呼：“您确认后”“我给您看一下”。
- 用教学助手语气，不用工程状态句。
- 可以承认正在做事，但不要暴露技术执行层。
- 总结积压信息时要像助教自然补充，不要说“刚刚后台/系统/流程”。

技术术语仍可出现在架构文档、日志、诊断事件和控制台，但不能进入主字幕和语音。

### 9.5 Narration Summarizer 输入输出

当 `pending_narration` 中同时存在多条可播报信息，或者当前 utterance 播放期间有新 facts 到达，Narration Aggregator 应调用 Narration Summarizer。

输入结构：

```json
{
  "current_user_focus": {
    "last_turn": "有哪些人参加了考试",
    "last_answer_topic": "participants"
  },
  "current_foreground_state": {
    "speaking": false,
    "last_utterance_interrupted": true
  },
  "job": {
    "job_id": "job_001",
    "type": "arrange_exam",
    "current_step": "wait_publish_confirm"
  },
  "latest_facts": {
    "participants": {
      "total": 8,
      "names": ["张伟", "李静", "王磊", "刘洋", "陈晨", "赵敏", "孙浩", "周琳"]
    },
    "exam_preview": {
      "question_total": 17
    },
    "need_confirmation": true,
    "confirmation_type": "confirm_publish"
  },
  "pending_items": [
    {
      "item_id": "nar_0012",
      "kind": "result",
      "summary_key": "participants",
      "fact_version": 3
    },
    {
      "item_id": "nar_0013",
      "kind": "result",
      "summary_key": "exam_draft",
      "fact_version": 4
    },
    {
      "item_id": "nar_0014",
      "kind": "confirmation",
      "summary_key": "confirm_publish",
      "requires_verbatim": true
    }
  ]
}
```

输出结构：

```json
{
  "text": "您刚才问名单时，我这边也把后续准备好了：8 名学员已经绑定，17 道题的试卷预览也生成了。您确认后，我就可以下发考试。",
  "source_item_ids": ["nar_0012", "nar_0013", "nar_0014"],
  "dropped_item_ids": [],
  "must_follow_up": false
}
```

LLM 超时或失败时，不能回退到逐条播报，应使用确定性摘要模板：

- 参与人 + 草稿 + 预览完成：“名单、草稿和预览都准备好了，下一步等待您确认下发。”
- 多条进度更新：“我这边看到进度有了新变化：{latest_progress_label}，已提交 {submitted}/{total}。”
- 阅卷 + 推荐完成：“阅卷和复训病例都生成了，我先报核心结果：平均分 {average}，主要薄弱点是 {weak_points}。”

## 10. TTS 与字幕调度

TTS Scheduler 不接收 workflow/domain 原始事件，只接收 Narration Aggregator 输出的最终 utterance。后台事件越多，越不能简单排队逐条读；队列里应该是“对用户有意义的当前摘要”。

聚合窗口建议：

- 用户正在回答或播报中：把 normal/low 信息暂存 1.5-3 秒，等待合并。
- 后台高频进度更新：按 `summary_key` 合并，最多每 3-5 秒发一条摘要。
- 结果到达：立即触发摘要，把之前同类 progress 标记为过期。
- 确认请求、严重错误、取消结果：不等待聚合窗口，作为 urgent/high utterance 直通。
- 用户刚打断后：先回答用户问题，再对积压信息做一次短总结，不恢复逐条补播。

### 10.1 TTS 优先级

TTS 队列必须支持优先级：

1. `urgent`：打断当前播报，例如取消、错误、确认请求。
2. `high`：用户问题答案。
3. `normal`：工作流关键进度。
4. `low`：装饰性说明和大屏解说。

后台进度播报不能压住用户问题答案。用户追问时，应停止或淡出低优先级播报。

如果队列中已有同一 `summary_key` 的 normal/low utterance，新摘要必须替换旧摘要，而不是排在旧摘要后面。只有 `urgent` 和 `requires_verbatim=true` 的信息允许并列保留。

每条 utterance 必须带：

```json
{
  "utterance_id": "utt_0009",
  "priority": "high",
  "interruptible": true,
  "generation": 13,
  "source": "context_qa|progress|confirmation|error|workflow"
}
```

`interruptible=false` 只允许用于极短的安全提示或确认结果，例如“已暂停”。普通长句、进度说明、方案介绍都必须可打断。

### 10.2 文本先于语音

字幕必须先显示，TTS 可以随后播放。不能因为阿里云 TTS 建连、合成、音频播放而延迟文本反馈。

### 10.3 播报去重

同一 job step 的 heartbeat 不能重复同一句。应维护：

- last_spoken_step
- last_spoken_text_hash
- last_spoken_at
- min_repeat_interval

### 10.4 Barge-in 音频控制

TTS Scheduler 必须支持以下操作：

- `stop(utterance_id)`：停止指定 utterance。
- `stop_below_priority(priority)`：停止低于指定优先级的播报。
- `flush_generation(generation)`：丢弃旧 generation 的排队文本、音频帧和 end 事件。
- `duck()`：用户刚开始说话但 ASR 尚未确定内容时，把当前音量降到 10%-20%。
- `restore()`：判断为误触发或无效语音后恢复音量。

前端 ASR 检测到用户开始说话时，不应等待最终识别结果才处理音频。推荐流程：

1. `speechstart` 或检测到有效音量：立即 duck 当前可打断 utterance。
2. 300-600ms 内出现稳定语音或 interim transcript：发送 interrupt。
3. 得到 final transcript：作为新 turn 发送。
4. 如果没有 transcript 或置信度低：发送 `interaction.barge_in_ignored`，恢复音量并继续当前播报。

为了避免数字人自问自答，TTS 播报期间麦克风仍可监听 barge-in，但 ASR 输入必须做回声保护：

- 前端记录当前正在播放的 utterance 文本。
- ASR 结果与当前播报文本高度重合时判为 echo，不触发打断。
- 短词如“嗯”“啊”“好”在非确认窗口中不触发业务 turn。
- 确认窗口中，“好/可以/确认/下发”才作为有效打断。

## 11. 前端改造要求

### 11.1 Store 分层

前端 store 应拆成：

- `sessionStore`：事实数据和连接状态。
- `interactionStore`：当前字幕、TTS 队列、麦克风、打断状态。
- `workflowStore`：工作流步骤、active jobs、控制台事件。

当前一个 Pinia store 同时管理所有状态，后续会让交互状态和业务事实互相污染。

### 11.2 输入不因后台 busy 禁用

输入框和麦克风不应因为 workflow busy 失效。可以显示“我正在处理”，但仍允许用户提问、取消、确认和修改参数。

### 11.3 用户打断输入

前端必须把“用户打断智能体发言”作为正常路径支持：

- 数字形象正在说话时，麦克风不应完全关闭；应进入 barge-in listening。
- 用户开始说话时，界面状态从“播报中”切到“正在听您说”，同时当前字幕可以淡出或冻结。
- 新 turn 的字幕必须覆盖旧字幕，旧字幕 delta 不得继续追加。
- 如果用户只是误触发，界面恢复到原 utterance，不创建新业务 turn。
- 如果用户明确打断，前端应显示新用户文本和新助教回应，不再播放旧 utterance。

前端必须维护 `active_generation`。任何 WebSocket 事件或 TTS 二进制帧 generation 小于当前值，都直接丢弃。

### 11.4 主屏显示策略

数字形象页应优先显示前台交互状态：

- 正在倾听
- 已收到
- 正在回答
- 我正在处理
- 等待确认

大屏工作流显示后台状态：

- 当前 step
- 进度
- 已完成成果
- 工具调用状态

两者可以同时存在，不互相覆盖。

## 12. 后端接口建议

### 12.1 用户输入

```http
POST /api/conversation/turn
```

请求：

```json
{
  "session_id": "demo_001",
  "source": "voice",
  "text": "有哪些人参加了考试",
  "client_time": 0
}
```

响应必须快速返回：

```json
{
  "ok": true,
  "turn_id": "turn_0008",
  "accepted": true
}
```

响应不承诺业务已完成，只承诺输入已进入前台交互通道。

### 12.2 Job 查询

```http
GET /api/sessions/{session_id}/jobs
```

返回 active jobs，供控制台调试。

### 12.3 打断

```http
POST /api/conversation/interrupt
```

请求：

```json
{
  "session_id": "demo_001",
  "utterance_id": "utt_0007",
  "reason": "user_barge_in|manual_stop|cancel|echo_rejected",
  "policy": "duck|stop_low_priority|stop_all|cancel_job",
  "job_id": "job_20260609_0001"
}
```

用途：

- 停止、淡出或降低当前 TTS 音量。
- 推进 `interrupt_generation`，让旧流式 token 和音频帧失效。
- 提升后续新 turn 优先级。
- 可选取消、暂停或重规划指定 job。

如果 interrupt 后会立即发送新用户文本，也可以合并到 `/api/conversation/turn`：

```json
{
  "session_id": "demo_001",
  "source": "voice",
  "text": "有哪些人参加",
  "barge_in": true,
  "interrupts_utterance_id": "utt_0007",
  "interrupt_policy": "stop_low_priority"
}
```

### 12.4 快照

```http
GET /api/sessions/{session_id}/snapshot
```

返回完整 session facts、workflow、interaction 状态。前端刷新后必须能恢复。

## 13. 观测与验收指标

### 13.1 必须记录的指标

- `turn_first_response_latency_ms`
- `turn_route_latency_ms`
- `job_duration_ms`
- `job_step_duration_ms`
- `llm_call_duration_ms`
- `tool_call_duration_ms`
- `time_since_last_user_visible_event_ms`
- `tts_queue_wait_ms`
- `interrupt_to_silence_ms`
- `barge_in_detection_latency_ms`
- `stale_event_dropped_count`
- `echo_rejected_count`
- `interrupt_generation`
- `job_command_latency_ms`
- `pending_narration_item_count`
- `narration_coalesced_count`
- `narration_dropped_stale_count`
- `narration_summary_latency_ms`
- `verbatim_item_preserved_count`

### 13.2 验收标准

完整实现必须满足：

1. 用户说“准备考试”后，800ms 内页面出现助教回应。
2. 后台 `claude_cli` 卡 30 秒时，前台至少播报 5 条非重复进度或状态解释。
3. 后台创建考试时，用户问“有哪些人参加了考试”，如果名单已查询，2 秒内直接回答姓名。
4. 名单未查询时，不能编造姓名，必须说明“还在查询”，并在查询完成后主动补充。
5. 用户问“现在到哪一步”，必须回答当前 active job step。
6. 用户打断播报后，低优先级 TTS 在 300ms 内停止。
7. 用户打断后产生的新 turn 必须覆盖旧字幕；旧 LLM token、旧 TTS 音频帧、旧 end 事件不得回写 UI。
8. 用户在助教发言时问上下文问题，后台 job 默认继续运行，不得被误取消。
9. 用户在助教发言时说“停一下/取消/重来”，后台 job 必须进入 pause/cancel/reset 对应状态。
10. 用户在确认窗口中打断说“可以/下发”，确认不能因为后台 busy 或 TTS 播报中而丢失。
11. ASR 识别到数字人自己播报内容时，必须判为 echo 并拒绝创建 turn。
12. 用户确认方案后，不允许因为后台 busy 丢弃确认。
13. WebSocket 断线重连后，前端能通过 snapshot 恢复 facts 和 active jobs。
14. 所有工具失败都必须有用户可理解的解释和下一步动作。
15. 日志能从 turn id 追踪到 job id、LLM 调用、工具调用和最终用户口播。
16. 用户回答或长播报期间积累 3 条以上 normal 进度时，恢复播报后只能输出一段总结，不能逐条补播。
17. 新结果到达后，旧的同类 progress 必须过期丢弃，例如“正在阅卷”不能在成绩已出后继续播放。
18. `requires_verbatim=true` 的确认请求、严重错误、取消结果不能被摘要丢掉。
19. Narration Summarizer 超时或失败时，必须使用确定性摘要模板，不能退化成 FIFO 逐条播报。

## 14. 实施顺序

### 阶段一：建立事件和状态底座

1. 定义 `Turn`、`Job`、`SessionFacts`。
2. 引入统一 event envelope。
3. 保留旧 WebSocket 事件 adapter，避免一次性改前端全部组件。
4. 记录 first response latency。

### 阶段二：前台交互通道独立

1. 新增 Conversation Gateway。
2. 用户输入后先发即时 utterance。
3. 移除“workflow busy 阻止对话”的逻辑。
4. 增加上下文问题 resolver。

### 阶段三：后台工作流 job 化

1. 把安排考试流程改为 job steps。
2. 确认点改为 `waiting_user`。
3. 每步写入 facts。
4. 每步发 workflow/domain events。

### 阶段四：进度安抚与打断

1. 增加 job heartbeat narrator。
2. 增加 Narration Aggregator 和 `pending_narration`。
3. TTS 队列支持优先级和同类摘要替换。
4. 用户新问题打断低优先级播报。
5. 引入 utterance id、generation 和 stale event 丢弃。
6. 支持 barge-in duck、stop、restore、echo reject。
7. 后台慢任务不再造成沉默窗口。
8. 后台高频事件不再造成逐条补播。

### 阶段五：LLM 策略重构

1. Intent Router、Context QA、Progress Narrator、Narration Summarizer、Workflow Planner 分 prompt。
2. Context QA 优先 facts resolver，必要时才模型润色。
3. Narration Summarizer 输入 pending items 和 latest facts，只输出摘要。
4. Workflow Planner 只允许后台调用。
5. 强模型和 Claude CLI 不允许出现在首句回应路径。

### 阶段六：观测、压测和演示验收

1. 增加 trace 日志。
2. 人为注入 30 秒 LLM 卡顿。
3. 人为注入教学平台超时。
4. 人为断开 WebSocket。
5. 人为制造用户打断、误触发、回声识别和确认窗口插话。
6. 人为制造用户问答期间后台连续产生多条进度和结果。
7. 逐条跑验收标准。

## 15. 需要废弃的现有模式

以下模式应在完整实现中废弃，而不是继续补丁式维护：

- 一个 `orchestrator.handle_message` 串起所有工作和所有播报。
- 用 `s.busy` 阻止用户继续交互。
- 把默认方案当作主要上下文。
- 用强模型或 Claude CLI 生成首句回应。
- 慢任务期间只更新大屏，不给数字人进度口播。
- 把 TTS 播放状态当作业务状态。
- 把“停止播放声音”当作完整打断处理。
- 旧流式回包不做 generation 校验，继续追加到新字幕。
- 用户插话时默认取消后台 job。
- 把后台事件直接塞进 TTS 队列逐条播放。
- 摘要失败时退回 FIFO 补播。
- 结果已更新后仍播过期进度。
- 小声失败、静默 fallback、导演台强推作为主要稳定性手段。

导演台可以保留，但它只能是运维控制面，不能成为正常交互架构的兜底核心。

## 16. 最终目标体验

用户说：“准备考试。”

助教 800ms 内回应：“收到，我先按胸部 CT 基础诊断考试来准备。我会同步整理方案、查询学员名单和匹配题库，进展随时告诉您。”

大屏开始显示工作流推进。

工作流较慢时，助教继续说：“我已经整理好考试方案，正在查现场学员名单。”随后：“名单查到了，一共 8 名学员，我正在把他们绑定到这场考试。”

助教还在解释后续题库匹配时，用户插话：“有哪些人参加了考试？”

前端先把当前播报音量压低并停止低优先级 utterance；后端提升 `interrupt_generation`，旧播报的后续字幕和音频帧全部失效。助教立即回答：“这场考试一共 8 名学员：张伟、李静、王磊、刘洋、陈晨、赵敏、孙浩和周琳。主要来自放射科、呼吸内科和胸外科。”

工作流继续创建考试，不被这次问答打断。

在这段回答期间，工作流又完成了“创建草稿”和“生成预览”。实现上不会等回答结束后补播两条旧进度，而是由 Narration Aggregator 合并成一句：“您刚才问名单时，我这边也把考试草稿和 17 道题的试卷预览准备好了，现在等您确认是否下发。”

如果用户插话说的是“停一下”，当前播报停止，工作流进入 pause；如果用户说“改成 20 分钟”，当前 job 进入 replanning，只重算受影响的方案和后续草稿，不粗暴清空已查询到的学员 facts。

用户说：“可以，下发。”

助教打断当前低优先级播报：“收到，我开始下发考试。”后台 job 进入 publish step，大屏同步二维码和答题进度。

这个体验才是语音前台和智能体后台正确协作的形态：用户始终被接住，后台始终在推进，所有事实都能被问到，任何慢步骤都不会让前台失声。
