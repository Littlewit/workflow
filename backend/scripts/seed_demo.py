"""演示数据种子脚本（M7 体验用）。

用法：
- 首次生成：`.venv\\Scripts\\python.exe scripts/seed_demo.py`
- 重建（先清空演示数据再生成）：`.venv\\Scripts\\python.exe scripts/seed_demo.py --force`

幂等：检测到演示定义已存在则跳过；--force 会先删除演示定义及其全部实例数据。

造数角色（与内置登录账号对应，见 app/core/security.py）：
- admin-1 (admin) ：发起人 + 审批人，登录即可体验全流程
- boss-1 (bob)    ：发起人
- user-of-approve_1 (alice)：审批人

流程设计覆盖面（对应新纵向设计器的可视化形态）：
- wf_leave    条件分支（天数判断）→ 分支汇聚
- wf_expense  串行多级审批
- wf_contract 会签（ALL）
- wf_purchase 条件分支 → 高值双级审批 / 默认单级审批 → 汇聚 → 抄送节点
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PYTHONUTF8", "1")
# Windows GBK 控制台兼容：强制 stdout 用 UTF-8（✔ 等字符）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import delete, select  # noqa: E402

from app.application.definition_service import DefinitionService  # noqa: E402
from app.application.workflow_service import WorkflowService  # noqa: E402
from app.domain.dsl import (  # noqa: E402
    ApprovalNode,
    AssigneeStrategy,
    CCNode,
    Edge,
    EndNode,
    ExclusiveGatewayNode,
    StartNode,
    WorkflowDSL,
)
from app.infra.models.definition import WorkflowDefinition, WorkflowDefinitionVersion  # noqa: E402
from app.infra.models.instance import (  # noqa: E402
    InstanceEvent,
    TaskInstance,
    TaskOpinion,
    WebhookDelivery,
    WorkflowInstance,
    WorkflowVariable,
)

SEED_CODES = ["wf_leave", "wf_expense", "wf_contract", "wf_purchase"]


def make_leave_dsl() -> WorkflowDSL:
    """请假审批：start -> 部门主管 -> (days>3 ? 总监 : 人事) -> end。"""
    return WorkflowDSL(
        code="wf_leave",
        name="请假审批",
        variables=[{"key": "days", "type": "number", "required": True}],
        nodes={
            "start": StartNode(
                key="start", name="发起",
                form_schema={
                    "properties": {
                        "days": {"type": "number", "title": "请假天数"},
                        "reason": {"type": "string", "title": "请假事由"},
                    },
                    "required": ["days"],
                },
            ),
            "approve_1": ApprovalNode(
                key="approve_1", name="部门主管审批",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["admin-1"]}),
            ),
            "gateway": ExclusiveGatewayNode(
                key="gateway", name="天数判断",
                branches=[{"branch_key": "long", "condition": "days > 3", "target": "approve_vip"}],
                default_branch_key="normal",
            ),
            "approve_vip": ApprovalNode(
                key="approve_vip", name="总监审批（>3天）",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["user-of-approve_1"]}),
            ),
            "approve_normal": ApprovalNode(
                key="approve_normal", name="人事备案",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["user-of-approve_1"]}),
            ),
            "end": EndNode(key="end", name="结束"),
        },
        edges=[
            Edge(source="start", target="approve_1"),
            Edge(source="approve_1", target="gateway"),
            Edge(source="gateway", target="approve_vip", branch_key="long"),
            Edge(source="gateway", target="approve_normal", branch_key="normal"),
            Edge(source="approve_vip", target="end"),
            Edge(source="approve_normal", target="end"),
        ],
    )


def make_expense_dsl() -> WorkflowDSL:
    """报销审批：start -> 财务初审(admin) -> 财务复审(alice) -> end。"""
    return WorkflowDSL(
        code="wf_expense",
        name="报销审批",
        nodes={
            "start": StartNode(
                key="start", name="发起",
                form_schema={
                    "properties": {
                        "amount": {"type": "number", "title": "报销金额"},
                        "reason": {"type": "string", "title": "报销事由"},
                    },
                    "required": ["amount"],
                },
            ),
            "check_1": ApprovalNode(
                key="check_1", name="财务初审",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["admin-1"]}),
            ),
            "check_2": ApprovalNode(
                key="check_2", name="财务复审",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["user-of-approve_1"]}),
            ),
            "end": EndNode(key="end", name="结束"),
        },
        edges=[
            Edge(source="start", target="check_1"),
            Edge(source="check_1", target="check_2"),
            Edge(source="check_2", target="end"),
        ],
    )


def make_contract_dsl() -> WorkflowDSL:
    """合同会签：start -> 双人会签(ALL) -> end。"""
    return WorkflowDSL(
        code="wf_contract",
        name="合同会签",
        nodes={
            "start": StartNode(
                key="start", name="发起",
                form_schema={
                    "properties": {
                        "contract_no": {"type": "string", "title": "合同编号"},
                    },
                    "required": ["contract_no"],
                },
            ),
            "sign": ApprovalNode(
                key="sign", name="法务+业务会签",
                assignee=AssigneeStrategy(
                    mode="fixed_list", params={"user_ids": ["admin-1", "user-of-approve_1"]}
                ),
                counter_sign="ALL",
            ),
            "end": EndNode(key="end", name="结束"),
        },
        edges=[Edge(source="start", target="sign"), Edge(source="sign", target="end")],
    )


def make_purchase_dsl() -> WorkflowDSL:
    """采购申请（新设计器形态全展示）：

    start -> 金额判断(>10000 ? 高值 : 默认)
      高值：总监审批(alice) -> 总裁审批(admin)
      默认：部门主管审批(admin)
    汇聚 -> 抄送行政(alice，仅通知) -> end
    """
    return WorkflowDSL(
        code="wf_purchase",
        name="采购申请",
        variables=[{"key": "amount", "type": "number", "required": True}],
        nodes={
            "start": StartNode(
                key="start", name="发起",
                form_schema={
                    "properties": {
                        "item": {"type": "string", "title": "采购物品"},
                        "amount": {"type": "number", "title": "采购金额（元）"},
                    },
                    "required": ["item", "amount"],
                },
            ),
            "gateway": ExclusiveGatewayNode(
                key="gateway", name="金额判断",
                branches=[{"branch_key": "high", "condition": "amount > 10000", "target": "director"}],
                default_branch_key="normal",
            ),
            "director": ApprovalNode(
                key="director", name="总监审批（高值）",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["user-of-approve_1"]}),
            ),
            "ceo": ApprovalNode(
                key="ceo", name="总裁审批（高值）",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["admin-1"]}),
            ),
            "manager": ApprovalNode(
                key="manager", name="部门主管审批",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["admin-1"]}),
            ),
            "cc_admin": CCNode(
                key="cc_admin", name="抄送行政备案",
                assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": ["user-of-approve_1"]}),
            ),
            "end": EndNode(key="end", name="结束"),
        },
        edges=[
            Edge(source="start", target="gateway"),
            Edge(source="gateway", target="director", branch_key="high"),
            Edge(source="gateway", target="manager", branch_key="normal"),
            Edge(source="director", target="ceo"),
            Edge(source="ceo", target="cc_admin"),
            Edge(source="manager", target="cc_admin"),
            Edge(source="cc_admin", target="end"),
        ],
    )


async def purge_demo_data(factory) -> None:
    """--force 重建：删除演示定义的版本、定义本体及其全部实例相关数据。

    另顺带清理联调遗留的"%_copy_%"草稿副本。
    """
    async with factory() as session:
        def_ids = (await session.execute(
            select(WorkflowDefinition.id).where(WorkflowDefinition.code.in_(SEED_CODES))
        )).scalars().all()
        if def_ids:
            inst_ids = (await session.execute(
                select(WorkflowInstance.id).where(WorkflowInstance.definition_id.in_(def_ids))
            )).scalars().all()
            if inst_ids:
                # 先删实例明细（意见/任务/事件/变量/Webhook 投递），再删实例本体
                for table in (TaskOpinion, TaskInstance, InstanceEvent, WorkflowVariable, WebhookDelivery):
                    await session.execute(delete(table).where(table.instance_id.in_(inst_ids)))
                await session.execute(delete(WorkflowInstance).where(WorkflowInstance.id.in_(inst_ids)))
            await session.execute(
                delete(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.definition_id.in_(def_ids))
            )
            await session.execute(delete(WorkflowDefinition).where(WorkflowDefinition.id.in_(def_ids)))
        # 联调遗留的"另存副本"草稿（演示账号名下的 draft 副本，无实例数据）。
        # 注意：SQLite LIKE 未指定 ESCAPE 时反斜杠无转义语义，直接用 _ 通配即可
        junk = (await session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.status == "draft",
                WorkflowDefinition.code.like("%_copy_%"),
            )
        )).scalars().all()
        for d in junk:
            await session.delete(d)
        await session.commit()
    print("已清理旧演示数据")


async def main() -> None:
    force = "--force" in sys.argv

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    factory = async_sessionmaker(create_async_engine(get_settings().database_url), expire_on_commit=False)

    if force:
        await purge_demo_data(factory)

    # 幂等：演示定义已存在则跳过
    async with factory() as session:
        exists = (await session.execute(
            select(WorkflowDefinition.id).where(WorkflowDefinition.code.in_(SEED_CODES))
        )).first()
    if exists is not None:
        print("演示数据已初始化过，跳过。如需重建请加 --force 参数。")
        return

    def_service = DefinitionService(factory)
    wf_service = WorkflowService(factory, admin_ids=["admin-1"])

    for dsl in (make_leave_dsl(), make_expense_dsl(), make_contract_dsl(), make_purchase_dsl()):
        draft = await def_service.create_draft("admin-1", "", dsl.name, dsl.model_dump(mode="json"))
        await def_service.publish("admin-1", draft["definitionId"])
        print(f"已发布定义: {dsl.code} {dsl.name}")

    # ---- 请假审批：admin 既是发起人也是审批人 ----
    # 1) 已完成（走人事备案分支）——注意链式取"审批后返回的下一任务"
    s1 = await wf_service.start_instance(
        "wf_leave", "boss-1", {"days": 1, "reason": "事假"},
        business_key="DEMO-L-001", title="张三的事假申请（1天）",
    )
    r1 = await wf_service.approve(s1["tasks"][0]["taskId"], "admin-1", "同意")
    await wf_service.approve(r1["tasks"][0]["taskId"], "user-of-approve_1", "备案完成")
    print("[OK] 已完成实例：张三的事假申请（1天）")

    # 2) 运行中（5 天走总监分支，admin 待办：部门主管审批）
    s2 = await wf_service.start_instance(
        "wf_leave", "boss-1", {"days": 5, "reason": "年假"},
        business_key="DEMO-L-002", title="李四的年假申请（5天）",
    )
    print("[OK] 运行中实例：李四的年假申请（admin 待办：部门主管审批）")

    # 3) 驳回重走：admin 驳回自己的申请 → 发起人待办（round=2，可体验重提交）
    s3 = await wf_service.start_instance(
        "wf_leave", "admin-1", {"days": 2, "reason": "调休"},
        business_key="DEMO-L-003", title="管理员自己的调休申请",
    )
    await wf_service.reject(s3["tasks"][0]["taskId"], "admin-1", "请补充调休明细", target_node_key="start")
    print("[OK] 驳回重走实例：管理员自己的调休申请（admin 待办：重新提交）")

    # ---- 报销审批：admin 初审待办 ----
    e1 = await wf_service.start_instance(
        "wf_expense", "boss-1", {"amount": 3200, "reason": "出差差旅费"},
        business_key="DEMO-E-001", title="王五的差旅报销（3200元）",
    )
    print("[OK] 运行中实例：王五的差旅报销（admin 待办：财务初审）")

    e2 = await wf_service.start_instance(
        "wf_expense", "boss-1", {"amount": 150, "reason": "办公用品"},
        business_key="DEMO-E-002", title="赵六的办公报销（150元）",
    )
    r2 = await wf_service.approve(e2["tasks"][0]["taskId"], "admin-1", "初审通过")
    await wf_service.approve(r2["tasks"][0]["taskId"], "user-of-approve_1", "复审通过")
    print("[OK] 已完成实例：赵六的办公报销（150元）")

    # ---- 合同会签：alice 已投一票，等待 admin ----
    c1 = await wf_service.start_instance(
        "wf_contract", "boss-1", {"contract_no": "HT-2026-042"},
        business_key="DEMO-C-001", title="市场部推广合同会签",
    )
    sign_task = next(t for t in c1["tasks"] if t["assigneeId"] == "user-of-approve_1")
    await wf_service.approve(sign_task["taskId"], "user-of-approve_1", "业务侧无异议")
    print("[OK] 运行中实例：市场部推广合同会签（admin 待办：会签一票）")

    # ---- 采购申请：覆盖新设计器的分支/汇聚/抄送形态 ----
    # 1) 高值分支运行中：alice 待办（总监审批）
    p1 = await wf_service.start_instance(
        "wf_purchase", "boss-1", {"item": "服务器 x2", "amount": 50000},
        business_key="DEMO-P-001", title="研发部服务器采购（5万元）",
    )
    print("[OK] 运行中实例：研发部服务器采购（alice 待办：总监审批·高值分支）")

    # 2) 默认分支运行中：admin 待办（部门主管审批）
    p2 = await wf_service.start_instance(
        "wf_purchase", "boss-1", {"item": "办公椅 x10", "amount": 8000},
        business_key="DEMO-P-002", title="行政部办公椅采购（8千元）",
    )
    print("[OK] 运行中实例：行政部办公椅采购（admin 待办：部门主管审批·默认分支）")

    # 3) 高值全链路完成：总监 -> 总裁 -> 抄送行政（自动） -> 结束
    p3 = await wf_service.start_instance(
        "wf_purchase", "boss-1", {"item": "图形工作站", "amount": 20000},
        business_key="DEMO-P-003", title="设计部图形工作站采购（2万元）",
    )
    r3 = await wf_service.approve(p3["tasks"][0]["taskId"], "user-of-approve_1", "高值采购，同意")
    await wf_service.approve(r3["tasks"][0]["taskId"], "admin-1", "同意采购")
    print("[OK] 已完成实例：设计部图形工作站采购（高值分支全链路）")

    print("=" * 50)
    print("演示数据初始化完成！用 admin/admin123 登录体验：")
    print("  我的待办 5 条（含会签/驳回重走/采购双分支）· 已办 4 条 · 监控看板已有数据")
    print("  采购申请流程展示：条件分支 + 分支汇聚 + 抄送节点（alice 登录可看高值分支待办）")


if __name__ == "__main__":
    asyncio.run(main())
