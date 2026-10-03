# Workflow Backend

通用工作流引擎后端——FastAPI + SQLAlchemy(async) + ARQ + Redis，开发默认 SQLite。

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

- API 文档：<http://localhost:8000/docs>（OpenAPI 3，前端类型生成的事实源）
- 健康检查：<http://localhost:8000/api/v1/healthz>

## 目录结构

```text
backend/
├── app/
│   ├── api/            # 路由层：认证/定义/实例/任务/开放接口/统计
│   ├── application/    # 用例服务（事务边界）：发起/审批/驳回/转办/撤回/超时/统计
│   ├── engine/         # 引擎内核（纯逻辑，禁框架依赖）
│   │   ├── executor.py       # Token 推进：串行/网关/会签/驳回/转办/撤回
│   │   ├── parser.py         # DSL 六项静态校验 + 表达式沙箱
│   │   ├── state_machine.py  # 实例/任务状态迁移表
│   │   └── resolvers.py      # 审批人解析插件注册表
│   ├── domain/         # DSL 模型(Pydantic 判别联合) + 枚举与状态机字典
│   ├── infra/          # ORM/仓储/Redis/幂等/引擎状态编解码
│   ├── plugins/        # 审批人解析器、通知渠道等插件实现
│   └── worker.py       # ARQ 定时任务：Outbox 投递 + 超时扫描
├── alembic/            # 数据库迁移
├── scripts/            # benchmark.py 压测 / export_openapi.py 契约导出
└── tests/              # engine 单测(纯逻辑) + integration + api
```

## 配置（前缀 `WF_`，见 `.env.example`）

| 变量 | 默认 | 说明 |
| :--- | :--- | :--- |
| `WF_DATABASE_URL` | `sqlite+aiosqlite:///./workflow.db` | 生产：`postgresql+asyncpg://...` |
| `WF_REDIS_URL` | `redis://localhost:6379` | 无 Redis 时锁/幂等自动降级内存实现 |
| `WF_JWT_SECRET` | dev-only | **生产必须覆盖** |

## 测试与检查

```bash
pytest -q            # 引擎单测 + SQLite 集成 + API 测试
ruff check .
mypy app
```

## 数据库迁移

```bash
alembic revision --autogenerate -m "..."   # 生成（需确认无 SQLite 不兼容语句）
alembic upgrade head                        # 应用
alembic downgrade -1                        # 回滚一版
```

## 设计要点

- **DSL 为唯一事实源**：`app/domain/dsl.py`（Pydantic 判别联合），发布后冻结为版本快照，运行实例锁定版本
- **引擎纯逻辑**：`engine/` 不依赖框架，持久化经 `infra/engine_codec.py` 以状态快照方式落地（加载→运算→回写）
- **一致性三防线**：Redis 锁 → 事务内行锁 → `state_version` 乐观锁（if-match）
- **副作用出事务**：通知/Webhook 走 `instance_event` Outbox，worker 周期投递（at-least-once）
- **插件扩展点**：审批人解析器 / 条件执行器 / 通知渠道，实现协议后经注册表注入
