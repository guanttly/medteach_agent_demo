# 巨鲨医用教学智能体展厅 Demo MVP PRD

> 版本：v0.2  
> 定位：展厅演示用 MVP  
> 核心技术路线：Claude Code CLI + DeepSeek API 作为 Agent Core  
> 数字形象：本地低成本动画小鲨鱼助教  
> 目标场景：围绕“安排一场医学教学考试”完成完整演示闭环

---

## 1. 项目背景

巨鲨已有教学平台，本项目不重做教学平台，也不做完整教学产品。

本项目要做的是一个放在公司展厅中的**智能体演示外壳**：演示者通过语音或文本向智能体提出教学任务，例如“安排一张考试”，智能体根据预设 Skill 和平台接口能力，完成考试方案生成、信息补全、考试创建、试卷预览、下发考试、答题进度展示、自动阅卷结果展示、学习目标和病例推荐。

展厅旁边的大屏实时展示智能体正在做什么，左侧使用一个本地动画“小鲨鱼助教”作为智能体形象，营造“巨鲨智能助教正在组织教学”的感知。

---

## 2. 项目一句话定义

> 基于现有教学平台能力，用 Claude Code CLI + DeepSeek API 作为 Agent Core，外层实现展厅交互、大屏展示、小鲨鱼动画、导演控制台和接口适配，完成一次“自然语言安排考试”的医学教学智能体演示闭环。

---

## 3. MVP 核心目标

MVP 只验证一件事：

> 演示者只需要用自然语言提出教学目标，系统就能通过智能体驱动现有教学平台完成一次考试演示流程。

必须跑通以下闭环：

```text
演示者提出：安排考试
↓
Claude Code Core 触发安排考试 Skill
↓
智能体生成默认考试方案
↓
演示者确认方案
↓
智能体调用工具脚本 / 接口适配器创建考试
↓
大屏展示试卷预览
↓
演示者确认下发
↓
智能体调用平台接口下发考试
↓
大屏展示学员答题进度
↓
真实答题或导演台模拟提交
↓
智能体读取成绩或使用 Mock 成绩
↓
生成阅卷分析、薄弱点总结
↓
推荐下一阶段学习目标和病例
↓
演示完成
```

---

## 4. MVP 不做范围

第一版明确不做：

```text
不重做教学平台
不重做题库系统
不重做病例库系统
不做完整考试后台
不做完整权限系统
不做多科室通用配置
不做复杂课程体系
不做完整学习计划产品
不做真人数字人
不做云数字人
不做 3D 数字人
不做真实生产级阅卷
不把模型结论用于临床诊断
```

第一版只围绕一个黄金路径：

```text
胸部 CT 基础诊断考试演示
```

---

## 5. 技术路线重大调整

### 5.1 原方案

原方案倾向于：

```text
自研 Agent Runtime
↓
直接调用 DeepSeek API
↓
自研状态机和工具调用
↓
教学平台接口
```

### 5.2 MVP 调整后方案

现在改为：

```text
展厅前端 / 小鲨鱼动画 / 大屏
↓
Demo Shell / Orchestrator
↓
Claude Code CLI Core
↓
DeepSeek API
↓
Claude Skill / 工具脚本 / MCP 或 Bash 工具
↓
教学平台接口适配器
↓
现有教学平台 / Mock 数据
```

### 5.3 调整原则

Claude Code CLI 是智能体核心。

外层 Demo Shell 不再承担完整 Agent 推理职责，只负责：

```text
1. 接收语音 / 文本输入
2. 将用户指令转成 Claude Code CLI 调用
3. 管理 Claude Code 会话和项目目录
4. 解析 Claude Code 输出
5. 推送大屏事件
6. 驱动小鲨鱼动画状态
7. 处理导演台控制
8. 管理 Mock / 真实接口切换
9. 做演示级状态保护
10. 记录日志和异常
```

---

## 6. 为什么采用 Claude Code CLI Core

当前目标是做展厅演示 MVP，不是做正式生产级智能体平台。

采用 Claude Code CLI Core 的好处：

```text
1. 可以直接利用 Claude Code 的 agentic loop 能力。
2. 可以用 Skill 文件沉淀考试安排流程。
3. 可以让智能体通过 Bash / 脚本 / MCP 方式调用教学平台接口。
4. 可以用 DeepSeek API 作为后端模型，降低模型调用成本。
5. 开发速度快，适合短周期搭建演示。
6. Claude Code 项目目录天然适合放置 Skill、工具脚本、Mock 数据和接口文档。
```

但必须明确：

```text
Claude Code CLI Core 只作为展厅 Demo 的 Agent 核心。
第一版不承诺生产级稳定性。
所有高风险动作都必须由外层 Demo Shell 和导演台兜底。
```

---

## 7. 总体架构

