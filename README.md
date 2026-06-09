# 巨鲨医用教学智能体 · 展厅 Demo (MVP)

> Claude Code Agent Core · DeepSeek · 阿里云语音交互 TTS · Vue 3 双大屏

围绕黄金路径 **「安排一场胸部 CT 基础诊断考试」**，将 AI 助教从「识别任务 → 生成方案 → 讲师确认 → 下发考试 → 监考进度 → 自动阅卷 → 病例推荐」的完整闭环，做成可在展厅现场演示的交互系统。

## ✨ 演示形态

| 页面 | 路径 | 作用 |
| --- | --- | --- |
| 🏠 导览 | `/home` | 入口导航 |
| 🖥 展厅大屏 | `/screen` | 动态展示智能体动作、阶段成果与最终成果（含工作流、考试方案、答题进度、阅卷分析、病例推荐、实时事件流） |
| 🦈 数字形象 | `/avatar` | 会随当前动作动态变形的小鲨鱼助教「鲨鲨」，支持语音播报与语音/文字交互 |
| 🎬 导演控制台 | `/control` | 展厅保命工具：推进流程、强制跳转、模式切换、自定义指令 |

> 建议：**大屏**与**数字形象**分屏 / 双显示器展示，**导演控制台**用平板或副屏操控。

## 🧱 架构

```
medteach_agent_demo/
├── medteach-agent-core/   # Claude Code Agent 核心：CLAUDE.md / skills / tools / mock 数据
├── backend/               # FastAPI「Demo Shell」：编排器 + WebSocket 推送 + 阿里云 TTS 代理
└── frontend/              # Vue 3 + Vite 前端：大屏 / 数字形象 / 控制台 三视图
```

- **Demo Shell（后端）** 是稳定性的核心：默认 `AGENT_MODE=simulated`，用确定性编排驱动黄金路径，按节奏通过 WebSocket 广播状态与事件；可选 `AGENT_MODE=claude` 调用真实 Claude Code CLI。
- **TTS** 在服务端完成阿里云 NLS 鉴权（`CreateToken` HMAC-SHA1 签名，自动缓存 Token），返回 `audio/mpeg`；未配置凭据时自动回退浏览器 `SpeechSynthesis`。
- **前端** 三个视图共享同一个 Pinia store，通过 WebSocket 接收快照与事件并渲染动效。

## 🚀 快速开始

前置：**Python 3.12+**、**Node 18+**。

### 方式一：一键脚本（单端口，推荐展厅使用）

```bash
./start.sh
```

脚本会：构建前端静态资源 → 创建后端虚拟环境并安装依赖 → 由后端在 `:8000` 同时托管前端与 API。

打开：

- 大屏 <http://localhost:8000/screen>
- 数字形象 <http://localhost:8000/avatar>
- 控制台 <http://localhost:8000/control>

### 方式二：开发模式（前后端分离，热更新）

```bash
./dev.sh
```

- 后端 API/WS：<http://localhost:8000>
- 前端 Vite：<http://localhost:5173>（已配置 `/api`、`/ws` 代理到后端）

也可分别手动启动：

```bash
# 后端
cd backend && ./run.sh

# 前端（另开终端）
cd frontend && npm install && npm run dev
```

### 方式三：远程演示（HTTPS，供其他机器访问）

让同一局域网的其他机器访问本开发机进行演示时，请务必用 **HTTPS**：浏览器的
**麦克风 / 语音识别** 只在「安全上下文」下可用，`localhost` 例外，但经 IP 访问必须走
HTTPS，否则数字形象页拿不到麦克风权限、语音交互无法进行。

```bash
# 单端口一键脚本（推荐）：自动生成自签证书并以 HTTPS 启动
HTTPS=1 ./start.sh

# 或开发模式（前端热更新）也走 HTTPS
HTTPS=1 ./dev.sh
```

启动日志会打印局域网访问地址，例如：

```
启动 Demo Shell：https://localhost:8000
局域网其他机器访问：https://192.168.1.23:8000
```

- 其他机器浏览器打开上面的 `https://<本机IP>:8000/avatar`，首次会提示「不安全」（自签
  证书的正常现象），点击「高级 → 继续前往」即可；之后即可正常授予麦克风并语音演示。
- 证书默认生成在 `backend/certs/`（已 gitignore）。如本机 IP 变化或需追加域名：
  `FORCE=1 ./gen_cert.sh` 重建，或 `EXTRA_SAN="IP:10.0.0.5" ./gen_cert.sh` 追加。
- 不加 `HTTPS=1` 时一切照旧走 HTTP，本机 `localhost` 演示不受影响。

## 🔧 配置（阿里云 TTS）

后端首次运行会从 `backend/.env.example` 复制出 `backend/.env`。要启用阿里云语音，填入：

```ini
# 必填
ALIYUN_NLS_APPKEY=你的AppKey

# 二选一：A. 直接给 NLS AccessToken（不是 sk- 开头的大模型 API Key）
ALIYUN_NLS_TOKEN=xxxx
# 或 B. 给 AccessKey，由服务端自动换取 NLS Token（长期运行推荐）
ALIYUN_AK_ID=xxxx
ALIYUN_AK_SECRET=xxxx

ALIYUN_NLS_REGION=cn-shanghai
ALIYUN_NLS_VOICE=zhixiaobai   # 可换 zhixiaomei / aixia / xiaoyun ...
```

> 未配置时，数字形象页会自动使用浏览器内置语音合成，演示仍可正常进行。

### 其它关键环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEMO_MODE` | `hybrid` | `mock` 全本地 / `real` 仅真实接口 / `hybrid` 优先真实失败回退 |
| `AGENT_MODE` | `simulated` | `simulated` 确定性编排（展厅稳定）/ `claude` 调用真实 Claude Code CLI |
| `STEP_DELAY` | `0.9` | 步骤间节奏（秒） |
| `PROGRESS_DELAY` | `1.4` | 监考进度推进节奏（秒） |
| `CLAUDE_CORE_DIR` | `../medteach-agent-core` | Agent 核心目录（含 mock 数据） |

## 🎬 现场演示脚本

1. 打开 **数字形象**页，点击「进入展厅 · 开启语音」（授予麦克风/音频权限）。
2. 对鲨鲨说 / 点击「安排考试」→ 助教识别任务并生成考试方案。
3. 点击「确认方案」→ 拉取现场学员、创建草稿、生成试卷预览。
4. 点击「下发考试」→ 考试发布，大屏开始滚动**答题进度**。
5. 自动进入**阅卷分析**（平均分、及格率、分数分布、薄弱点）。
6. 自动给出**学习目标与病例推荐**，演示闭环完成。

> 任一步卡顿，用**导演控制台**的「强制跳转（兜底）」直接跳到目标阶段。

## ✅ 已验证

- 后端黄金路径端到端：`IDLE → 等待方案确认 → 等待下发确认 → DONE`，10 个工作流步骤全部完成，事件流完整推送。
- 前端 `npm run build` 通过，三视图 + 控制台在浏览器中渲染与交互正常（含鲨鱼随状态变形、CountUp 数字动画、实时事件流）。
