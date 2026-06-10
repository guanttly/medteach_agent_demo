#!/usr/bin/env python3
"""查询教学计划/教学阅片安排列表（主题、讲师、时间、状态等）。可选参数：[page] [size]。输出 JSON。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    page = int(argv[0]) if len(argv) > 0 else 1
    size = int(argv[1]) if len(argv) > 1 else 10
    client = TeachingPlatformClient()
    print(json.dumps(client.list_teaching_plans(page=page, size=size), ensure_ascii=False))