```text
┌─────────────────────────────────────────────┐
│ 展厅大屏 Frontend                             │
│ Vue 3 + 小鲨鱼动画 + 工作流展示 + 成绩展示       │
└──────────────────────┬──────────────────────┘
                       │ WebSocket / HTTP
                       ↓
┌─────────────────────────────────────────────┐
│ Demo Shell / Orchestrator                    │
│ - 接收用户输入                                │
│ - 调用 Claude Code CLI                       │
│ - 解析 JSON / Stream 输出                     │
│ - 推送大屏事件                                │
│ - 驱动小鲨鱼状态                              │
│ - 控制 Mock / 真实接口                        │
│ - 导演台干预                                  │
└──────────────────────┬──────────────────────┘
                       │ subprocess / shell
                       ↓
┌─────────────────────────────────────────────┐
│ Claude Code CLI Core                         │
│ - 接入 DeepSeek API                           │
│ - 加载 CLAUDE.md                              │
│ - 触发 arrange_exam Skill                     │
│ - 调用工具脚本                                │
│ - 组织多步骤任务                              │
└──────────────────────┬──────────────────────┘
                       │ Bash / MCP / Scripts
                       ↓
┌─────────────────────────────────────────────┐
│ Tool Layer                                   │
│ - get_present_students.py                     │
│ - create_exam_draft.py                        │
│ - get_exam_preview.py                         │
│ - publish_exam.py                             │
│ - get_exam_progress.py                        │
│ - get_exam_result.py                          │
│ - recommend_cases.py                          │
└──────────────────────┬──────────────────────┘
                       │ HTTP
                       ↓
┌─────────────────────────────────────────────┐
│ Teaching Platform Adapter                    │
│ - 固定账号登录                                │
│ - Token 管理                                  │
│ - 参数转换                                    │
│ - 错误处理                                    │
│ - Mock 兜底                                   │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│ 现有教学平台 / Mock 数据                       │
└─────────────────────────────────────────────┘
```

---

## 8. 系统组成

MVP 包含 5 个部分：

```text
1. 展厅大屏页面
2. 小鲨鱼动画助教
3. Demo Shell / Orchestrator
4. Claude Code Agent Core 项目目录
5. 教学平台接口适配器与 Mock 数据
```

---

## 9. Claude Code Core 设计

### 9.1 Core 定义

Claude Code Core 是本项目的智能体中枢。

它负责：

```text
1. 理解用户任务
2. 触发安排考试 Skill
3. 根据 Skill 补全考试方案
4. 判断是否需要用户确认
5. 调用工具脚本执行平台动作
6. 读取工具结果
7. 生成对讲师和观众友好的回复
8. 输出结构化事件给 Demo Shell
```

### 9.2 Claude Code 接入 DeepSeek API

环境变量示例：

```bash
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_AUTH_TOKEN=<your_deepseek_api_key>
export ANTHROPIC_MODEL=deepseek-v4-pro[1m]
export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]
export ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]
export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
export CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash
export CLAUDE_CODE_EFFORT_LEVEL=max
```

Windows PowerShell 示例：

```powershell
$env:ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN="<your_deepseek_api_key>"
$env:ANTHROPIC_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_EFFORT_LEVEL="max"
```

### 9.3 Claude Code CLI 调用方式

MVP 推荐使用非交互调用模式，由 Demo Shell 通过子进程调用。

基础调用：

```bash
claude -p "用户指令" --output-format json
```

流式调用：

```bash
claude -p "用户指令" --output-format stream-json --verbose
```

带系统提示：

```bash
claude -p "用户指令" \
  --append-system-prompt-file ./prompts/demo_runtime_rules.md \
  --output-format json
```

限制回合数：

```bash
claude -p "用户指令" \
  --max-turns 8 \
  --output-format json
```

指定工具权限：

```bash
claude -p "用户指令" \
  --allowedTools "Bash(python tools/*)" "Read" \
  --output-format json
```

> MVP 不建议直接使用 `--dangerously-skip-permissions` 作为默认模式。展厅 Demo 可以在隔离环境中评估是否使用，但必须限制工作目录、限制工具脚本、限制可执行命令。

---

## 10. Claude Code 项目目录结构

建议建立一个专门的 Agent Core 工作目录：

```text
medteach-agent-core/
  CLAUDE.md
  .claude/
    skills/
      arrange_exam/
        SKILL.md
        slot_schema.json
        demo_defaults.json
        response_templates.json
        tool_contracts.json
        fallback_policy.md
  prompts/
    demo_runtime_rules.md
    output_schema.md
  tools/
    get_present_students.py
    create_exam_draft.py
    get_exam_preview.py
    publish_exam.py
    get_exam_progress.py
    get_exam_result.py
    recommend_cases.py
  adapter/
    teaching_platform_client.py
    auth_client.py
    mock_client.py
  mock/
    students.json
    exam_preview.json
    exam_progress_steps.json
    exam_result.json
    recommended_cases.json
  logs/
  tmp/
```

---

## 11. CLAUDE.md 设计

`CLAUDE.md` 是 Claude Code Core 的项目级行为约束文件。

建议内容：

