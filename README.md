# 通用工作流引擎 (Common Workflow)

[![CI](https://github.com/Littlewit/workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/Littlewit/workflow/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

轻量级、高性能、可视化的**通用工作流引擎**。参考飞书/钉钉审批流体验，但更侧重通用性、可嵌入性与开发者友好度——不局限于 OA 审批，同样适配业务编排、数据管道等场景。

## ✨ 核心特性

- 🎨 **可视化编排**：基于 LogicFlow 的拖拽式流程设计器，审批流风格自定义节点，Undo/Redo、画布校验、保存/发布闭环
- ⚙️ **自研 JSON DSL**：轻量灵活、前后端同构（Pydantic → TypeScript 类型同源），发布时权威校验 + 版本快照不可变
- 🔀 **完整流转能力**：串行 / 排他网关 / 并行网关（AND/OR 汇合）/ 会签（ALL/ANY/ratio）/ 驳回重走 / 转办 / 撤回 / 加签
- ⏱️ **超时 SLA**：节点级超时策略（提醒 / 自动转交 / 自动同意 / 自动拒绝），ARQ 定时扫描，幂等防误触发
- 🪝 **事件驱动**：Outbox 模式事件流水（at-least-once 投递）、Webhook 出站签名（HMAC-SHA256）+ 指数退避重试 + 死信记录
- 🔐 **安全**：JWT 认证 + RBAC、开放接口签名防重放（appKey + 时间戳 + Nonce）、字段级表单权限、审计事件流水
- 🛡️ **高可靠**：Redis 分布式锁（无 Redis 自动降级行锁）、operationId 幂等、乐观锁兜底、失败重试 ≥3 次
- 📊 **监控运维**：流程追踪时间线与运行态高亮、节点瓶颈分析看板、traceId 全链路追踪
- 🚀 **高性能**：全链路 async/await，单节点流转 p50 ≈ 23ms（SQLite 本机基线）

## 🏗️ 架构

```text
┌───────────────────── 前端 Vue3 + TS ─────────────────────┐
│  流程设计器(LogicFlow)  审批中心  表单渲染器  监控看板      │
└──────────────────────────┬───────────────────────────────┘
                           │ REST / JWT
┌──────────────────────────▼───────────────────────────────┐
│ FastAPI ──▶ Application Service ──▶ Workflow Engine Core │
│                │                    DSL解析/状态机/网关   │
│                │                    Token推进/事件总线     │
│         ARQ Worker ◀── Outbox事件 ◀── 插件体系            │
└──────┬──────────────┬──────────────┬─────────────────────┘
       ▼              ▼              ▼
  PostgreSQL/     Redis(锁/幂等)   Webhook/通知渠道
  SQLite(开发)
```

## 📂 项目结构

```text
workflow/
├── backend/          # FastAPI 后端（引擎内核/应用服务/API）  → backend/README.md
├── frontend/         # Vue3 前端（设计器/审批中心/看板）      → frontend/README.md
├── .codebuddy/docs/  # 需求规格 / 系统设计 / 详细设计 / 编码计划
└── .github/workflows/
```

## 🚀 快速开始

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell；Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env              # 开发默认 SQLite，无需额外依赖
alembic upgrade head
uvicorn app.main:app --reload
# API 文档: http://localhost:8000/docs
```

### 前端

```bash
cd frontend
npm install
npm run dev       # 代理 /api → localhost:8000
# 页面: http://localhost:5173
```

### 体验端到端流程

1. 使用 `admin / admin123` 登录（内置账号见 `backend/app/core/security.py`）
2. **流程定义** → 新建流程 → 画布编排 → 保存 → 发布
3. 切换 `bob / bob123` → **发起流程** → 填表提交
4. 切换 `alice / alice123` → **我的待办** → 同意/驳回
5. 实例详情 → **查看流程图** → 运行态高亮追踪

## ⚙️ 环境变量（前缀 `WF_`）

| 变量 | 默认 | 说明 |
| :--- | :--- | :--- |
| `WF_DATABASE_URL` | `sqlite+aiosqlite:///./workflow.db` | 生产切换 `postgresql+asyncpg://...` |
| `WF_REDIS_URL` | `redis://localhost:6379` | 锁/幂等/队列；无 Redis 自动降级内存实现 |
| `WF_JWT_SECRET` | dev-only 密钥 | **生产必须覆盖** |
| `WF_DEBUG` | `true` | 调试模式 |

启动 ARQ Worker（超时扫描 + Outbox 投递，需 Redis）：

```bash
cd backend
.venv\Scripts\arq app.worker.WorkerSettings
```

## 🧪 测试

```bash
cd backend
pytest -q          # 66 用例：引擎单测 + SQLite 集成 + API 契约
ruff check .
mypy app
```

## 📈 性能压测

```bash
cd backend
python scripts/benchmark.py 200 50    # [流转次数] [并发数]
```

| 指标 | 目标（需求 §4） | SQLite 本机基线 |
| :--- | :--- | :--- |
| 单节点流转延迟 p50 | < 50ms | ✅ ≈ 23ms |
| 流程发起吞吐 | 1000+ QPS | 59 QPS（单文件库上限，需 PG + 多 worker 达标） |

## 📌 Roadmap

- [x] M1-M4：引擎内核 / 持久化 / API / 认证
- [x] M5：ARQ / 超时 SLA / Webhook / 开放接口 / 并行网关
- [x] M6：设计器 / 表单渲染器 / 审批中心 / 追踪高亮 / 类型生成 CI
- [x] M7：监控看板 / 性能压测
- [ ] 企微 / 钉钉 / 飞书通知渠道实装（当前为日志桩）
- [ ] BPMN 2.0 XML 导出
- [ ] 移动端深度适配

## 📄 License

MIT
