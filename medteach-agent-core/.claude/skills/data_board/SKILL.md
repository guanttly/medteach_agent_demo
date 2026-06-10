---
name: data_board
summary: 教学/考试综合数据看板查询 Skill，用于播报考试数、试卷数、题量、平均分及题型/难度分布等整体概览。
---

# 教学数据看板 Skill

## 触发条件

当用户表达以下意图时触发：

- 看一下数据看板 / 数据概览 / 整体情况
- 现在一共有多少场考试 / 多少套试卷 / 题库有多少题
- 教学整体跑得怎么样 / 给我个总览
- 平台数据 / 运营情况 / 统计数据

## 行为流程（只读，无需确认）

1. 识别用户想看整体教学/考试数据。
2. 调用 `tools/get_data_board.py`。
3. 根据返回的 `exam`（考试数/试卷数/题量/平均分/难度分布/题型分布）与 `edu`（教学场次/直播数/教学类型分布）生成播报。
4. 输出 `data_board_ready` 大屏事件，把核心指标推上大屏。
5. 一句话总结整体态势，可顺势引导用户进入「安排考试」「查看成绩」等下一步。

## 工具

见 `tool_contracts.json`。本 Skill 为只读查询，不涉及写操作，不需要用户确认。

## 大屏事件要求

- `intent_recognized`
- `tool_call_started` / `tool_call_succeeded` / `tool_call_failed`
- `data_board_ready`

## 小鲨鱼状态要求

- 倾听：`listening`
- 思考：`thinking`
- 调用工具：`working`
- 播报结果：`speaking`
- 成功：`success`
- 兜底：`soft_warning`

## 兜底策略

`get_data_board` 失败时使用 `mock` 看板数据继续播报，事件标记 `fallback=true`，小鲨鱼进入 `soft_warning`，大屏温和提示"已切换演示兜底数据"，绝不在观众面前报错卡死。