```md
# 巨鲨医用教学智能体展厅 Demo Core

你是巨鲨医用教学智能体的 Agent Core。

你的任务不是泛聊，而是围绕展厅演示流程，驱动现有教学平台完成“安排考试”演示闭环。

## 总原则

1. 你必须优先触发 arrange_exam Skill。
2. 你不能跳过用户确认直接创建考试。
3. 你不能跳过用户确认直接下发考试。
4. 你必须优先输出结构化 JSON，便于 Demo Shell 解析。
5. 你调用工具脚本后，必须根据工具返回结果生成大屏事件。
6. 工具失败时，按 fallback_policy.md 使用 Mock 数据继续演示。
7. 面向观众的回复要简洁、专业、适合展厅播报。
8. 不能声称完成未实际完成的真实接口调用；如果使用 Mock，内部事件标记 fallback=true。
9. 不输出临床诊断建议，只输出教学分析和训练建议。

## 固定演示主题

第一版默认主题为：胸部 CT 基础诊断考试。

## 输出要求

每轮回复尽量输出符合 prompts/output_schema.md 的 JSON：

- assistant_text：给用户听到的话
- shark_state：小鲨鱼动画状态
- screen_events：大屏事件
- next_state：下一流程状态
- need_user_confirmation：是否需要用户确认
- tool_calls：已执行或建议执行的工具调用结果
```

---

## 12. arrange_exam Skill 设计

### 12.1 Skill 目标

当用户提出安排考试、创建考试、组织测评、给学员出题等需求时，触发本 Skill。

本 Skill 负责完成：

```text
1. 识别考试任务
2. 补全考试默认参数
3. 给出考试方案
4. 等待演示者确认
5. 创建考试草稿
6. 展示试卷预览
7. 等待下发确认
8. 下发考试
9. 监控答题进度
10. 获取成绩结果
11. 分析薄弱点
12. 推荐病例和下一阶段学习目标
```

### 12.2 Skill 文件：SKILL.md

```md
---
name: arrange_exam
summary: 医学教学考试安排演示 Skill，用于创建考试、下发考试、阅卷分析和推荐病例。
---

# 医学教学考试安排 Skill

## 触发条件

当用户表达以下意图时触发：

- 安排一场考试
- 创建一场考试
- 给学员出一套题
- 安排一次测评
- 组织一次考核
- 给规培学员考一下
- 安排胸部 CT 基础考试

## 默认演示方案

如果用户信息不足，使用以下默认值：

- 考试主题：胸部 CT 基础诊断
- 考试对象：现场规培学员
- 学员数量：8 人
- 考试时长：15 分钟
- 单选题：10 道
- 多选题：5 道
- 病例分析题：2 道
- 总分：100 分
- 难度：中级
- 阅卷方式：客观题自动阅卷，病例题智能辅助点评
- 推荐病例数量：6 个

## 行为流程

1. 用户提出安排考试需求。
2. 识别考试主题、对象、时长。
3. 如果信息不完整，不要连续追问，先给出推荐方案。
4. 在用户确认方案前，不调用 create_exam_draft。
5. 用户确认后，调用 tools/create_exam_draft.py。
6. 创建成功后，调用 tools/get_exam_preview.py。
7. 展示试卷预览，并询问是否下发。
8. 用户明确说“下发”后，调用 tools/publish_exam.py。
9. 下发后，调用 tools/get_exam_progress.py 或等待导演台模拟进度。
10. 学员全部提交后，调用 tools/get_exam_result.py。
11. 根据薄弱点调用 tools/recommend_cases.py。
12. 输出总结。

## 大屏事件要求

每个关键动作都要生成 screen_event：

- intent_recognized
- plan_proposed
- waiting_user_confirmation
- tool_call_started
- tool_call_succeeded
- tool_call_failed
- exam_preview_ready
- exam_published
- progress_updated
- report_ready
- recommendation_ready
- demo_done

## 小鲨鱼状态要求

- 待命：idle
- 倾听：listening
- 思考：thinking
- 说话：speaking
- 调用工具：working
- 等待确认：waiting_confirm
- 成功完成：success
- 错误兜底：soft_warning
```

---

## 13. Claude Code 输出协议

为了让 Demo Shell 能解析 Claude Code 输出，MVP 要强约束输出 JSON。

### 13.1 标准输出结构

```json
{
  "assistant_text": "好的。我建议安排一场 15 分钟的胸部 CT 基础测评……",
  "next_state": "PLAN_PROPOSED",
  "need_user_confirmation": true,
  "confirmation_type": "confirm_plan",
  "shark_state": "speaking",
  "screen_events": [
    {
      "type": "plan_proposed",
      "title": "已生成考试方案",
      "message": "胸部 CT 基础诊断测评，15 分钟，17 道题，总分 100 分。",
      "status": "completed",
      "fallback": false,
      "payload": {}
    }
  ],
  "exam_plan": {
    "exam_name": "胸部 CT 基础诊断测评",
    "topic": "胸部 CT 基础诊断",
    "student_group": "现场规培学员",
    "student_count": 8,
    "duration_minutes": 15,
    "difficulty": "中级",
    "total_score": 100,
    "question_structure": {
      "single_choice": 10,
      "multiple_choice": 5,
      "case_analysis": 2
    }
  },
  "tool_results": [],
  "error": null
}
```

### 13.2 Demo Shell 处理原则

