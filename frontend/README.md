# Workflow Frontend

通用工作流引擎前端——Vue 3 + TypeScript(strict) + Vite + Pinia + Ant Design Vue + LogicFlow。

## 快速开始

```bash
npm install
npm run dev       # http://localhost:5173，代理 /api → localhost:8000
npm run build     # vue-tsc 类型检查 + vite 构建
```

内置测试账号（与后端一致）：`admin/admin123`（管理员）、`bob/bob123`（发起人）、`alice/alice123`（审批人）。

## 目录结构

```text
frontend/src/
├── api/
│   ├── request.ts        # axios 封装：JWT 注入/统一错误码/409 冲突提示/响应解包
│   ├── workflow.ts       # 业务接口（逐步替换为 OpenAPI 生成物）
│   └── schema.d.ts       # openapi-typescript 生成的契约类型（CI 校验同步）
├── types/workflow.ts     # WorkflowDSL 类型（与后端 Pydantic 模型对应）
├── stores/
│   ├── auth.ts           # 登录态（token/角色，localStorage 持久化）
│   └── designer.ts       # 设计器：DSL 唯一事实源 + Undo/Redo 快照栈
├── modules/designer/
│   ├── customNodes.ts    # LogicFlow 审批流风格自定义节点（5 类配色）
│   ├── mapping.ts        # DSL ↔ 画布数据双向映射
│   └── validator.ts      # 画布轻校验（权威校验在后端 parser）
├── components/form-renderer/   # JSON Schema 表单渲染器（含字段级权限）
└── views/                # 登录/定义列表/设计器/发起/待办/详情/追踪/监控看板
```

## 脚本

| 命令 | 说明 |
| :--- | :--- |
| `npm run dev` | 开发服务器（`/api` 代理到 8000 端口） |
| `npm run build` | 类型检查 + 生产构建 |
| `npm run gen:api` | 从 `openapi.json` 重新生成 `src/api/schema.d.ts` |

## 设计要点

- **DSL 唯一事实源**：画布坐标（`layout`）与 DSL 分离存储，结构变更统一走 `commit()` 入口保证 Undo/Redo 一致
- **类型同构**：后端 `scripts/export_openapi.py` 导出契约 → `npm run gen:api` 生成类型；CI 用 `git diff` 强制两者同步
- **前后端双校验**：画布轻校验即时反馈，发布以后端 `parser` 六项权威校验为准
- **并发友好**：收到 42100（流转锁）/43102（状态已变）自动提示刷新
