#!/usr/bin/env python3
"""获取已创建考试的试卷预览。输出 JSON。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

if __name__ == "__main__":
    client = TeachingPlatformClient()
    print(json.dumps(client.get_exam_preview(), ensure_ascii=False))