Demo Shell 只信任 JSON 字段，不从自然语言里猜状态。

处理顺序：

```text
1. 读取 assistant_text → 展示字幕 / TTS 播报
2. 读取 shark_state → 切换小鲨鱼动画
3. 读取 screen_events → 推送大屏
4. 读取 next_state → 更新演示状态
5. 读取 need_user_confirmation → 控制按钮和流程锁
6. 读取 tool_results → 更新接口调用面板
7. 读取 error → 决定是否进入兜底
```

---

## 14. Demo Shell / Orchestrator 设计

### 14.1 定位

Demo Shell 是 Claude Code Core 的外壳，不做复杂智能判断。

它负责把 Claude Code 变成一个可展示、可控制、可兜底的展厅系统。

### 14.2 核心职责

```text
1. 提供 HTTP API 给前端。
2. 提供 WebSocket 给大屏实时推送。
3. 将用户输入拼接成 Claude Code CLI prompt。
4. 启动 Claude Code 子进程。
5. 读取 stdout / stderr。
6. 解析 JSON 或 stream-json。
7. 管理当前 Demo Session。
8. 处理小鲨鱼动画状态。
9. 处理 TTS 播报文本。
10. 管理导演台强制推进。
11. 管理 Mock / 真实接口模式。
12. 记录演示日志。
```

### 14.3 推荐技术栈

```text
Python FastAPI
subprocess / asyncio.create_subprocess_exec
WebSocket
Pydantic
httpx
Redis 可选，MVP 可先用内存状态
```

### 14.4 CLI 调用封装

Demo Shell 应封装一个 `ClaudeCodeClient`：

```python
class ClaudeCodeClient:
    async def run_turn(self, session_id: str, user_message: str) -> ClaudeTurnResult:
        ...
```

内部逻辑：

```text
1. 读取当前 session 状态。
2. 构造 prompt。
3. 进入 medteach-agent-core 工作目录。
4. 设置 DeepSeek 环境变量。
5. 调用 claude -p。
6. 限制超时时间。
7. 解析 JSON 输出。
8. 失败则返回 fallback 结果。
```

### 14.5 推荐 CLI 调用模板

```bash
claude -p "$PROMPT" \
  --append-system-prompt-file ./prompts/demo_runtime_rules.md \
  --output-format json \
  --max-turns 8 \
  --allowedTools "Read" "Bash(python tools/*)"
```

### 14.6 超时策略

```text
方案生成：15 秒超时
创建考试：30 秒超时
获取进度：10 秒超时
生成报告：20 秒超时
推荐病例：20 秒超时
```

超时后：

```text
1. Demo Shell 记录 timeout。
2. 小鲨鱼进入 soft_warning。
3. 大屏显示“已切换演示兜底数据”。
4. 使用 Mock 结果继续流程。
```

---

## 15. 小鲨鱼动画助教设计

### 15.1 形象定位

数字形象不使用真人，不使用云数字人。

MVP 使用本地低成本动画小鲨鱼：

```text
小鲨鱼医学助教
```

气质关键词：

```text
聪明
亲和
专业
温暖
有科技感
不幼稚
不恐怖
不复杂
适合巨鲨品牌
```

### 15.2 视觉建议

小鲨鱼不应该是凶猛鲨鱼，而是“医疗智能助教”的拟人化形象。

建议元素：

```text
圆润鲨鱼头部
白色或浅蓝色医用外套元素
小型听诊器 / 医学徽章
柔和发光边缘
背后有数据光环
眼神专注但友好
嘴部可简单开合
```

### 15.3 动画状态

MVP 至少 8 个状态：

| 状态 | 英文字段 | 动画表现 |
|---|---|---|
| 待命 | idle | 缓慢呼吸、尾巴轻摆 |
| 倾听 | listening | 耳侧声波 / 眼睛聚焦 |
| 思考 | thinking | 头顶气泡 / 光环旋转 |
| 说话 | speaking | 嘴部开合、字幕同步 |
| 执行 | working | 身边数据流动、鳍部轻挥 |
| 等待确认 | waiting_confirm | 轻轻点头、确认按钮高亮 |
| 成功 | success | 微笑、光效闪烁 |
| 兜底提示 | soft_warning | 温和提示，不做强烈报错 |

### 15.4 实现方式

第一版不做 Live2D。

使用：

```text
SVG / PNG 分层素材
CSS Animation
Web Audio API 音量驱动嘴部开合，可选
Vue 组件状态切换
```

建议组件：

```text
AvatarShark.vue
```

Props：

```ts
interface AvatarSharkProps {
  state: 'idle' | 'listening' | 'thinking' | 'speaking' | 'working' | 'waiting_confirm' | 'success' | 'soft_warning'
  text?: string
  audioPlaying?: boolean
}
```

### 15.5 小鲨鱼与 Agent 事件映射

| Claude 输出 shark_state | 前端动画 |
|---|---|
| idle | 呼吸待机 |
| listening | 倾听 |
| thinking | 思考 |
| speaking | 播报 |
| working | 调接口 / 组卷 |
| waiting_confirm | 等待用户确认 |
| success | 完成 |
| soft_warning | 兜底提醒 |

