---
name: student_management
summary: 学员名册查询 Skill，用于查询现场在科学员、按关键字检索学员，播报姓名/科室/年级等信息。
---

# 学员管理 Skill

## 触发条件

当用户表达以下意图时触发：

- 现场有哪些学员 / 在科学员名单 / 今天来了哪些人
- 查一下学员 / 看看学员名册 / 学员有多少人
- 某某（姓名/工号）在不在 / 帮我找一下某学员

## 行为流程（只读，无需确认）

1. 识别用户想查看或检索学员。
2. 默认调用 `tools/get_present_students.py` 取现场在科学员名册；
   若用户提供了关键字（姓名/工号），改调用 `tools/search_students.py <keyword>`。
3. 根据返回的 `students[]`（id/name/department/grade/color）与 `total` 生成播报。
4. 输出 `students_ready` 大屏事件，把名册推上大屏。
5. 简洁总结人数与构成，可引导用户进入「安排考试」。

## 工具

见 `tool_contracts.json`。本 Skill 为只读查询，不需要用户确认。

## 大屏事件要求

- `intent_recognized`
- `tool_call_started` / `tool_call_succeeded` / `tool_call_failed`
- `students_ready`

## 小鲨鱼状态要求

- 倾听：`listening`，思考：`thinking`，调用工具：`working`，播报：`speaking`，成功：`success`，兜底：`soft_warning`

## 兜底策略

学员接口失败时使用 `mock/students.json` 的固定学员名册继续演示，事件标记 `fallback=true`，小鲨鱼 `soft_warning`，绝不报错卡死。
