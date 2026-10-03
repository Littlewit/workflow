"""导出 OpenAPI schema 到 frontend/openapi.json（前端类型生成的事实源）。

用法：`python scripts/export_openapi.py`（本地或 CI 中运行）。
前端通过 `npm run gen:api` 将其转换为 src/api/schema.d.ts，
CI 用 git diff 校验"后端契约变更必须同步提交类型文件"。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app  # noqa: E402

out = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
out.write_text(
    json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"written: {out}")