---

## 16. 前端大屏设计

### 16.1 页面定位

大屏要展示“智能体正在工作”，不是展示后台管理页面。

用户看到的重点：

```text
1. 小鲨鱼智能助教在和演示者对话。
2. 智能体理解了考试任务。
3. 智能体正在调用教学平台。
4. 考试被创建并下发。
5. 学员答题进度实时变化。
6. 成绩分析和病例推荐自动生成。
```

### 16.2 页面布局

```text
┌──────────────────────────────────────────────┐
│ 顶部：巨鲨医用教学智能体 / 当前状态 / Demo 模式 │
├───────────────┬──────────────────────────────┤
│ 左侧：小鲨鱼助教 │ 右侧：智能体工作流              │
│ - 动画状态      │ - 识别任务                     │
│ - 对话字幕      │ - 生成方案                     │
│ - 语音识别文本  │ - 查询学员                     │
│                │ - 创建考试                     │
│                │ - 下发考试                     │
│                │ - 阅卷分析                     │
├───────────────┴──────────────────────────────┤
│ 下方：考试方案 / 答题进度 / 成绩分析 / 病例推荐 │
└──────────────────────────────────────────────┘
```

### 16.3 顶部状态栏

展示：

```text
当前任务：安排胸部 CT 基础诊断考试
当前阶段：等待方案确认
模式：Mock 演示 / 真实接口
Claude Core：运行中 / 超时 / 兜底
```

### 16.4 工作流区域

固定展示 10 个步骤：

```text
1. 识别教学任务
2. 生成考试方案
3. 等待讲师确认
4. 查询学员列表
5. 创建考试草稿
6. 展示试卷预览
7. 下发考试
8. 监控答题进度
9. 自动阅卷分析
10. 推荐学习病例
```

每一步状态：

```text
未开始
进行中
已完成
失败
兜底完成
```

### 16.5 考试方案卡片

展示：

```text
考试名称：胸部 CT 基础诊断测评
考试对象：现场规培学员 8 人
考试时长：15 分钟
题型结构：单选 10 道 / 多选 5 道 / 病例分析 2 道
总分：100 分
难度：中级
阅卷方式：客观题自动阅卷，病例题智能辅助点评
```

### 16.6 答题进度卡片

展示：

```text
已下发：8 人
已进入：8 人
答题中：3 人
已提交：5 人
剩余时间：08:30
```

### 16.7 成绩分析卡片

展示：

```text
平均分：78.5
最高分：92
最低分：64
及格率：87.5%
```

### 16.8 薄弱点与病例推荐卡片

展示：

```text
薄弱点：
1. 肺结节良恶性征象判断
2. 磨玻璃影鉴别
3. 结构化报告表达

推荐病例：
1. 右上肺磨玻璃结节鉴别病例
2. 实性肺结节良恶性判断病例
3. 胸部 CT 报告结构化表达训练病例
```

---

## 17. 导演控制台设计

### 17.1 定位

导演台是展厅演示保命工具。

即使 Claude Code 超时、接口失败、语音识别失败、学员未提交，现场技术人员也可以强制推进流程。

### 17.2 入口

```text
/demo-control
```

或快捷键：

```text
Ctrl + Shift + D
```

### 17.3 必做功能

| 功能 | 说明 |
|---|---|
| 重置演示 | 回到 IDLE |
| 切换 Mock / 真实接口 | 一键切换模式 |
| 发送预设指令 | 自动向 Claude Core 发送标准演示话术 |
| 进入方案阶段 | 强制展示默认考试方案 |
| 确认方案 | 强制进入创建考试 |
| 展示试卷预览 | 跳到预览阶段 |
| 下发考试 | 强制进入已下发状态 |
| 模拟学员进入 | 展示 8/8 已进入 |
| 模拟部分提交 | 展示 5/8 已提交 |
| 模拟全部提交 | 展示 8/8 已提交 |
| 生成成绩分析 | 直接展示 Mock 成绩 |
| 推荐病例 | 直接展示 Mock 推荐 |
| Claude Core 状态 | 查看运行中 / 超时 / 错误 |
| 日志查看 | 查看最近 20 条事件 |

---

## 18. 语音与文本输入

### 18.1 MVP 优先级

第一优先级：文本输入 + 快捷指令。

第二优先级：浏览器语音识别。

### 18.2 必须支持的输入方式

```text
1. 文本输入框
2. 快捷按钮：安排考试
3. 快捷按钮：确认方案
4. 快捷按钮：下发考试
5. 快捷按钮：模拟提交
```

### 18.3 可选语音能力

第一版可用浏览器 Web Speech API。

语音识别失败时，演示者可以使用快捷按钮继续。

### 18.4 TTS 播报

第一版可用浏览器 SpeechSynthesis。

后续如公司要求效果，再替换为云 TTS 或本地 TTS。

---

## 19. 教学平台接口适配器

### 19.1 适配原则

Claude Code Core 不直接硬编码教学平台接口地址。

Claude Code 只调用工具脚本。

工具脚本调用适配器。

