---
name: question_bank
summary: 题库查询 Skill，用于播报题库题目列表、题型/器官/难度构成与总题量。
---

# 题库查询 Skill

## 触发条件

当用户表达以下意图时触发：

- 题库里有哪些题 / 题目列表 / 查一下题库
- 一共有多少道题 / 单选题多少 / 有哪些题型
- 看看某个器官/难度的题

## 行为流程（只读，无需确认）

1. 识别用户想查看题库。
2. 调用 `tools/list_questions.py`。
3. 根据返回的 `total` 与 `questions[]`（content/type/organ/difficulty/creator）生成播报。
4. 输出 `question_bank_ready` 大屏事件，把题目列表与构成推上大屏。
5. 简洁总结题量与题型构成，可引导用户进入「安排考试」组卷。

## 工具

见 `tool_contracts.json`。本 Skill 为只读查询，不需要用户确认。

## 大屏事件要求

- `intent_recognized`
- `tool_call_started` / `tool_call_succeeded` / `tool_call_failed`
- `question_bank_ready`

## 小鲨鱼状态要求

- 倾听：`listening`，思考：`thinking`，调用工具：`working`，播报：`speaking`，成功：`success`，兜底：`soft_warning`

## 兜底策略

题库接口失败时使用 `mock` 预设题目继续演示，事件标记 `fallback=true`，小鲨鱼 `soft_warning`，绝不报错卡死。
