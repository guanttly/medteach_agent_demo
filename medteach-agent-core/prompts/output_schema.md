# 输出 JSON Schema（output_schema）

每轮回复输出如下结构：

```json
{
  "assistant_text": "string，给用户听到的话",
  "next_state": "IDLE | INTENT_RECOGNIZED | PLAN_PROPOSED | WAITING_PLAN_CONFIRM | CREATING_EXAM | EXAM_PREVIEW_READY | WAITING_PUBLISH_CONFIRM | PUBLISHING_EXAM | EXAM_PUBLISHED | MONITORING_PROGRESS | GRADING | REPORT_READY | RECOMMENDING | DONE",
  "need_user_confirmation": true,
  "confirmation_type": "confirm_plan | confirm_publish | null",
  "shark_state": "idle | listening | thinking | speaking | working | waiting_confirm | success | soft_warning",
  "screen_events": [
    {
      "type": "plan_proposed",
      "title": "已生成考试方案",
      "message": "胸部 CT 基础诊断测评，15 分钟，17 道题，总分 100 分。",
      "status": "completed",
      "fallback": false,
      "payload": {}
    }
  ],
  "exam_plan": {},
  "tool_results": [],
  "error": null
}
```

字段说明：

- `assistant_text`：字幕 + TTS 播报文本。
- `shark_state`：驱动小鲨鱼动画。
- `screen_events[]`：推送大屏，`status` ∈ `pending|running|completed|failed|fallback`。
- `next_state`：演示状态机的下一状态。
- `need_user_confirmation` / `confirmation_type`：控制确认按钮与流程锁。
- `tool_results[]`：工具调用结果，结构 `{ name, ok, fallback, data, error }`。
- `error`：致命错误信息，正常为 `null`。