适配器决定走真实接口还是 Mock。

```text
Claude Code
↓
python tools/create_exam_draft.py
↓
adapter/teaching_platform_client.py
↓
真实教学平台接口 或 mock_client.py
```

### 19.2 必需工具脚本

```text
tools/get_present_students.py
tools/create_exam_draft.py
tools/get_exam_preview.py
tools/publish_exam.py
tools/get_exam_progress.py
tools/get_exam_result.py
tools/recommend_cases.py
```

### 19.3 工具脚本输出要求

所有工具脚本只输出 JSON。

成功示例：

```json
{
  "ok": true,
  "fallback": false,
  "data": {
    "exam_id": "exam_001",
    "status": "draft_created"
  },
  "error": null
}
```

失败但兜底示例：

```json
{
  "ok": true,
  "fallback": true,
  "data": {
    "exam_id": "exam_demo_001",
    "status": "draft_created_mock"
  },
  "error": {
    "type": "real_api_failed",
    "message": "真实接口超时，已切换 Mock 数据。"
  }
}
```

失败且不可恢复示例：

```json
{
  "ok": false,
  "fallback": false,
  "data": null,
  "error": {
    "type": "fatal_error",
    "message": "缺少必要配置 TEACHING_PLATFORM_BASE_URL。"
  }
}
```

---

## 20. Mock 机制

### 20.1 必须支持 Mock

展厅演示不能依赖真实接口稳定性。

MVP 必须支持：

```text
DEMO_MODE=mock
DEMO_MODE=real
DEMO_MODE=hybrid
```

### 20.2 模式解释

| 模式 | 说明 |
|---|---|
| mock | 全部使用本地演示数据 |
| real | 尽量调用真实教学平台接口 |
| hybrid | 优先真实接口，失败自动使用 Mock |

### 20.3 Mock 数据文件

```text
mock/students.json
mock/exam_preview.json
mock/exam_progress_steps.json
mock/exam_result.json
mock/recommended_cases.json
```

### 20.4 兜底策略

| 失败点 | 兜底方式 |
|---|---|
| Claude Code 超时 | Demo Shell 返回预设话术 |
| 学员接口失败 | 使用 8 名固定学员 |
| 创建考试失败 | 返回 exam_demo_001 |
| 下发考试失败 | 使用模拟二维码 |
| 进度接口失败 | 使用预设进度动画 |
| 成绩接口失败 | 使用预设成绩报告 |
| 推荐接口失败 | 使用本地病例 JSON |

---

## 21. 状态机设计

虽然 Agent Core 使用 Claude Code，但外层 Demo Shell 仍需要演示状态机。

状态机不是为了替代 Claude Code，而是为了保证展厅流程不乱。

```text
IDLE
↓
INTENT_RECOGNIZED
↓
PLAN_PROPOSED
↓
WAITING_PLAN_CONFIRM
↓
CREATING_EXAM
↓
EXAM_PREVIEW_READY
↓
WAITING_PUBLISH_CONFIRM
↓
PUBLISHING_EXAM
↓
EXAM_PUBLISHED
↓
MONITORING_PROGRESS
↓
GRADING
↓
REPORT_READY
↓
RECOMMENDING
↓
DONE
```

### 21.1 状态和小鲨鱼映射

| 状态 | 小鲨鱼状态 | 大屏表现 |
|---|---|---|
| IDLE | idle | 等待任务 |
| INTENT_RECOGNIZED | thinking | 已识别任务 |
| PLAN_PROPOSED | speaking | 展示考试方案 |
| WAITING_PLAN_CONFIRM | waiting_confirm | 等待确认 |
| CREATING_EXAM | working | 调用平台创建考试 |
| EXAM_PREVIEW_READY | speaking | 展示试卷预览 |
| WAITING_PUBLISH_CONFIRM | waiting_confirm | 等待下发 |
| PUBLISHING_EXAM | working | 下发考试 |
| EXAM_PUBLISHED | success | 显示答题入口 |
| MONITORING_PROGRESS | working | 答题进度变化 |
| GRADING | thinking | 自动阅卷中 |
| REPORT_READY | speaking | 成绩分析 |
| RECOMMENDING | working | 推荐病例 |
| DONE | success | 演示完成 |

---

## 22. 前后端 API

### 22.1 发送用户消息

```http
POST /api/demo/message
```

请求：

```json
{
  "session_id": "demo_001",
  "message": "帮我给今天现场的规培学员安排一场胸部 CT 基础考试"
}
```

响应：

```json
{
  "ok": true,
  "state": "PLAN_PROPOSED",
  "assistant_text": "好的。我建议安排一场 15 分钟的胸部 CT 基础测评……",
  "shark_state": "speaking",
  "need_user_confirmation": true,
  "screen_events": []
}
```

### 22.2 确认当前方案

```http
POST /api/demo/confirm
```

请求：

```json
{
  "session_id": "demo_001",
  "confirmation_type": "confirm_plan"
}
```

### 22.3 下发考试

```http
POST /api/demo/publish
```

请求：

```json
{
  "session_id": "demo_001"
}
```

### 22.4 导演台推进

