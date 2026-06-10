---
name: teaching_plan
summary: 教学计划查询 Skill，用于播报教学阅片/教学安排列表（主题、讲师、时间、状态）。
---

# 教学计划 Skill

## 触发条件

当用户表达以下意图时触发：

- 教学计划 / 教学安排 / 教学阅片
- 最近有哪些教学活动 / 排课情况 / 谁来讲课
- 看看教学日程

## 行为流程（只读，无需确认）

1. 识别用户想查看教学计划/教学阅片安排。
2. 调用 `tools/list_teaching_plans.py`。
3. 根据返回的 `total` 与 `plans[]`（subject/type/education_time/end_time/lecturers/teachers/status）生成播报。
4. 输出 `teaching_plan_ready` 大屏事件，把教学安排推上大屏。
5. 简洁总结近期教学安排。

## 工具

见 `tool_contracts.json`。本 Skill 为只读查询，不需要用户确认。

## 大屏事件要求

- `intent_recognized`
- `tool_call_started` / `tool_call_succeeded` / `tool_call_failed`
- `teaching_plan_ready`

## 小鲨鱼状态要求

- 倾听：`listening`，思考：`thinking`，调用工具：`working`，播报：`speaking`，成功：`success`，兜底：`soft_warning`

## 兜底策略

教学计划接口失败时使用 `mock` 预设安排继续演示，事件标记 `fallback=true`，小鲨鱼 `soft_warning`，绝不报错卡死。
