"""超时/SLA 扫描集成测试（M5-T5.2）。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm.attributes import flag_modified

from app.application.workflow_service import WorkflowService
from app.infra.models.definition import WorkflowDefinition, WorkflowDefinitionVersion
from tests.engine.conftest import simple_serial_dsl


def timeout_dsl(action: str) -> dict:
    """带超时策略的串行 DSL（duration 最小 1 分钟，测试中将 deadline 改到过去）。"""
    dsl = simple_serial_dsl().model_dump(mode="json")
    dsl["nodes"]["approve_1"]["timeout_policy"] = {
        "duration_minutes": 1,
        "action": action,
        "transfer_to": "user-backup-1" if action == "transfer_to" else None,
    }
    return dsl


async def publish(factory, dsl_json: dict) -> None:
    """落库发布定义。"""
    async with factory() as session:
        definition = WorkflowDefinition(
            id="def-1", code=dsl_json["code"], name="t",
            status="published", current_version=1, draft_dsl=dsl_json,
        )
        version = WorkflowDefinitionVersion(
            id="ver-1", definition_id="def-1", version=1,
            dsl=dsl_json, dsl_hash="x",
        )
        session.add_all([definition, version])
        await session.commit()


def make_service(url: str) -> tuple[WorkflowService, async_sessionmaker]:
    """构造服务与工厂。"""
    factory = async_sessionmaker(create_async_engine(url), expire_on_commit=False)
    return WorkflowService(factory, admin_ids=["admin-1"]), factory


async def _expire_first_deadline(factory, instance_id: str) -> None:
    """把任务的 deadline 改到过去（模拟超时到期）：快照与镜像表同步更新。"""

    from app.infra.models.instance import TaskInstance, WorkflowInstance

    async with factory() as session:
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        instance = await session.get(WorkflowInstance, instance_id)
        assert instance is not None
        for t in instance.engine_state["tasks"]:
            t["deadline_at"] = past.isoformat()
        # JSON 列的原地修改必须显式标记，否则不会持久化
        flag_modified(instance, "engine_state")
        rows = (await session.execute(
            select(TaskInstance).where(TaskInstance.instance_id == instance_id)
        )).scalars().all()
        for row in rows:
            row.deadline_at = past
        await session.commit()


@pytest.mark.asyncio
class TestTimeoutScan:
    """超时策略执行。"""

    @pytest.mark.parametrize(
        ("action", "expect_status"),
        [("auto_approve", "approved"), ("auto_reject", "rejected"), ("transfer_to", "transferred")],
    )
    async def test_policies(self, sqlite_db, action, expect_status) -> None:
        """三种自动策略：到期后扫描触发对应动作。"""
        service, factory = make_service(sqlite_db)
        await publish(factory, timeout_dsl(action))
        started = await service.start_instance(definition_code="wf_test", initiator_id="boss-1")
        await _expire_first_deadline(factory, started["instanceId"])

        processed = await service.scan_overdue_tasks()
        assert processed, "应有任务被扫描处理"

        detail = await service.get_instance_detail(started["instanceId"])
        task = detail["tasks"][0]
        assert task["status"] in (expect_status, "pending", "canceled")
        if action != "transfer_to":
            # auto approve/reject 会推进或驳回：任务状态应为终态
            assert task["status"] == expect_status
        else:
            # 转交后新任务给 backup
            assert any(t["assigneeId"] == "user-backup-1" for t in detail["tasks"])

    async def test_scan_is_idempotent(self, sqlite_db) -> None:
        """重复扫描不重复处理（幂等）。"""
        service, factory = make_service(sqlite_db)
        await publish(factory, timeout_dsl("auto_approve"))
        started = await service.start_instance(definition_code="wf_test", initiator_id="boss-1")
        await _expire_first_deadline(factory, started["instanceId"])

        first = await service.scan_overdue_tasks()
        assert len(first) == 1
        second = await service.scan_overdue_tasks()
        assert second == []  # 任务已终态，不再命中
