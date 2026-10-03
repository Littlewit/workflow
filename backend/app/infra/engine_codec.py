"""引擎内存状态 <-> JSONB 快照 的双向编解码。

持久化策略（M3）：以 ExecutionState 整体快照存于 workflow_instance.engine_state，
每次流转在同一事务内"加载快照 → 引擎运算 → 回写快照 + 镜像任务表"。
相比逐行同步任务/Token，快照方案实现简单且天然一致；行级查询需求
（待办列表）由 task_instance 镜像表承担。
"""

from dataclasses import asdict

from app.domain.dsl import WorkflowDSL
from app.domain.enums import InstanceStatus, TaskAction, TaskStatus
from app.engine.executor import EngineTask, EngineToken, ExecutionState


def serialize_tasks(state: ExecutionState) -> list[dict]:
    """将任务列表序列化为 dict（镜像表写入与状态快照共用）。"""
    return [
        {
            **asdict(t),
            "status": t.status.value,
            "action": t.action.value if t.action else None,
        }
        for t in state.tasks.values()
    ]


def serialize_state(state: ExecutionState) -> dict:
    """将引擎状态序列化为可 JSON 存储的 dict。"""
    return {
        "status": state.status.value,
        "variables": state.variables,
        "tasks": serialize_tasks(state),
        "tokens": [asdict(t) for t in state.tokens.values()],
    }


def deserialize_state(dsl: WorkflowDSL, instance_id: str, data: dict) -> ExecutionState:
    """从快照恢复引擎状态（恢复后可直接调用 engine.approve/reject）。"""
    tasks = {
        t["id"]: EngineTask(
            id=t["id"],
            node_key=t["node_key"],
            node_name=t["node_name"],
            assignee_id=t["assignee_id"],
            status=TaskStatus(t["status"]),
            round=t["round"],
            counter_sign_group_id=t.get("counter_sign_group_id"),
            action=TaskAction(t["action"]) if t.get("action") else None,
        )
        for t in data["tasks"]
    }
    tokens = {
        tk["id"]: EngineToken(id=tk["id"], current_key=tk["current_key"], path=tk["path"])
        for tk in data["tokens"]
    }
    return ExecutionState(
        instance_id=instance_id,
        dsl=dsl,
        status=InstanceStatus(data["status"]),
        variables=dict(data["variables"]),
        tasks=tasks,
        tokens=tokens,
    )
