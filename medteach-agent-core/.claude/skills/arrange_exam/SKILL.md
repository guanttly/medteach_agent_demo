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

如果用户信息不足，使用以下默认值（见 `demo_defaults.json`）：

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
4. 在用户确认方案前，不调用 `create_exam_draft`。
5. 用户确认后，调用 `tools/create_exam_draft.py`。
6. 创建成功后，调用 `tools/get_exam_preview.py`。
7. 展示试卷预览，并询问是否下发。
8. 用户明确说"下发"后，调用 `tools/publish_exam.py`。
9. 下发后，调用 `tools/get_exam_progress.py` 或等待导演台模拟进度。
10. 学员全部提交后，调用 `tools/get_exam_result.py`。
11. 根据薄弱点调用 `tools/recommend_cases.py`。
12. 输出总结。

## 大屏事件要求

每个关键动作都要生成 `screen_event`：

`intent_recognized` / `plan_proposed` / `waiting_user_confirmation` /
`tool_call_started` / `tool_call_succeeded` / `tool_call_failed` /
`exam_preview_ready` / `exam_published` / `progress_updated` /
`report_ready` / `recommendation_ready` / `demo_done`

## 小鲨鱼状态要求

- 待命：`idle`
- 倾听：`listening`
- 思考：`thinking`
- 说话：`speaking`
- 调用工具：`working`
- 等待确认：`waiting_confirm`
- 成功完成：`success`
- 错误兜底：`soft_warning`