```http
POST /api/demo/control/step
```

请求：

```json
{
  "session_id": "demo_001",
  "target_state": "REPORT_READY"
}
```

### 22.5 重置演示

```http
POST /api/demo/reset
```

请求：

```json
{
  "session_id": "demo_001"
}
```

### 22.6 切换模式

```http
POST /api/demo/mode
```

请求：

```json
{
  "mode": "hybrid"
}
```

---

## 23. WebSocket 事件

路径：

```text
/ws/demo/{session_id}
```

事件类型：

```text
assistant_message
shark_state_update
workflow_update
tool_call_update
exam_plan_update
exam_preview_update
exam_progress_update
exam_result_update
case_recommendation_update
core_status_update
demo_reset
```

示例：

```json
{
  "type": "shark_state_update",
  "data": {
    "state": "working",
    "text": "我正在匹配胸部 CT 基础题库。"
  }
}
```

---

## 24. 标准演示脚本

### 24.1 开始

演示者：

```text
帮我给今天现场的规培学员安排一场胸部 CT 基础考试，时间控制在 15 分钟。
```

小鲨鱼：

```text
好的。我建议安排一场 15 分钟的胸部 CT 基础测评，面向今天现场的 8 名规培学员。题型包括单选题 10 道、多选题 5 道、病例分析题 2 道，总分 100 分，难度为中级。是否按这个方案准备？
```

### 24.2 确认

演示者：

```text
可以。
```

小鲨鱼：

```text
已确认。我现在开始查询学员、匹配题库并创建考试草稿。
```

大屏显示：

```text
正在查询现场学员……
正在匹配胸部 CT 题库……
正在创建考试草稿……
试卷预览已完成。
```

### 24.3 下发

演示者：

```text
下发。
```

小鲨鱼：

```text
考试已下发给 8 名学员。我会持续跟踪答题进度。
```

### 24.4 答题进度

大屏显示：

```text
已下发：8 人
已进入：8 人
答题中：3 人
已提交：5 人
```

导演台可点击：

```text
模拟全部提交
```

### 24.5 阅卷和推荐

小鲨鱼：

```text
本次考试已完成。平均分 78.5 分，主要薄弱点集中在肺结节良恶性判断、磨玻璃影鉴别和结构化报告表达。我建议下一阶段安排肺结节专题训练，并推荐 6 个典型病例用于复训。
```

---

## 25. 开发排期

### 第 1 阶段：项目骨架，2 天

交付：

```text
Vue 大屏骨架
小鲨鱼 AvatarShark 组件雏形
FastAPI Demo Shell
WebSocket 推送
Mock 数据加载
导演台基础页面
```

### 第 2 阶段：Claude Code Core 接入，2—3 天

交付：

```text
medteach-agent-core 目录
CLAUDE.md
arrange_exam Skill
DeepSeek 环境变量配置
Claude Code CLI 调用封装
JSON 输出解析
超时处理
```

### 第 3 阶段：黄金路径，3—4 天

交付：

```text
安排考试 → 方案生成 → 确认 → 创建考试 → 预览 → 下发 → 进度 → 成绩 → 推荐
全流程 Mock 跑通
大屏事件完整展示
小鲨鱼状态联动
```

### 第 4 阶段：教学平台接口适配，3—5 天

交付：

```text
固定账号登录
学员查询接口
创建考试接口
下发考试接口
成绩查询接口
真实 / Mock / Hybrid 模式
接口失败兜底
```

### 第 5 阶段：展厅包装，2—3 天

交付：

```text
小鲨鱼动画优化
大屏视觉优化
TTS 播报
快捷指令
导演台完善
部署脚本
演示文档
```

预计总周期：

```text
10—15 个工作日
```

---

## 26. 项目目录建议

```text
medteach-agent-demo/
  frontend/
    src/
      pages/
        BigScreen.vue
        DemoControl.vue
      components/
        AvatarShark.vue
        WorkflowPanel.vue
        ExamPlanCard.vue
        ExamProgressPanel.vue
        ExamResultPanel.vue
        CaseRecommendPanel.vue
        CoreStatusPanel.vue
      stores/
        demoStore.ts
      api/
        demoApi.ts
      assets/
        shark/
          shark_idle.svg
          shark_listening.svg
          shark_thinking.svg
          shark_speaking.svg
          shark_working.svg
          shark_success.svg

  backend/
    app/
      main.py
      config.py
      session_store.py
      state_machine.py
      claude_code_client.py
      ws_manager.py
      routes/
        demo.py
        control.py
      models/
        demo_session.py
        claude_result.py
        screen_event.py
      fallback/
        fallback_service.py

  medteach-agent-core/
    CLAUDE.md
    .claude/
      skills/
        arrange_exam/
          SKILL.md
          slot_schema.json
          demo_defaults.json
          response_templates.json
          tool_contracts.json
          fallback_policy.md
    prompts/
      demo_runtime_rules.md
      output_schema.md
    tools/
      get_present_students.py
      create_exam_draft.py
      get_exam_preview.py
      publish_exam.py
      get_exam_progress.py
      get_exam_result.py
      recommend_cases.py
    adapter/
      teaching_platform_client.py
      mock_client.py
      auth_client.py
    mock/
      students.json
      exam_preview.json
      exam_progress_steps.json
      exam_result.json
      recommended_cases.json

  docs/
    demo_script.md
    deployment.md
    api_mapping.md
    troubleshooting.md
```

