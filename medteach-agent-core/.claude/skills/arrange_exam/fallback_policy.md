# 兜底策略 fallback_policy

展厅演示不能依赖真实接口稳定性。任何工具调用失败时，按以下策略兜底，保证演示不中断。

| 失败点 | 兜底方式 | 内部标记 |
|---|---|---|
| Claude Code 超时 | Demo Shell 返回预设话术 | `fallback=true` |
| 学员接口失败 | 使用 `mock/students.json` 的 8 名固定学员 | `fallback=true` |
| 创建考试失败 | 返回 `exam_demo_001` | `fallback=true` |
| 下发考试失败 | 使用模拟二维码 / 入口链接 | `fallback=true` |
| 进度接口失败 | 使用 `mock/exam_progress_steps.json` 预设进度 | `fallback=true` |
| 成绩接口失败 | 使用 `mock/exam_result.json` 预设成绩 | `fallback=true` |
| 推荐接口失败 | 使用 `mock/recommended_cases.json` | `fallback=true` |

## 原则

1. 永远不要让演示在观众面前报错卡死。
2. 兜底时小鲨鱼进入 `soft_warning`，大屏温和提示"已切换演示兜底数据"。
3. 所有兜底数据都必须在事件里标记 `fallback=true`，导演台可见。
4. 兜底完成后继续推进流程，不回退。
