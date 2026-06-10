---
name: exam_grading
summary: 阅卷成绩分析 Skill，用于播报考试平均分、通过率、分数分布、最高/最低分及薄弱点分析。
---

# 阅卷成绩分析 Skill

## 触发条件

当用户表达以下意图时触发：

- 看一下成绩 / 阅卷结果 / 分数怎么样
- 平均分多少 / 通过率多少 / 最高分是谁
- 这次考试报告 / 分析一下成绩 / 薄弱点在哪

## 行为流程（只读，无需确认）

1. 识别用户想看阅卷成绩与分析。
2. 调用 `tools/get_exam_result.py`（默认取最近一场已结束考试）。
3. 根据返回的 `summary`（average/highest/lowest/pass_rate/submitted/total）、
   `score_distribution[]`、`students[]`、`weak_points[]` 生成播报。
4. 输出 `report_ready` 大屏事件，把成绩概览与薄弱点推上大屏。
5. 总结薄弱点，自然引导用户进入「病例推荐」做复训闭环。
6. 只输出教学分析和训练建议，不输出临床诊断建议。

## 工具

见 `tool_contracts.json`。本 Skill 为只读查询，不需要用户确认。

## 大屏事件要求

- `intent_recognized`
- `tool_call_started` / `tool_call_succeeded` / `tool_call_failed`
- `report_ready`

## 小鲨鱼状态要求

- 倾听：`listening`，思考：`thinking`，调用工具：`working`，播报：`speaking`，成功：`success`，兜底：`soft_warning`

## 兜底策略

成绩接口失败时使用 `mock/exam_result.json` 预设成绩继续演示，事件标记 `fallback=true`，小鲨鱼 `soft_warning`，绝不报错卡死。
