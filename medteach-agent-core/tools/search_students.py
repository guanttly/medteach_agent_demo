#!/usr/bin/env python3
"""检索学员名册。可选参数：keyword [page] [size] [scope(in|out)]。输出 JSON。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    keyword = argv[0] if len(argv) > 0 and argv[0] not in ("", "-") else None
    page = int(argv[1]) if len(argv) > 1 else 1
    size = int(argv[2]) if len(argv) > 2 else 20
    scope = argv[3] if len(argv) > 3 else "in"
    client = TeachingPlatformClient()
    print(
        json.dumps(
            client.search_students(keyword=keyword, page=page, size=size, scope=scope),
            ensure_ascii=False,
        )
    )
