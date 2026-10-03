"""M3 集成测试：真实 SQLite 库上的发起→审批→驳回→重提交→完成 全链路。"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.outbox import LoggingDispatcher, dispatch_pending_events
from app.application.workflow_service import WorkflowService
from app.infra.models.definition import WorkflowDefinition, WorkflowDefinitionVersion
from tests.engine.conftest import branch_dsl, simple_serial_dsl


async def publish_definition(factory, dsl) -> str:
    """直接落库发布一个定义（发布 API 在 M4 实装，测试前置数据）。"""
    async with factory() as session:
        definition = WorkflowDefinition(
            id=uuid4().hex, code=dsl.code, name=dsl.name,
            status="published", current_version=1,
        )
        version = WorkflowDefinitionVersion(
            id=uuid4().hex, definition_id=definition.id, version=1,
            dsl=dsl.model_dump(mode="json"), dsl_hash="test-hash",
            published_at=datetime.now(timezone.utc),
        )
        session.add_all([definition, version])
        await session.commit()
        return definition.id


def make_service(sqlite_db: str) -> tuple[WorkflowService, async_sessionmaker]:
    """基于隔离库构造服务与会话工厂。"""
    engine = create_async_engine(sqlite_db)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return WorkflowService(factory, admin_ids=["admin-1"]), factory


@pytest.fixture()
def svc(sqlite_db):
    """服务 + 工厂元组。"""
    return make_service(sqlite_db)


class TestSerialFlowE2E:
    """端到端：发起 → 审批 → 完成。"""

    async def test_full_cycle(self, svc) -> None:
        """串行流程全链路 + 事件 Outbox 投递。"""
        service, factory = svc
        dsl = simple_serial_dsl()
        await publish_definition(factory, dsl)

        started = await service.start_instance(
            definition_code=dsl.code, initiator_id="boss-1",
            form_data={"days": 1}, business_key="LEAVE-1",
            operation_id="op-start-1",
        )
        assert started["status"] == "running"
        first_task = started["tasks"][0]
        assert first_task["assigneeId"] == "user-of-approve_1"

        # 幂等：同 operationId 再次发起返回同一实例
        again = await service.start_instance(
            definition_code=dsl.code, initiator_id="boss-1",
            business_key="LEAVE-1", operation_id="op-start-1",
        )
        assert again["instanceId"] == started["instanceId"]

        # 非处理人审批被拒（43101）
        from app.application.errors import ApplicationError

        with pytest.raises(ApplicationError) as exc_info:
            await service.approve(task_id=first_task["taskId"], user_id="someone-else")
        assert exc_info.value.code == 43101

        # 处理人审批 → 完成
        result = await service.approve(
            task_id=first_task["taskId"], user_id="user-of-approve_1",
            opinion="同意", operation_id="op-approve-1",
        )
        assert result["instanceStatus"] == "completed"

        # Outbox：事件待投递 → 投递后清零
        dispatched = await dispatch_pending_events(factory)
        assert dispatched > 0
        assert await dispatch_pending_events(factory, LoggingDispatcher()) == 0

    async def test_business_key_duplicate_rejected(self, svc) -> None:
        """同 businessKey 二次发起应报 42001。"""
        from app.application.errors import BusinessKeyDuplicateError

        service, factory = svc
        dsl = simple_serial_dsl()
        await publish_definition(factory, dsl)
        await service.start_instance(definition_code=dsl.code, initiator_id="u0", business_key="B-1")
        with pytest.raises(BusinessKeyDuplicateError):
            await service.start_instance(definition_code=dsl.code, initiator_id="u0", business_key="B-1")


class TestRejectCycleE2E:
    """端到端：发起 → 驳回到发起人 → 修改重提交 → 完成。"""

    async def test_reject_and_resubmit(self, svc) -> None:
        """驳回后 start 节点重建任务（round=2），重提交后走完。"""
        service, factory = svc
        dsl = simple_serial_dsl()
        await publish_definition(factory, dsl)

        started = await service.start_instance(definition_code=dsl.code, initiator_id="boss-1")
        first_task = started["tasks"][0]

        # 审批人驳回到发起人
        await service.reject(
            task_id=first_task["taskId"], user_id="user-of-approve_1",
            opinion="材料不全", target_node_key="start",
        )
        todo = await service.list_todo("boss-1")
        assert len(todo) == 1
        assert todo[0]["round"] == 2  # 发起人第二轮

        # 发起重提交（start 任务的处理人是发起人）
        resubmit = await service.approve(task_id=todo[0]["taskId"], user_id="boss-1")
        assert resubmit["tasks"][0]["nodeKey"] == "approve_1"

        # 审批通过 → 完成
        final = await service.approve(
            task_id=resubmit["tasks"][0]["taskId"], user_id="user-of-approve_1"
        )
        assert final["instanceStatus"] == "completed"


class TestBranchFlowE2E:
    """端到端：条件分支路由。"""

    async def test_branch_routing(self, svc) -> None:
        """days=5 走 VIP 分支，处理人为 VIP 节点审批人。"""
        service, factory = svc
        dsl = branch_dsl()
        await publish_definition(factory, dsl)

        started = await service.start_instance(
            definition_code=dsl.code, initiator_id="u0", form_data={"days": 5}
        )
        assert started["tasks"][0]["nodeKey"] == "approve_vip"
