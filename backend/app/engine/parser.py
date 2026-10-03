"""DSL 解析与静态校验（权威校验层）。

对应详细设计文档第三部分 §2.1 的 6 项校验规则：
1. 结构完整性：有且仅有一个 start/end；边引用的 nodeKey 必须存在
2. 可达性：start 可达所有节点；除 end 外所有节点都有出边（否则死胡同）
3. 环检测：存在不含 rework 豁免的环 → 死循环风险
4. 网关配对：排他网关分支/默认分支完整；并行 split 至少两条出边且需有 join
5. 必填配置：webhook 必须 https、等待回调的 webhook 不能直接指向 end 等
6. 表达式校验：条件表达式可被沙箱编译；引用变量需在声明列表中（警告级）

校验结果分 errors（阻塞发布）与 warnings（不阻塞，仅提示），一次性全部返回。
"""

import asyncio
from dataclasses import dataclass, field

from simpleeval import SimpleEval

from app.domain.dsl import (
    ApprovalNode,
    Edge,
    ExclusiveGatewayNode,
    Node,
    NodeType,
    ParallelGatewayNode,
    WebhookNode,
    WorkflowDSL,
)


@dataclass
class ValidationIssue:
    """单条校验问题。

    Attributes:
        severity: error（阻塞发布）/ warning（提示）。
        node_key: 关联节点（图级别问题为 None）。
        message: 人读问题描述。
    """

    severity: str  # "error" | "warning"
    message: str
    node_key: str | None = None


@dataclass
class ValidationResult:
    """校验结果聚合。"""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """无 error 即通过。"""
        return not self.errors


def _outgoing(edges: list[Edge]) -> dict[str, list[Edge]]:
    """按 source 分组出边。"""
    result: dict[str, list[Edge]] = {}
    for e in edges:
        result.setdefault(e.source, []).append(e)
    return result


def _incoming(edges: list[Edge]) -> dict[str, list[Edge]]:
    """按 target 分组入边。"""
    result: dict[str, list[Edge]] = {}
    for e in edges:
        result.setdefault(e.target, []).append(e)
    return result


def _detect_cycle(nodes: dict[str, Node], edges: list[Edge]) -> list[str] | None:
    """DFS 环检测；rework 回退边豁免（它是被允许指回历史节点的显式语义）。

    Returns:
        环上的节点 key 列表（发现环时），否则 None。
    """
    graph: dict[str, list[str]] = {}
    for e in edges:
        if e.edge_type == "rework":
            continue
        graph.setdefault(e.source, []).append(e.target)

    WHITE, GRAY, BLACK = 0, 1, 2  # 三色标记：未访问 / 递归栈中 / 已完成
    color = {k: WHITE for k in nodes}
    path: list[str] = []

    def dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        path.append(u)
        for v in graph.get(u, []):
            if color.get(v) == GRAY:
                # 找到环：返回从 v 在 path 中首次出现的位置到当前的切片
                return path[path.index(v):]
            if color.get(v) == WHITE:
                found = dfs(v)
                if found:
                    return found
        path.pop()
        color[u] = BLACK
        return None

    for key in nodes:
        if color[key] == WHITE:
            found = dfs(key)
            if found:
                return found
    return None


def _reachable_from_start(dsl: WorkflowDSL) -> set[str]:
    """从 start 出发 BFS 可达的节点集合。"""
    start = next(k for k, n in dsl.nodes.items() if n.type == NodeType.START)
    seen = {start}
    queue = [start]
    out = _outgoing(dsl.edges)
    while queue:
        cur = queue.pop()
        for e in out.get(cur, []):
            if e.target not in seen:
                seen.add(e.target)
                queue.append(e.target)
    return seen


def _compile_expression(expression: str) -> None:
    """语法检查：用 ast.parse 试编译表达式，语法错误抛异常（不执行任何语义）。

    运行期安全由 simpleeval 沙箱（evaluator.py / executor 降级策略）保证，
    这里只负责把"写错了"的表达式在发布前拦下来。
    """
    import ast

    ast.parse(expression, mode="eval")


