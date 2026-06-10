---
name: exam_monitoring
summary: 考试监考 Skill，用于查询考试列表与实时答题进度（已发布/进场/作答/交卷人数）。
---

# 考试监考 Skill

## 触发条件

当用户表达以下意图时触发：

- 现在有哪些考试 / 考试列表 / 最近的考试
- 考试进行得怎么样 / 答题进度 / 交卷情况 / 监考一下
- 多少人交卷了 / 还有多少人在答题

## 行为流程（只读，无需确认）

1. 识别用户想看考试列表还是某场考试进度。
2. 想看列表 → 调用 `tools/list_exams.py`；
   想看进度 → 调用 `tools/get_exam_progress.py`（默认取最近一场考试）。
3. 根据返回结果生成播报：
   - 列表：考试名、开始时间、时长、总分、状态。
   - 进度：已发布/进场/作答/已交卷/剩余时间。
4. 输出 `exam_list_ready` 或 `progress_updated` 大屏事件。
5. 简洁总结监考态势，可引导进入「阅卷分析」。

## 工具

见 `tool_contracts.json`。本 Skill 为只读查询，不需要用户确认。

## 大屏事件要求

- `intent_recognized`
- `tool_call_started` / `tool_call_succeeded` / `tool_call_failed`
- `exam_list_ready` / `progress_updated`

## 小鲨鱼状态要求

- 倾听：`listening`，思考：`thinking`，调用工具：`working`，播报：`speaking`，成功：`success`，兜底：`soft_warning`

## 兜底策略

考试列表或进度接口失败时使用 `mock` 预设数据继续演示，事件标记 `fallback=true`，小鲨鱼 `soft_warning`，绝不报错卡死。
