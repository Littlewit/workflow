"""演示数据种子脚本（M7 体验用）。

用法：`.venv\\Scripts\\python.exe scripts/seed_demo.py`（使用 WF_DATABASE_URL，默认开发库）
幂等：检测到演示定义已存在则跳过，可安全重复执行。

造数角色（与内置登录账号对应，见 app/core/security.py）：
- admin-1 (admin)  ：发起人 + 审批人，登录即可体验全流程
- boss-1 (bob)     ：发起人
- user-of-approve_1 (alice)：审批人
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

from sqlalchemy import select  # noqa: E402

from app.application.definition_service import DefinitionService  # noqa: E402
from app.application.workflow_service import WorkflowService  # noqa: E402
from app.domain.dsl import (  # noqa: E402
    ApprovalNode,
    AssigneeStrategy,
    Edge,
    EndNode,
    ExclusiveGatewayNode,
    StartNode,
    WorkflowDSL,
)
from app.infra.models.definition import WorkflowDefinition  # noqa: E402

SEED_CODES = ["wf_leave", "wf_expense", "wf_contract"]


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
                    }
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
                    }
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
                    }
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


async def main() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    factory = async_sessionmaker(create_async_engine(get_settings().database_url), expire_on_commit=False)

    # 幂等：演示定义已存在则跳过
    async with factory() as session:
        exists = (await session.execute(
            select(WorkflowDefinition.id).where(WorkflowDefinition.code.in_(SEED_CODES))
        )).first()
    if exists is not None:
        print("演示数据已初始化过，跳过。如需重建请手动清理相关定义。")
        return

    def_service = DefinitionService(factory)
    wf_service = WorkflowService(factory, admin_ids=["admin-1"])

    for dsl in (make_leave_dsl(), make_expense_dsl(), make_contract_dsl()):
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

    print("=" * 50)
    print("演示数据初始化完成！用 admin/admin123 登录体验：")
    print("  我的待办 4 条（含会签/驳回重走）· 已办 3 条 · 我发起的 3 条 · 监控看板已有数据")


if __name__ == "__main__":
    asyncio.run(main())