---

## 27. 验收标准

### 27.1 功能验收

| 验收项 | 标准 |
|---|---|
| Claude Code Core 可调用 | Demo Shell 能成功启动 claude -p |
| DeepSeek API 可接入 | Claude Code 使用 DeepSeek API 响应 |
| Skill 可触发 | 输入安排考试后触发 arrange_exam 流程 |
| JSON 可解析 | Demo Shell 能解析 Claude 输出 |
| 小鲨鱼可联动 | 根据 shark_state 切换动画 |
| 大屏可展示流程 | 工作流步骤可变化 |
| 可生成考试方案 | 展示题型、题量、时长、难度 |
| 可确认方案 | 确认后进入创建考试 |
| 可下发考试 | 下发后进入答题进度 |
| 可展示成绩 | 显示平均分、最高分、薄弱点 |
| 可推荐病例 | 显示推荐病例列表 |
| 导演台可兜底 | 可强制推进任意关键阶段 |
| Mock 可切换 | 接口失败不影响演示 |

### 27.2 演示验收

完整演示时间控制在：

```text
3—5 分钟
```

必须能完成：

```text
发起任务
→ 小鲨鱼响应
→ 生成方案
→ 确认方案
→ 创建考试
→ 展示预览
→ 下发考试
→ 进度变化
→ 成绩分析
→ 病例推荐
```

### 27.3 稳定性验收

以下故障不能导致演示中断：

```text
Claude Code 超时
真实接口失败
语音识别失败
学员未提交
成绩接口不可用
推荐接口不可用
```

每种故障都必须能通过 Mock 或导演台继续演示。

---

## 28. 风险与对策

| 风险 | 表现 | 对策 |
|---|---|---|
| Claude Code 输出不稳定 | JSON 解析失败 | 强制 output_schema；失败走 fallback |
| Claude Code 调用慢 | 现场等待过长 | 设置超时；导演台推进 |
| 权限提示阻塞 | CLI 等待确认 | 限定 allowedTools；预配置权限；隔离环境 |
| DeepSeek API 不稳定 | 响应超时 | 预设话术 + Mock 流程 |
| 教学平台接口失败 | 创建或下发失败 | hybrid 模式自动兜底 |
| 小鲨鱼效果弱 | 演示观感不足 | 优先优化状态动画和字幕，而不是口型 |
| 语音识别失败 | 用户话没识别 | 文本输入和快捷按钮兜底 |
| 现场流程拖慢 | 学员答题耗时 | 导演台模拟提交 |

---

## 29. 部署建议

### 29.1 推荐部署方式

```text
单机 Docker Compose
```

服务：

```text
frontend：Vue 静态资源 / Nginx
backend：FastAPI Demo Shell
agent-core：作为 backend 挂载目录，不单独起服务
```

### 29.2 环境变量

```env
DEMO_MODE=hybrid
DEEPSEEK_API_KEY=xxxx
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=xxxx
ANTHROPIC_MODEL=deepseek-v4-pro[1m]
TEACHING_PLATFORM_BASE_URL=https://xxx
TEACHING_PLATFORM_USERNAME=demo_teacher
TEACHING_PLATFORM_PASSWORD=xxxx
CLAUDE_CORE_DIR=/app/medteach-agent-core
CLAUDE_TIMEOUT_SECONDS=30
```

### 29.3 展厅启动命令

```bash
docker compose up -d
```

或本地开发：

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

cd frontend
npm run dev
```

---

## 30. 最终 MVP 范围总结

本 MVP 的最终范围是：

> 做一个围绕“安排一场胸部 CT 基础诊断考试”的展厅智能体 Demo。底层采用接入 DeepSeek API 的 Claude Code CLI 作为 Agent Core；外层 Demo Shell 负责交互、状态、兜底、大屏事件和导演台；前端使用本地小鲨鱼动画助教承载智能体形象；通过教学平台接口或 Mock 数据完成考试创建、下发、答题进度、阅卷分析和病例推荐的完整演示闭环。

一句话原则：

> Claude Code 负责“像智能体一样做事”，Demo Shell 负责“让它稳定、可控、好演示”。

---

## 31. 参考依据

- DeepSeek 官方文档支持通过 Anthropic 兼容接口集成 Claude Code，并提供相关环境变量配置。
- Claude Code CLI 支持 `claude -p` 非交互调用、`--output-format json / stream-json` 输出、`--max-turns` 限制回合、`--allowedTools` 限制工具权限。
- Claude Skills 采用文件系统目录结构，通过 `SKILL.md` 和相关资源文件实现渐进加载，适合把“安排考试”这类稳定流程沉淀为 Skill。
- Claude Code Hooks 可在生命周期节点执行命令或 HTTP Hook，后续可用于日志、审计、状态同步或自动兜底增强。