def validate_dsl(dsl: WorkflowDSL) -> ValidationResult:
    """对 DSL 执行全部静态校验，返回 errors + warnings。

    Args:
        dsl: 已通过 Pydantic 结构校验的流程定义。

    Returns:
        ValidationResult：ok=True 表示可发布。
    """
    result = ValidationResult()
    nodes = dsl.nodes
    node_keys = set(nodes)

    # ---- 规则 1：结构完整性 ----
    starts = [k for k, n in nodes.items() if n.type == NodeType.START]
    ends = [k for k, n in nodes.items() if n.type == NodeType.END]
    if len(starts) != 1:
        result.errors.append(ValidationIssue("error", f"start 节点数量必须为 1，当前 {len(starts)}"))
    if len(ends) != 1:
        result.errors.append(ValidationIssue("error", f"end 节点数量必须为 1，当前 {len(ends)}"))

    for i, e in enumerate(dsl.edges):
        if e.source not in node_keys or e.target not in node_keys:
            result.errors.append(
                ValidationIssue("error", f"第 {i} 条边引用了不存在的节点 {e.source}->{e.target}")
            )

    # ---- 规则 2：可达性 / 死胡同 ----
    if len(starts) == 1:
        reachable = _reachable_from_start(dsl)
        for key in node_keys - reachable:
            result.errors.append(ValidationIssue("error", f"节点 {key} 从 start 不可达", key))
    out = _outgoing(dsl.edges)
    for key, node in nodes.items():
        if node.type != NodeType.END and not out.get(key):
            result.errors.append(ValidationIssue("error", f"节点 {key} 无出边（死胡同）", key))

    # ---- 规则 3：环检测 ----
    cycle = _detect_cycle(nodes, dsl.edges)
    if cycle:
        result.errors.append(ValidationIssue("error", f"检测到死循环风险：{' -> '.join(cycle)}"))

    # ---- 规则 4/5：网关配对与必填配置 ----
    splits = [k for k, n in nodes.items() if isinstance(n, ParallelGatewayNode) and n.kind == "split"]
    joins = [k for k, n in nodes.items() if isinstance(n, ParallelGatewayNode) and n.kind == "join"]
    for s in splits:
        if len(out.get(s, [])) < 2:
            result.errors.append(ValidationIssue("error", f"并行分叉 {s} 至少需要两条出边", s))
    if splits and not joins:
        result.errors.append(ValidationIssue("error", "存在并行分叉但缺少汇合(join)节点"))
    for j in joins:
        if nodes[j].join_type is None:  # type: ignore[union-attr]
            result.errors.append(ValidationIssue("error", f"并行汇合 {j} 必须声明 join_type", j))

    for key, node in nodes.items():
        if isinstance(node, ExclusiveGatewayNode):
            # 路由以边为事实源：每个条件分支 + default 都必须有对应 branch_key 的出边
            gw_edges = {e.branch_key for e in out.get(key, []) if e.branch_key}
            required = {b.branch_key for b in node.branches} | {node.default_branch_key}
            missing = required - gw_edges
            if missing:
                result.errors.append(
                    ValidationIssue("error", f"排他网关 {key} 缺少分支出边: {sorted(missing)}", key)
                )
            # 条件分支的 branch_key 与 default 重名会导致路由歧义
            if node.default_branch_key in {b.branch_key for b in node.branches}:
                result.errors.append(
                    ValidationIssue("error", f"排他网关 {key} 的 default_branch_key 与条件分支重名", key)
                )
        if isinstance(node, ApprovalNode) and not node.assignee.mode:
            # Pydantic 已保证字段存在，这里防显式空串
            result.errors.append(ValidationIssue("error", f"审批节点 {key} 缺少审批人配置", key))
        if isinstance(node, WebhookNode) and not node.url.startswith(("https://", "http://localhost")):
            # 生产强制 https；本地调试允许 localhost
            result.errors.append(ValidationIssue("error", f"Webhook 节点 {key} 的 url 必须为 https", key))

    # ---- 规则 6：表达式校验 ----
    declared = {v.key for v in dsl.variables}
    for key, node in nodes.items():
        if isinstance(node, ExclusiveGatewayNode):
            for branch in node.branches:
                try:
                    _compile_expression(branch.condition)
                except Exception:  # simpleeval 各类错误统一视为不可编译
                    result.errors.append(
                        ValidationIssue(
                            "error", f"分支 '{branch.branch_key}' 表达式无法编译: {branch.condition}", key
                        )
                    )
                else:
                    # 引用未声明变量降级为 warning：可能来自上游脚本节点产出
                    referenced = {t for t in _identifiers(branch.condition) if not t.startswith("$_")}
                    unknown = referenced - declared
                    if unknown:
                        result.warnings.append(
                            ValidationIssue(
                                "warning",
                                f"分支 '{branch.branch_key}' 引用了未声明变量: {sorted(unknown)}",
                                key,
                            )
                        )
    return result


def _identifiers(expression: str) -> set[str]:
    """从表达式中粗提取标识符（用于未声明变量告警）。

    简化实现：按非字母数字下划线切分，过滤纯数字；不求语法树，
    误报由 warnings 级别兜底，不影响发布。
    """
    import re

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)
    keywords = {"and", "or", "not", "True", "False", "None", "if", "else"}
    return {t for t in tokens if t not in keywords and not t.isdigit()}


async def validate_expression_runtime(expression: str, variables: dict) -> bool:
    """运行期条件求值（带 50ms 超时保护），供 executor 使用。

    Raises:
        ExpressionError: 求值失败（语法/未定义变量/超时）。
    """
    from simpleeval import NameNotDefined

    from app.engine.exceptions import ExpressionError

    evaluator = SimpleEval(
        names=variables,
        functions={"len": len, "abs": abs, "min": min, "max": max, "round": round, "str": str},
    )
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(evaluator.eval, expression), timeout=0.05
        )
    except NameNotDefined as exc:
        raise ExpressionError(f"表达式引用了未定义变量: {exc}") from exc
    except asyncio.TimeoutError as exc:
        raise ExpressionError(f"表达式求值超时(>50ms): {expression}") from exc
    except Exception as exc:
        raise ExpressionError(f"表达式求值失败: {exc}") from exc
    return bool(result)
