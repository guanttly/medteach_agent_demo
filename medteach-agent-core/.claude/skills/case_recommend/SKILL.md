---
name: case_recommend
summary: 复训病例推荐 Skill，用于根据薄弱点或下一阶段目标推荐典型训练病例。
---

# 病例推荐 Skill

## 触发条件

当用户表达以下意图时触发：

- 推荐几个病例 / 复训病例 / 训练病例
- 下一阶段练什么 / 给学员安排点病例
- 针对薄弱点推荐病例

## 行为流程（只读，无需确认）

1. 识别用户想要复训病例推荐。
2. 调用 `tools/recommend_cases.py`。
3. 根据返回的 `next_goal` 与 `cases[]`（title/focus/difficulty/tags/est_minutes）生成播报。
4. 输出 `recommendation_ready` 大屏事件，把推荐病例推上大屏。
5. 总结下一阶段训练目标，形成"考试→分析→复训"教学闭环。
6. 只输出教学训练建议，不输出临床诊断建议。

## 工具

见 `tool_contracts.json`。本 Skill 为只读查询，不需要用户确认。

## 大屏事件要求

- `intent_recognized`
- `tool_call_started` / `tool_call_succeeded` / `tool_call_failed`
- `recommendation_ready`

## 小鲨鱼状态要求

- 倾听：`listening`，思考：`thinking`，调用工具：`working`，播报：`speaking`，成功：`success`，兜底：`soft_warning`

## 兜底策略

推荐接口为空或失败时使用 `mock/recommended_cases.json` 继续演示，事件标记 `fallback=true`，小鲨鱼 `soft_warning`，绝不报错卡死。
