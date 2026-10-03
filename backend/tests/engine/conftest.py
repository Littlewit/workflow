"""引擎测试公共设施：DSL fixture 工厂。

提供最小可用的流程 DSL 构造器，供 M2 引擎内核单测与 M3 集成测试复用，
避免每个测试重复拼装大段 JSON。
"""

from typing import Any

from app.domain.dsl import (
    ApprovalNode,
    AssigneeStrategy,
    Edge,
    EndNode,
    ExclusiveGatewayNode,
    Node,
    StartNode,
    WorkflowDSL,
)


def approval_node(key: str = "approve_1", name: str = "审批", **kwargs: Any) -> ApprovalNode:
    """构造一个最简审批节点（默认指定人员 fixed_list）。"""
    return ApprovalNode(
        key=key,
        name=name,
        assignee=AssigneeStrategy(mode="fixed_list", params={"user_ids": [f"user-of-{key}"]}),
        **kwargs,
    )


def simple_serial_dsl() -> WorkflowDSL:
    """串行审批 DSL：start -> approve_1 -> end（冒烟基线）。"""
    nodes: dict[str, Node] = {
        "start": StartNode(key="start", name="发起"),
        "approve_1": approval_node(),
        "end": EndNode(key="end", name="结束"),
    }
    edges = [
        Edge(source="start", target="approve_1"),
        Edge(source="approve_1", target="end"),
    ]
    return WorkflowDSL(code="wf_test", name="测试流程", nodes=nodes, edges=edges)


def branch_dsl(condition_true_target: str = "approve_vip") -> WorkflowDSL:
    """条件分支 DSL：start -> gateway ->(命中-> approve_vip | default-> approve_normal)-> end。"""
    nodes: dict[str, Node] = {
        "start": StartNode(key="start", name="发起"),
        "gateway": ExclusiveGatewayNode(
            key="gateway",
            name="条件判断",
            branches=[
                {"branch_key": "vip", "condition": "days > 3", "target": condition_true_target}
            ],
            default_branch_key="normal",
        ),
        condition_true_target: approval_node(key=condition_true_target, name="VIP审批"),
        "approve_normal": approval_node(key="approve_normal", name="普通审批"),
        "end": EndNode(key="end", name="结束"),
    }
    edges = [
        Edge(source="start", target="gateway"),
        Edge(source="gateway", target=condition_true_target, branch_key="vip"),
        Edge(source="gateway", target="approve_normal", branch_key="normal"),
        Edge(source=condition_true_target, target="end"),
        Edge(source="approve_normal", target="end"),
    ]
    return WorkflowDSL(code="wf_branch", name="分支流程", nodes=nodes, edges=edges)
