#!/usr/bin/env python3
"""查询教学/考试综合数据看板（考试数、试卷数、题量、教学场次等）。输出 JSON。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

if __name__ == "__main__":
    client = TeachingPlatformClient()
    print(json.dumps(client.get_data_board(), ensure_ascii=False))
