#!/usr/bin/env python3
"""查询现场参加考试的学员列表。输出 JSON。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

if __name__ == "__main__":
    client = TeachingPlatformClient()
    print(json.dumps(client.get_present_students(), ensure_ascii=False))
