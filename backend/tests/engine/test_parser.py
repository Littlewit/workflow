"""DSL 静态校验测试（T2.1）：6 项规则逐条覆盖。"""

from app.domain.dsl import Edge, EndNode, StartNode, WorkflowDSL
from app.engine.parser import validate_dsl
from tests.engine.conftest import approval_node, branch_dsl, simple_serial_dsl


def _dsl_with(nodes_dict: dict, edges: list[Edge]) -> WorkflowDSL:
    """用原始 dict 快速构造 DSL（绕过便捷工厂，便于构造非法结构）。"""
    return WorkflowDSL(code="wf_x", name="x", nodes=nodes_dict, edges=edges)  # type: ignore[arg-type]


class TestStructureRules:
    """规则 1：结构完整性。"""

    def test_missing_end_rejected(self) -> None:
        """缺少 end 节点应报 error。"""
        dsl = _dsl_with(
            {"start": StartNode(key="start", name="s"), "a": approval_node(key="a")},
            [Edge(source="start", target="a")],
        )
        result = validate_dsl(dsl)
        assert not result.ok
        assert any("end" in e.message for e in result.errors)

    def test_edge_referencing_missing_node_rejected(self) -> None:
        """边引用不存在的节点应报 error。"""
        dsl = simple_serial_dsl().model_copy(deep=True)
        dsl.edges.append(Edge(source="approve_1", target="ghost"))
        result = validate_dsl(dsl)
        assert any("ghost" in e.message for e in result.errors)


class TestReachabilityRules:
    """规则 2：可达性 / 死胡同。"""

    def test_unreachable_node_rejected(self) -> None:
        """start 不可达的节点应报 error。"""
        dsl = _dsl_with(
            {
                "start": StartNode(key="start", name="s"),
                "end": EndNode(key="end", name="e"),
                "orphan": approval_node(key="orphan"),
            },
            [Edge(source="start", target="end")],  # orphan 无任何边
        )
        result = validate_dsl(dsl)
        assert any("orphan" in e.message and "不可达" in e.message for e in result.errors)

    def test_dead_end_rejected(self) -> None:
        """非 end 节点无出边（死胡同）应报 error。"""
        dsl = _dsl_with(
            {
                "start": StartNode(key="start", name="s"),
                "a": approval_node(key="a"),
                "end": EndNode(key="end", name="e"),
            },
            [Edge(source="start", target="a")],  # a -> end 缺失
        )
        result = validate_dsl(dsl)
        assert any("死胡同" in e.message for e in result.errors)


class TestCycleRules:
    """规则 3：死循环检测。"""

    def test_cycle_rejected(self) -> None:
        """a->b->a 的环应报 error。"""
        dsl = _dsl_with(
            {
                "start": StartNode(key="start", name="s"),
                "a": approval_node(key="a"),
                "b": approval_node(key="b"),
                "end": EndNode(key="end", name="e"),
            },
            [
                Edge(source="start", target="a"),
                Edge(source="a", target="b"),
                Edge(source="b", target="a"),  # 环
                Edge(source="b", target="end"),
            ],
        )
        result = validate_dsl(dsl)
        assert any("死循环" in e.message for e in result.errors)

    def test_valid_dsl_has_no_errors(self) -> None:
        """基线串行/分支 DSL 应通过校验（防误报）。"""
        assert validate_dsl(simple_serial_dsl()).ok
        assert validate_dsl(branch_dsl()).ok


class TestGatewayRules:
    """规则 4：网关配对。"""

    def test_gateway_missing_default_branch_edge_rejected(self) -> None:
        """default 分支缺少对应出边应报 error。"""
        dsl = branch_dsl().model_copy(deep=True)
        dsl.edges = [e for e in dsl.edges if e.branch_key != "normal"]
        result = validate_dsl(dsl)
        assert any("normal" in e.message for e in result.errors)


class TestExpressionRules:
    """规则 6：表达式校验。"""

    def test_undeclared_variable_warns_not_errors(self) -> None:
        """引用未声明变量降级为 warning，不阻塞发布。"""
        dsl = branch_dsl().model_copy(deep=True)
        result = validate_dsl(dsl)
        assert result.ok  # 未声明变量只警告
        assert any("未声明变量" in w.message for w in result.warnings)

    def test_broken_expression_rejected(self) -> None:
        """语法错误的表达式应报 error。"""
        dsl = branch_dsl().model_copy(deep=True)
        gw = dsl.nodes["gateway"]
        gw.branches[0].condition = "days >>> 3"  # 非法语法  # type: ignore[union-attr]
        result = validate_dsl(dsl)
        assert any("无法编译" in e.message for e in result.errors)
