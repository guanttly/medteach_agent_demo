"""前台交互 / 后台工作流解耦运行时。

按 docs/interaction_workflow_decoupling_plan.md 实现：
- 前台交互通道（Conversation Gateway + Foreground）：即时接话、上下文问答、打断。
- 后台工作流通道（Workflow Engine）：以 job 为单位执行业务，写 facts、发事件，不阻塞前台。
- 播报聚合（Narration Aggregator）：合并/去重后台积压进度与结果，再进 TTS。
- 事实解析（Facts Resolver）：上下文问答先走确定性 facts，再决定是否模型润色。
"""
from __future__ import annotations
